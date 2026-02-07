"""Main server orchestrator — startup, shutdown, and lifecycle."""

import asyncio
import logging
import signal
from pathlib import Path

from squadpy.config import ServerConfig, LoggingConfig
from squadpy.events.emitter import EventBus
from squadpy.logger import setup_logging
from squadpy.plugin_loader import PluginLoader, LoadedPlugin, PluginStatus
from squadpy.log_parser import LogParser, LocalLogReader
from squadpy.rcon.client import RconClient

logger = logging.getLogger("squadpy")

VERSION = "0.1.0"


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
    ):
        self._server_config = server_config
        self._logging_config = logging_config
        self._base_dir = base_dir
        self._running = False
        self._event_bus = EventBus()
        self._rcon: RconClient | None = None
        self._loaded_plugins: list[LoadedPlugin] = []
        self._periodic_tasks: list[asyncio.Task] = []
        self._log_parser: LogParser | None = None
        self._log_parser_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    @property
    def version(self) -> str:
        return VERSION

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._running = True

        log_dir = self._base_dir / self._logging_config.file.path
        setup_logging(self._logging_config, log_dir if self._logging_config.file.enabled else None)

        # Connect RCON
        rcon_ok = False
        rcon_detail = ""
        try:
            self._rcon = RconClient(
                host=self._server_config.rcon.host,
                port=self._server_config.rcon.port,
                password=self._server_config.rcon.password,
            )
            await self._rcon.connect()
            self._rcon.on_chat = self._handle_chat
            rcon_ok = True
            rcon_detail = f"connected ({self._server_config.rcon.host}:{self._server_config.rcon.port})"
        except Exception as e:
            rcon_detail = str(e)
            logger.error("RCON connection failed: %s", e)

        # Start log reader (if configured)
        log_ok = False
        log_detail = ""
        if self._server_config.log.enabled:
            try:
                if self._server_config.log.mode == "local":
                    reader = LocalLogReader(
                        self._server_config.log.path,
                        poll_interval=self._server_config.log.poll_interval,
                    )
                else:
                    raise NotImplementedError("SFTP log reader not yet implemented")
                self._log_parser = LogParser(reader=reader, event_bus=self._event_bus)
                self._log_parser_task = asyncio.create_task(self._log_parser.run())
                log_ok = True
                log_detail = f"tailing ({self._server_config.log.mode})"
            except Exception as e:
                log_detail = str(e)
                logger.error("Log reader failed: %s", e)
        else:
            log_detail = "not configured"

        # Load plugins
        services = {
            "rcon": self._rcon if rcon_ok else None,
            "log_reader": self._log_parser if log_ok else None,
            "discord": None,
            "db": None,
            "server": self,
        }

        plugin_loader = PluginLoader(
            plugins_dir=self._base_dir / "plugins",
            config_dir=self._base_dir / "config" / "plugins",
        )
        self._loaded_plugins = await plugin_loader.load_all(services)

        for lp in self._loaded_plugins:
            if lp.status == PluginStatus.ENABLED and lp.instance:
                self._register_plugin_events(lp)
                self._start_periodic_tasks(lp)

        self._print_summary(rcon_ok, rcon_detail, log_ok, log_detail)

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        await self._shutdown_event.wait()

    def _register_plugin_events(self, loaded: LoadedPlugin) -> None:
        for event_name, method_name in loaded.event_handlers:
            handler = getattr(loaded.instance, method_name)
            self._event_bus.subscribe(event_name, handler)

    def _start_periodic_tasks(self, loaded: LoadedPlugin) -> None:
        for method_name, interval in loaded.periodic_tasks:
            method = getattr(loaded.instance, method_name)
            task = asyncio.create_task(
                self._run_periodic(loaded.name, method, interval)
            )
            self._periodic_tasks.append(task)

    async def _run_periodic(self, plugin_name: str, method, interval: float) -> None:
        while self._running:
            await asyncio.sleep(interval)
            try:
                await method()
            except Exception:
                logger.exception("Error in periodic task %s.%s", plugin_name, method.__name__)

    def _handle_chat(self, body: str) -> None:
        logger.debug("Chat: %s", body)

    def _print_summary(self, rcon_ok: bool, rcon_detail: str, log_ok: bool = False, log_detail: str = "") -> None:
        lines = [
            "",
            f"  SquadPy v{self.version}",
            "",
            "  Core Services:",
            format_service_line("RCON", rcon_ok, rcon_detail),
            format_service_line("Log Reader", log_ok, log_detail),
            format_service_line("Discord", False, "not configured (Phase 3)"),
            format_service_line("Database", False, "not configured (Phase 4)"),
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

        for task in self._periodic_tasks:
            task.cancel()

        for lp in self._loaded_plugins:
            if lp.status == PluginStatus.ENABLED and lp.instance:
                try:
                    await asyncio.wait_for(lp.instance.on_disable(), timeout=5.0)
                except Exception:
                    logger.exception("Error disabling plugin %s", lp.name)

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
            try:
                await target.instance.on_disable()
            except Exception:
                logger.exception("Error disabling %s during reload", target.name)

            for event_name, method_name in target.event_handlers:
                handler = getattr(target.instance, method_name)
                self._event_bus.unsubscribe(event_name, handler)

        services = {
            "rcon": self._rcon,
            "log_reader": self._log_parser,
            "discord": None,
            "db": None,
            "server": self,
        }
        loader = PluginLoader(
            plugins_dir=self._base_dir / "plugins",
            config_dir=self._base_dir / "config" / "plugins",
        )
        discovered = loader.discover()
        info = next((d for d in discovered if d.dir_name == target.dir_name), None)
        if info is None:
            return False, "Plugin directory no longer exists"

        new_loaded = await loader._load_one(info, services)

        idx = self._loaded_plugins.index(target)
        self._loaded_plugins[idx] = new_loaded

        if new_loaded.status == PluginStatus.ENABLED and new_loaded.instance:
            self._register_plugin_events(new_loaded)
            self._start_periodic_tasks(new_loaded)
            return True, ""

        return False, new_loaded.error
