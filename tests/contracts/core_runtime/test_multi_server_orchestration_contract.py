"""Contract test for one-process multi-server context isolation."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from squadpy.config import LoggingConfig, ServerConfig
from squadpy.events.types import BaseEvent, PlayerConnected
from squadpy.multi_server import (
    MultiServerRuntime,
    ServerRuntimeDefinition,
    discover_server_runtime_definitions,
)
from squadpy.plugin_loader import PluginStatus
from squadpy.rcon.client import RconClient
from squadpy.rcon.protocol import PacketType, RconPacket
from squadpy.server import SquadPyServer

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]


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


async def test_multi_server_contexts_are_isolated() -> None:
    """P2-BEYOND-001: contexts run side-by-side without event cross-talk."""
    runtime = MultiServerRuntime.from_definitions(
        [_definition("alpha"), _definition("bravo")]
    )
    alpha = cast(SquadPyServer, runtime.get_server("alpha"))
    bravo = cast(SquadPyServer, runtime.get_server("bravo"))

    alpha_seen: list[str] = []
    bravo_seen: list[str] = []

    async def on_alpha(event: BaseEvent) -> None:
        alpha_seen.append(event.event_name)

    async def on_bravo(event: BaseEvent) -> None:
        bravo_seen.append(event.event_name)

    alpha.event_bus.subscribe("player_connected", on_alpha)
    bravo.event_bus.subscribe("player_connected", on_bravo)

    await alpha.event_bus.emit(PlayerConnected())
    await bravo.event_bus.emit(PlayerConnected())

    assert alpha_seen == ["player_connected"]
    assert bravo_seen == ["player_connected"]


def test_multi_server_discovery_prefers_per_server_db_and_falls_back_to_shared(
    tmp_path: Path,
) -> None:
    """P2-BEYOND-001: each context resolves DB config independently."""
    config_dir = tmp_path / "config"
    servers_dir = config_dir / "servers"
    alpha_dir = servers_dir / "alpha"
    bravo_dir = servers_dir / "bravo"
    alpha_dir.mkdir(parents=True)
    bravo_dir.mkdir(parents=True)

    server_toml = '[rcon]\nhost = "127.0.0.1"\nport = 21114\npassword = "test"\n'
    (alpha_dir / "server.toml").write_text(server_toml, encoding="utf-8")
    (bravo_dir / "server.toml").write_text(server_toml, encoding="utf-8")

    (config_dir / "database.toml").write_text(
        'enabled = true\ndriver = "sqlite"\npath = "data/shared.db"\n',
        encoding="utf-8",
    )
    (alpha_dir / "database.toml").write_text(
        'enabled = true\ndriver = "sqlite"\npath = "data/alpha.db"\n',
        encoding="utf-8",
    )

    definitions = discover_server_runtime_definitions(tmp_path)
    by_name = {definition.name: definition for definition in definitions}

    assert sorted(by_name.keys()) == ["alpha", "bravo"]
    assert by_name["alpha"].db_config is not None
    assert by_name["alpha"].db_config.path == "data/alpha.db"
    assert by_name["bravo"].db_config is not None
    assert by_name["bravo"].db_config.path == "data/shared.db"


async def test_multi_server_loads_real_db_log_in_both_contexts(tmp_path: Path) -> None:
    """P2-BEYOND-001: real db_log plugin enables in both contexts in one process."""
    project_root = Path(__file__).resolve().parents[3]
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

    runtime = MultiServerRuntime.from_definitions([
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
    ])

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


async def test_multi_server_single_context_rcon_drop_and_recovery_is_isolated() -> None:
    """P2-BEYOND-001: one context can drop/recover RCON without blocking siblings."""
    runtime = MultiServerRuntime.from_definitions(
        [_definition("alpha"), _definition("bravo")]
    )
    alpha = cast(SquadPyServer, runtime.get_server("alpha"))
    bravo = cast(SquadPyServer, runtime.get_server("bravo"))

    alpha_client = RconClient(
        host="127.0.0.1",
        port=21114,
        password="test",
        auto_reconnect=True,
    )
    alpha_client._connected = True
    alpha_client._reconnecting = False
    alpha_client._reconnect_event.set()
    alpha_client._writer = AsyncMock()
    alpha_client._writer.write = Mock()
    alpha_client._writer.drain = AsyncMock()

    bravo_client = RconClient(
        host="127.0.0.1",
        port=21115,
        password="test",
        auto_reconnect=True,
    )
    bravo_client._connected = False
    bravo_client._reconnecting = True
    bravo_client._reconnect_event.clear()
    bravo_client._writer = AsyncMock()
    bravo_client._writer.write = Mock()
    bravo_client._writer.drain = AsyncMock()

    alpha._rcon = alpha_client
    bravo._rcon = bravo_client

    bravo_task = asyncio.create_task(bravo._rcon.execute("ListPlayers"))
    await asyncio.sleep(0)
    assert not bravo_task.done()

    alpha_task = asyncio.create_task(alpha._rcon.execute("ListPlayers"))
    await asyncio.sleep(0)
    alpha_request_id = alpha_client._packet_id_counter
    alpha_client._handle_response_packet(
        RconPacket(id=alpha_request_id, type=PacketType.RESPONSE_VALUE, body="alpha-ok")
    )
    alpha_client._handle_response_packet(
        RconPacket(id=alpha_request_id, type=PacketType.RESPONSE_VALUE, body="")
    )
    assert await alpha_task == "alpha-ok"
    assert not bravo_task.done()
    alpha_client._writer.write.assert_called_once()
    alpha_client._writer.drain.assert_awaited_once()

    bravo_client._connected = True
    bravo_client._reconnecting = False
    bravo_client._reconnect_event.set()
    await asyncio.sleep(0)
    bravo_request_id = bravo_client._packet_id_counter
    bravo_client._handle_response_packet(
        RconPacket(id=bravo_request_id, type=PacketType.RESPONSE_VALUE, body="bravo-ok")
    )
    bravo_client._handle_response_packet(
        RconPacket(id=bravo_request_id, type=PacketType.RESPONSE_VALUE, body="")
    )
    assert await bravo_task == "bravo-ok"
    bravo_client._writer.write.assert_called_once()
    bravo_client._writer.drain.assert_awaited_once()
    assert alpha_client.connected is True
