"""Tests for one-process multi-server orchestration."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from squadpy.config import LoggingConfig, ServerConfig
from squadpy.events.types import BaseEvent, PlayerConnected
from squadpy.plugin_loader import PluginStatus
from squadpy.multi_server import (
    MultiServerRuntime,
    ServerRuntimeDefinition,
    discover_server_runtime_definitions,
)
from squadpy.server import SquadPyServer


class _FakeServer:
    def __init__(self):
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def start(self) -> None:
        self.started.set()
        await self.stopped.wait()

    async def stop(self) -> None:
        self.stopped.set()


def _definition(name: str) -> ServerRuntimeDefinition:
    return ServerRuntimeDefinition(
        name=name,
        server_config=ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
        }),
        logging_config=LoggingConfig.model_validate(
            {"level": "INFO", "file": {"enabled": False}}
        ),
        base_dir=Path("/tmp/test"),
    )


class TestMultiServerRuntime:
    def test_requires_at_least_one_server(self) -> None:
        with pytest.raises(ValueError, match="at least one server"):
            MultiServerRuntime({})

    async def test_start_and_stop_manages_all_servers(self) -> None:
        alpha = _FakeServer()
        bravo = _FakeServer()
        runtime = MultiServerRuntime({"alpha": alpha, "bravo": bravo})

        await runtime.start()
        await asyncio.wait_for(alpha.started.wait(), timeout=1.0)
        await asyncio.wait_for(bravo.started.wait(), timeout=1.0)
        assert runtime.running is True

        await runtime.stop()
        assert runtime.running is False

    async def test_wait_without_start_raises(self) -> None:
        runtime = MultiServerRuntime({"alpha": _FakeServer()})
        with pytest.raises(RuntimeError, match="has not been started"):
            await runtime.wait()

    def test_from_definitions_rejects_duplicate_names(self) -> None:
        definitions = [_definition("alpha"), _definition("alpha")]
        with pytest.raises(ValueError, match="duplicate server definition name"):
            MultiServerRuntime.from_definitions(definitions)

    async def test_isolated_contexts_prevent_cross_talk(self) -> None:
        runtime = MultiServerRuntime.from_definitions(
            [_definition("alpha"), _definition("bravo")]
        )

        alpha = cast(SquadPyServer, runtime.get_server("alpha"))
        bravo = cast(SquadPyServer, runtime.get_server("bravo"))

        seen: list[str] = []

        async def handler(event: BaseEvent) -> None:
            seen.append(event.event_name)

        alpha.event_bus.subscribe("player_connected", handler)

        await bravo.event_bus.emit(PlayerConnected())
        assert seen == []

        await alpha.event_bus.emit(PlayerConnected())
        assert seen == ["player_connected"]

    async def test_db_log_enables_in_both_contexts_in_one_process(self, tmp_path: Path) -> None:
        project_root = Path(__file__).resolve().parent.parent
        plugins_dir = project_root / "plugins"
        alpha_config_dir = tmp_path / "config" / "plugins-alpha"
        bravo_config_dir = tmp_path / "config" / "plugins-bravo"
        alpha_config_dir.mkdir(parents=True)
        bravo_config_dir.mkdir(parents=True)

        for plugin_dir in sorted(path for path in plugins_dir.iterdir() if path.is_dir()):
            if plugin_dir.name == "db_log":
                continue
            disabled_config = "enabled = false\n"
            (alpha_config_dir / f"{plugin_dir.name}.toml").write_text(disabled_config, encoding="utf-8")
            (bravo_config_dir / f"{plugin_dir.name}.toml").write_text(disabled_config, encoding="utf-8")
        (alpha_config_dir / "db_log.toml").write_text("enabled = true\n", encoding="utf-8")
        (bravo_config_dir / "db_log.toml").write_text("enabled = true\n", encoding="utf-8")

        definitions = [
            ServerRuntimeDefinition(
                name="alpha",
                server_config=ServerConfig.model_validate({
                    "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
                }),
                logging_config=LoggingConfig.model_validate(
                    {"level": "INFO", "file": {"enabled": False}}
                ),
                base_dir=project_root,
                plugins_dir=plugins_dir,
                plugin_config_dir=alpha_config_dir,
            ),
            ServerRuntimeDefinition(
                name="bravo",
                server_config=ServerConfig.model_validate({
                    "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
                }),
                logging_config=LoggingConfig.model_validate(
                    {"level": "INFO", "file": {"enabled": False}}
                ),
                base_dir=project_root,
                plugins_dir=plugins_dir,
                plugin_config_dir=bravo_config_dir,
            ),
        ]
        runtime = MultiServerRuntime.from_definitions(definitions)
        alpha = cast(SquadPyServer, runtime.get_server("alpha"))
        bravo = cast(SquadPyServer, runtime.get_server("bravo"))

        alpha._db = SimpleNamespace(
            driver="sqlite",
            sqlite_path=":memory:",
            create_tables=AsyncMock(),
            session=lambda: None,
        )
        bravo._db = SimpleNamespace(
            driver="sqlite",
            sqlite_path=":memory:",
            create_tables=AsyncMock(),
            session=lambda: None,
        )

        await alpha._load_plugins(alpha._build_services(rcon=None, log_parser=None))
        await bravo._load_plugins(bravo._build_services(rcon=None, log_parser=None))

        alpha_db_log = next(
            loaded for loaded in alpha._loaded_plugins if loaded.dir_name == "db_log"
        )
        bravo_db_log = next(
            loaded for loaded in bravo._loaded_plugins if loaded.dir_name == "db_log"
        )
        assert alpha_db_log.status == PluginStatus.ENABLED
        assert bravo_db_log.status == PluginStatus.ENABLED


class TestMultiServerDiscovery:
    def test_ignores_server_dirs_without_server_toml(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        servers_dir = config_dir / "servers"
        (servers_dir / "example-a").mkdir(parents=True)
        (servers_dir / "example-b").mkdir(parents=True)

        definitions = discover_server_runtime_definitions(tmp_path)
        assert definitions == []

    def test_discovers_only_dirs_with_server_toml(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        servers_dir = config_dir / "servers"
        (servers_dir / "example-a").mkdir(parents=True)
        target = servers_dir / "live-a"
        target.mkdir(parents=True)
        (target / "server.toml").write_text(
            '[rcon]\nhost = "127.0.0.1"\nport = 21114\npassword = "test"\n',
            encoding="utf-8",
        )

        definitions = discover_server_runtime_definitions(tmp_path)
        assert [definition.name for definition in definitions] == ["live-a"]
