"""Multi-server runtime orchestration with isolated server contexts."""

import asyncio
import logging
import signal
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from squadpy.config import (
    DatabaseConfig,
    LoggingConfig,
    ServerConfig,
    load_config,
)
from squadpy.server import SquadPyServer

logger = logging.getLogger("squadpy.multi_server")


class ManagedServer(Protocol):
    """Protocol for a server managed by the multi-server runtime."""

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...


@dataclass(frozen=True)
class ServerRuntimeDefinition:
    """Configuration for one managed server runtime instance."""

    name: str
    server_config: ServerConfig
    logging_config: LoggingConfig
    base_dir: Path
    db_config: DatabaseConfig | None = None
    plugins_dir: Path | None = None
    plugin_config_dir: Path | None = None


def discover_server_runtime_definitions(base_dir: Path) -> list[ServerRuntimeDefinition]:
    """Discover multi-server configuration definitions from config/servers/*."""
    config_dir = base_dir / "config"
    servers_dir = config_dir / "servers"
    if not servers_dir.exists():
        return []

    shared_logging = _load_optional_config(LoggingConfig, config_dir / "logging.toml")
    shared_db = _load_optional_config(DatabaseConfig, config_dir / "database.toml")
    definitions: list[ServerRuntimeDefinition] = []

    for server_dir in sorted(path for path in servers_dir.iterdir() if path.is_dir()):
        server_config = load_config(ServerConfig, server_dir / "server.toml")
        logging_config = _load_optional_config(LoggingConfig, server_dir / "logging.toml")
        db_config = _load_optional_config(DatabaseConfig, server_dir / "database.toml")

        effective_logging = (
            logging_config or shared_logging or LoggingConfig()
        ).model_copy(deep=True)
        effective_db_base = db_config or shared_db
        effective_db = effective_db_base.model_copy(deep=True) if effective_db_base else None
        plugin_config_dir = server_dir / "plugins"

        definitions.append(
            ServerRuntimeDefinition(
                name=server_dir.name,
                server_config=server_config,
                logging_config=effective_logging,
                base_dir=base_dir,
                db_config=effective_db,
                plugin_config_dir=plugin_config_dir if plugin_config_dir.exists() else None,
            )
        )

    return definitions


def _load_optional_config[T: BaseModel](model: type[T], path: Path) -> T | None:
    if not path.exists():
        return None
    return load_config(model, path)


class MultiServerRuntime:
    """Runtime manager for one-process multi-server orchestration."""

    def __init__(self, servers: Mapping[str, ManagedServer]):
        if not servers:
            raise ValueError("MultiServerRuntime requires at least one server")

        normalized_servers: dict[str, ManagedServer] = {}
        for name, server in servers.items():
            server_name = str(name).strip()
            if not server_name:
                raise ValueError("server name must be non-empty")
            normalized_servers[server_name] = server

        self._servers = normalized_servers
        self._server_tasks: dict[str, asyncio.Task[None]] = {}
        self._signal_handlers_installed = False

    @classmethod
    def from_definitions(
        cls,
        definitions: list[ServerRuntimeDefinition],
    ) -> "MultiServerRuntime":
        if not definitions:
            raise ValueError("at least one server definition is required")

        servers: dict[str, SquadPyServer] = {}
        for definition in definitions:
            server_name = definition.name.strip()
            if not server_name:
                raise ValueError("server definition name must be non-empty")
            if server_name in servers:
                raise ValueError(f"duplicate server definition name: {server_name}")

            servers[server_name] = SquadPyServer(
                server_config=definition.server_config,
                logging_config=definition.logging_config,
                base_dir=definition.base_dir,
                db_config=definition.db_config,
                manage_signals=False,
                plugins_dir=definition.plugins_dir,
                plugin_config_dir=definition.plugin_config_dir,
            )

        return cls(servers)

    @property
    def server_names(self) -> tuple[str, ...]:
        return tuple(self._servers.keys())

    @property
    def running(self) -> bool:
        return any(not task.done() for task in self._server_tasks.values())

    def get_server(self, name: str) -> ManagedServer:
        return self._servers[name]

    async def start(self) -> None:
        if self._server_tasks:
            raise RuntimeError("MultiServerRuntime has already been started")

        self._install_signal_handlers()

        for name, server in self._servers.items():
            self._server_tasks[name] = asyncio.create_task(
                server.start(),
                name=f"squadpy-server-{name}",
            )

        # Give scheduled server tasks a cycle to start.
        await asyncio.sleep(0)

    async def wait(self) -> None:
        if not self._server_tasks:
            raise RuntimeError("MultiServerRuntime has not been started")
        await asyncio.gather(*self._server_tasks.values())

    async def stop(self) -> None:
        if not self._server_tasks:
            return

        await asyncio.gather(
            *(server.stop() for server in self._servers.values()),
            return_exceptions=True,
        )
        await asyncio.gather(*self._server_tasks.values(), return_exceptions=True)
        self._server_tasks.clear()

    def _install_signal_handlers(self) -> None:
        if self._signal_handlers_installed:
            return

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._on_termination_signal)
            except (NotImplementedError, RuntimeError, ValueError):
                logger.debug("Signal handler registration unavailable for %s", sig)

        self._signal_handlers_installed = True

    def _on_termination_signal(self) -> None:
        asyncio.create_task(self.stop())
