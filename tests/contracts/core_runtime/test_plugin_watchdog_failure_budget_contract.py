"""Contract test for plugin watchdog failure budget degradation."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.config import LoggingConfig, ServerConfig
from squadpy.events.types import PlayerConnected
from squadpy.plugin_loader import LoadedPlugin, PluginStatus
from squadpy.server import SquadPyServer

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]


async def test_plugin_watchdog_contract_degrades_after_repeated_failures() -> None:
    """P2-BEYOND-006: repeated plugin failures trigger controlled degradation."""
    server = SquadPyServer(
        server_config=ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
            "plugin_watchdog": {
                "enabled": True,
                "failure_threshold": 2,
                "failure_window_seconds": 60,
            },
        }),
        logging_config=LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}}),
        base_dir=Path("/tmp/test"),
    )

    plugin_instance = AsyncMock()
    plugin_instance.handle_player_connected = AsyncMock(
        side_effect=[RuntimeError("boom-1"), RuntimeError("boom-2")]
    )
    plugin_instance.on_disable = AsyncMock()

    loaded = LoadedPlugin(
        name="Watchdog Contract Plugin",
        dir_name="watchdog_contract_plugin",
        status=PluginStatus.ENABLED,
        instance=plugin_instance,
        event_handlers=[("player_connected", "handle_player_connected")],
    )
    server._loaded_plugins = [loaded]
    server._register_plugin_events(loaded)

    await server.event_bus.emit(PlayerConnected())
    await server.event_bus.emit(PlayerConnected())

    assert loaded.status == PluginStatus.DISABLED
    assert "watchdog: disabled after 2 failures" in loaded.error
    plugin_instance.on_disable.assert_awaited_once()
