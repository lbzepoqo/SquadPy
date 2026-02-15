"""Main server orchestrator — startup, shutdown, and lifecycle."""

import asyncio
import logging
import re
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from squadpy.config import ServerConfig, LoggingConfig, DatabaseConfig
from squadpy.api import WebsocketControlService
from squadpy.database import DatabaseManager
from squadpy.events.emitter import EventBus, EventHandler
from squadpy.events.types import BaseEvent, ChatMessage
from squadpy.log_parser.id_parser import parse_online_ids
from squadpy.layers import LayerCatalogService
from squadpy.logger import setup_logging
from squadpy.plugin_loader import PluginLoader, LoadedPlugin, PluginStatus
from squadpy.log_parser import LogParser, LocalLogReader, SFTPLogReader
from squadpy.rcon.client import RconClient
from squadpy.discord.connector import DiscordConnector

logger = logging.getLogger("squadpy")

VERSION = "0.1.0"

_CHAT_RE = re.compile(
    r"\[(?P<channel>ChatAll|ChatTeam|ChatSquad|ChatAdmin)\] "
    r"\[Online IDs:(?P<ids>[^\]]+)\] "
    r"(?P<name>.+?) : (?P<message>.*)"
)


def format_service_line(name: str, ok: bool, detail: str) -> str:
    status = "ok" if ok else "FAIL"
    return f"    {name:<16s} {status:<5s} {detail}"


def format_plugin_line(plugin: LoadedPlugin) -> str:
    if plugin.status == PluginStatus.ENABLED:
        return f"    {plugin.name:<24s} ok       enabled"
    elif plugin.status == PluginStatus.DISABLED:
        return f"    {plugin.name:<24s} --       disabled"
    else:
        return f"    {plugin.name:<24s} FAIL     {plugin.error}"


class SquadPyServer:
    def __init__(
        self,
        server_config: ServerConfig,
        logging_config: LoggingConfig,
        base_dir: Path,
        db_config: DatabaseConfig | None = None,
        *,
        manage_signals: bool = True,
        plugins_dir: Path | None = None,
        plugin_config_dir: Path | None = None,
    ):
        self._server_config = server_config
        self._logging_config = logging_config
        self._base_dir = base_dir
        self._db_config = db_config
        self._manage_signals = manage_signals
        self._plugins_dir = plugins_dir or (self._base_dir / "plugins")
        self._plugin_config_dir = plugin_config_dir or (self._base_dir / "config" / "plugins")
        self._running = False
        self._event_bus = EventBus()
        self._rcon: RconClient | None = None
        self._loaded_plugins: list[LoadedPlugin] = []
        self._periodic_tasks: list[tuple[str, asyncio.Task]] = []
        self._log_parser: LogParser | None = None
        self._log_parser_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._discord: DiscordConnector | None = None
        self._db: DatabaseManager | None = None
        self._api: WebsocketControlService | None = None
        self._layers: LayerCatalogService = LayerCatalogService()
        self._plugin_watchdog_enabled = self._server_config.plugin_watchdog.enabled
        self._plugin_watchdog_failure_threshold = self._server_config.plugin_watchdog.failure_threshold
        self._plugin_watchdog_failure_window_seconds = self._server_config.plugin_watchdog.failure_window_seconds
        self._event_handler_wrappers: dict[str, list[tuple[str, EventHandler]]] = {}
        self._plugin_failure_timestamps: dict[str, list[float]] = {}
        self._plugin_degradation_records: list[dict[str, str]] = []
        self._plugins_degrading: set[str] = set()

    @property
    def version(self) -> str:
        return VERSION

    @property
    def running(self) -> bool:
        return self._running

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def recent_plugin_degradation_records(self) -> list[dict[str, str]]:
        return list(self._plugin_degradation_records)

    async def _connect_rcon(self) -> tuple[bool, str]:
        try:
            self._rcon = RconClient(
                host=self._server_config.rcon.host,
                port=self._server_config.rcon.port,
                password=self._server_config.rcon.password,
            )
            await self._rcon.connect()
            self._rcon.on_chat = self._handle_chat
            detail = f"connected ({self._server_config.rcon.host}:{self._server_config.rcon.port})"
            return True, detail
        except Exception as e:
            logger.error("RCON connection failed: %s", e)
            return False, str(e)

    async def _start_log_reader(self) -> tuple[bool, str]:
        if not self._server_config.log.enabled:
            return False, "not configured"
        try:
            if self._server_config.log.mode == "local":
                reader = LocalLogReader(
                    self._server_config.log.path,
                    poll_interval=self._server_config.log.poll_interval,
                )
            elif self._server_config.log.mode == "sftp":
                reader = SFTPLogReader(
                    host=self._server_config.log.host,
                    port=self._server_config.log.port,
                    username=self._server_config.log.username,
                    password=self._server_config.log.password,
                    path=self._server_config.log.path,
                    poll_interval=self._server_config.log.poll_interval,
                )
            else:
                raise ValueError(f"Unsupported log mode: {self._server_config.log.mode}")
            self._log_parser = LogParser(
                reader=reader,
                event_bus=self._event_bus,
                rcon_client=self._rcon,
            )
            self._log_parser_task = asyncio.create_task(self._log_parser.run())
            return True, f"tailing ({self._server_config.log.mode})"
        except Exception as e:
            logger.error("Log reader failed: %s", e)
            return False, str(e)

    async def _connect_discord(self) -> tuple[bool, str]:
        if not self._server_config.discord.enabled:
            return False, "not configured"
        try:
            self._discord = DiscordConnector(self._server_config.discord)
            await self._discord.start()
            await asyncio.wait_for(self._discord.wait_until_ready(), timeout=30.0)
            bot_name = str(self._discord.bot.user) if self._discord.bot.user else "unknown"
            return True, f"connected ({bot_name})"
        except Exception as e:
            logger.error("Discord connection failed: %s", e)
            self._discord = None
            return False, str(e)

    async def _connect_database(self) -> tuple[bool, str]:
        if not self._db_config or not self._db_config.enabled:
            return False, "not configured"
        try:
            self._db = DatabaseManager()
            await self._db.initialize(self._db_config)
            if self._db_config.driver == "sqlite":
                detail = f"SQLite ({self._db_config.path})"
            elif self._db_config.driver == "postgresql":
                detail = f"PostgreSQL ({self._db_config.host}:{self._db_config.port}/{self._db_config.database})"
            else:
                detail = f"MySQL ({self._db_config.host}:{self._db_config.port}/{self._db_config.database})"
            return True, detail
        except Exception as e:
            logger.error("Database initialization failed: %s", e)
            self._db = None
            return False, str(e)

    async def _start_api(self) -> tuple[bool, str]:
        if not self._server_config.api.enabled:
            return False, "not configured"

        try:
            self._api = WebsocketControlService(
                token=self._server_config.api.auth_token,
                host=self._server_config.api.host,
                port=self._server_config.api.port,
                path=self._server_config.api.websocket_path,
                rbac_enabled=self._server_config.api.rbac_enabled,
                rbac_default_role=self._server_config.api.rbac_default_role,
                rbac_role_permissions=self._server_config.api.rbac_role_permissions,
                webhook_signing_enabled=self._server_config.api.webhook_signing_enabled,
                webhook_signing_secret=self._server_config.api.webhook_signing_secret,
                webhook_signature_header=self._server_config.api.webhook_signature_header,
                webhook_timestamp_header=self._server_config.api.webhook_timestamp_header,
                webhook_max_age_seconds=self._server_config.api.webhook_max_age_seconds,
                layer_catalog_service=self._layers,
                server=self,
            )
            await self._api.start()
            detail = (
                f"websocket "
                f"(ws://{self._server_config.api.host}:{self._server_config.api.port}"
                f"{self._server_config.api.websocket_path})"
            )
            return True, detail
        except Exception as e:
            logger.error("API service failed: %s", e)
            self._api = None
            return False, str(e)

    def _build_services(self, rcon, log_parser) -> dict:
        return {
            "rcon": rcon,
            "log_reader": log_parser,
            "discord": self._discord,
            "db": self._db,
            "layers": self._layers,
            "server": self,
        }

    async def _load_plugins(self, services: dict) -> None:
        plugin_loader = PluginLoader(
            plugins_dir=self._plugins_dir,
            config_dir=self._plugin_config_dir,
        )
        self._loaded_plugins = await plugin_loader.load_all(services)

    def _setup_signals(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    async def start(self) -> None:
        self._running = True

        log_dir = self._base_dir / self._logging_config.file.path
        setup_logging(self._logging_config, log_dir if self._logging_config.file.enabled else None)

        rcon_ok, rcon_detail = await self._connect_rcon()
        log_ok, log_detail = await self._start_log_reader()
        discord_ok, discord_detail = await self._connect_discord()
        db_ok, db_detail = await self._connect_database()
        api_ok, api_detail = await self._start_api()

        if self._db:
            try:
                await self._db.create_tables()
            except Exception as e:
                logger.error("Failed to create database tables: %s", e)

        services = self._build_services(
            rcon=self._rcon if rcon_ok else None,
            log_parser=self._log_parser if log_ok else None,
        )
        await self._load_plugins(services)

        for lp in self._loaded_plugins:
            if lp.status == PluginStatus.ENABLED and lp.instance:
                self._register_plugin_events(lp)
                self._start_periodic_tasks(lp)

        if self._discord:
            for lp in self._loaded_plugins:
                if lp.status == PluginStatus.ENABLED and lp.instance:
                    self._register_plugin_discord(lp)
            try:
                await self._discord.sync_commands()
            except Exception as e:
                logger.error("Failed to sync Discord commands: %s", e)

        self._print_summary(
            rcon_ok,
            rcon_detail,
            log_ok,
            log_detail,
            discord_ok,
            discord_detail,
            db_ok,
            db_detail,
            api_ok,
            api_detail,
        )

        if self._manage_signals:
            self._setup_signals()
        await self._shutdown_event.wait()

    def _register_plugin_events(self, loaded: LoadedPlugin) -> None:
        wrappers: list[tuple[str, EventHandler]] = []
        for event_name, method_name in loaded.event_handlers:
            handler = getattr(loaded.instance, method_name)
            wrapped = self._wrap_plugin_event_handler(loaded, method_name, handler)
            self._event_bus.subscribe(event_name, wrapped)
            wrappers.append((event_name, wrapped))
        self._event_handler_wrappers[loaded.dir_name] = wrappers

    def _unregister_plugin_events(self, plugin_dir_name: str) -> None:
        wrappers = self._event_handler_wrappers.pop(plugin_dir_name, [])
        for event_name, handler in wrappers:
            self._event_bus.unsubscribe(event_name, handler)

    def _wrap_plugin_event_handler(
        self,
        loaded: LoadedPlugin,
        method_name: str,
        handler: EventHandler,
    ) -> EventHandler:
        async def _wrapped(event: BaseEvent) -> None:
            try:
                await handler(event)
            except Exception as exc:
                await self._record_plugin_failure(
                    loaded,
                    source=f"event:{method_name}",
                    error=exc,
                )
                raise

        return _wrapped

    def _start_periodic_tasks(self, loaded: LoadedPlugin) -> None:
        for method_name, interval in loaded.periodic_tasks:
            method = getattr(loaded.instance, method_name)
            task = asyncio.create_task(
                self._run_periodic(loaded, method_name, method, interval)
            )
            self._periodic_tasks.append((loaded.dir_name, task))

    def _cancel_periodic_tasks(self, plugin_dir_name: str, *, skip_current_task: bool = False) -> None:
        remaining: list[tuple[str, asyncio.Task]] = []
        current_task = asyncio.current_task() if skip_current_task else None
        for dir_name, task in self._periodic_tasks:
            if dir_name == plugin_dir_name:
                if current_task is not None and task is current_task:
                    continue
                task.cancel()
            else:
                remaining.append((dir_name, task))
        self._periodic_tasks = remaining

    def _register_plugin_discord(self, loaded: LoadedPlugin) -> None:
        if not self._discord:
            return
        plugin_name = loaded.dir_name
        for meta, method_name in loaded.slash_commands:
            method = getattr(loaded.instance, method_name)
            self._discord.register_slash_command(
                plugin_name, method, name=meta["name"], description=meta.get("description", ""),
            )
        for meta, method_name in loaded.discord_handlers:
            method = getattr(loaded.instance, method_name)
            self._discord.register_interaction_handler(
                plugin_name, meta["event_type"], meta.get("custom_id"), method,
            )

    async def _run_periodic(
        self,
        loaded: LoadedPlugin,
        method_name: str,
        method,
        interval: float,
    ) -> None:
        while self._running:
            await asyncio.sleep(interval)
            if loaded.status != PluginStatus.ENABLED:
                return
            try:
                await method()
            except Exception as exc:
                logger.exception("Error in periodic task %s.%s", loaded.name, method_name)
                should_degrade = await self._record_plugin_failure(
                    loaded,
                    source=f"periodic:{method_name}",
                    error=exc,
                )
                if should_degrade:
                    return

    async def _record_plugin_failure(
        self,
        loaded: LoadedPlugin,
        *,
        source: str,
        error: Exception,
    ) -> bool:
        if not self._plugin_watchdog_enabled:
            return False
        if loaded.status != PluginStatus.ENABLED:
            return False

        now = time.monotonic()
        failures = self._plugin_failure_timestamps.setdefault(loaded.dir_name, [])
        cutoff = now - self._plugin_watchdog_failure_window_seconds
        failures[:] = [timestamp for timestamp in failures if timestamp >= cutoff]
        failures.append(now)

        if len(failures) < self._plugin_watchdog_failure_threshold:
            return False

        await self._degrade_plugin(loaded, source=source, error=error)
        return True

    async def _degrade_plugin(
        self,
        loaded: LoadedPlugin,
        *,
        source: str,
        error: Exception,
    ) -> None:
        if loaded.status != PluginStatus.ENABLED or loaded.instance is None:
            return
        if loaded.dir_name in self._plugins_degrading:
            return

        self._plugins_degrading.add(loaded.dir_name)
        loaded.status = PluginStatus.DISABLED
        loaded.error = (
            f"watchdog: disabled after {self._plugin_watchdog_failure_threshold} "
            f"failures in {self._plugin_watchdog_failure_window_seconds}s "
            f"({source}: {error})"
        )

        try:
            self._unregister_plugin_events(loaded.dir_name)
            self._cancel_periodic_tasks(loaded.dir_name, skip_current_task=True)

            if self._discord:
                self._discord.unregister_plugin(loaded.dir_name)

            try:
                await asyncio.wait_for(loaded.instance.on_disable(), timeout=5.0)
            except Exception:
                logger.exception(
                    "Error disabling plugin %s during watchdog degradation",
                    loaded.name,
                )
        finally:
            self._plugins_degrading.discard(loaded.dir_name)
            self._record_plugin_degradation(loaded.name, source, str(error))

        logger.warning("Plugin %s degraded by watchdog (%s)", loaded.name, source)

    def _record_plugin_degradation(self, plugin_name: str, source: str, detail: str) -> None:
        record: dict[str, str] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "plugin": plugin_name,
            "source": source,
            "detail": detail,
        }
        self._plugin_degradation_records.append(record)
        if len(self._plugin_degradation_records) > 1000:
            self._plugin_degradation_records = self._plugin_degradation_records[-1000:]

    def _handle_chat(self, body: str) -> None:
        logger.debug("Chat: %s", body)
        m = _CHAT_RE.match(body)
        if not m:
            return
        ids = parse_online_ids(m.group("ids"))
        event = ChatMessage(
            player_name=m.group("name"),
            steam_id=ids["steam_id"],
            eos_id=ids["eos_id"],
            channel=m.group("channel"),
            message=m.group("message"),
        )
        asyncio.get_event_loop().create_task(self._event_bus.emit(event))

    def _print_summary(self, rcon_ok: bool, rcon_detail: str, log_ok: bool = False, log_detail: str = "", discord_ok: bool = False, discord_detail: str = "", db_ok: bool = False, db_detail: str = "", api_ok: bool = False, api_detail: str = "") -> None:
        lines = [
            "",
            f"  SquadPy v{self.version}",
            "",
            "  Core Services:",
            format_service_line("RCON", rcon_ok, rcon_detail),
            format_service_line("Log Reader", log_ok, log_detail),
            format_service_line("Discord", discord_ok, discord_detail),
            format_service_line("Database", db_ok, db_detail),
            format_service_line("API", api_ok, api_detail),
            "",
        ]

        if self._loaded_plugins:
            lines.append("  Plugins:")
            for lp in self._loaded_plugins:
                lines.append(format_plugin_line(lp))
            lines.append("")

        print("\n".join(lines))

    async def stop(self) -> None:
        if not self._running:
            return
        logger.info("Shutting down...")
        self._running = False

        # Cancel log parser
        if self._log_parser_task:
            self._log_parser_task.cancel()

        for _, task in self._periodic_tasks:
            task.cancel()
        self._periodic_tasks.clear()

        for lp in self._loaded_plugins:
            self._unregister_plugin_events(lp.dir_name)
            if lp.status == PluginStatus.ENABLED and lp.instance:
                try:
                    await asyncio.wait_for(lp.instance.on_disable(), timeout=5.0)
                except Exception:
                    logger.exception("Error disabling plugin %s", lp.name)

        if self._discord:
            await self._discord.close()

        if self._api:
            await self._api.stop()

        if self._db:
            await self._db.shutdown()

        if self._rcon:
            await self._rcon.close()

        self._event_bus.clear()
        self._shutdown_event.set()
        logger.info("Shutdown complete")

    async def reload_plugin(self, plugin_name: str) -> tuple[bool, str]:
        target = None
        for lp in self._loaded_plugins:
            if lp.dir_name == plugin_name or lp.name == plugin_name:
                target = lp
                break

        if target is None:
            return False, f"Plugin '{plugin_name}' not found"

        if target.instance:
            self._cancel_periodic_tasks(target.dir_name)
            self._unregister_plugin_events(target.dir_name)
            try:
                await target.instance.on_disable()
            except Exception:
                logger.exception("Error disabling %s during reload", target.name)
            self._plugin_failure_timestamps.pop(target.dir_name, None)

            if self._discord:
                self._discord.unregister_plugin(target.dir_name)

        services = self._build_services(rcon=self._rcon, log_parser=self._log_parser)
        loader = PluginLoader(
            plugins_dir=self._plugins_dir,
            config_dir=self._plugin_config_dir,
        )
        discovered = loader.discover()
        info = next((d for d in discovered if d.dir_name == target.dir_name), None)
        if info is None:
            return False, "Plugin directory no longer exists"

        if self._db:
            try:
                await self._db.create_tables()
            except Exception:
                logger.exception("Failed to create tables after reload")

        new_loaded = await loader._load_one(info, services)
        self._plugin_failure_timestamps.pop(target.dir_name, None)

        idx = self._loaded_plugins.index(target)
        self._loaded_plugins[idx] = new_loaded

        if new_loaded.status == PluginStatus.ENABLED and new_loaded.instance:
            self._register_plugin_events(new_loaded)
            self._start_periodic_tasks(new_loaded)
            if self._discord:
                self._register_plugin_discord(new_loaded)
                try:
                    await self._discord.sync_commands()
                except Exception:
                    logger.exception("Failed to sync commands after reload")
            return True, ""

        return False, new_loaded.error
