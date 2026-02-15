"""Contract tests for Prometheus metrics exporter output."""

from unittest.mock import AsyncMock

import pytest

from squadpy.api.websocket_control import WebsocketControlService
from squadpy.plugin_loader import LoadedPlugin, PluginStatus

pytestmark = [pytest.mark.contract, pytest.mark.api_security]


async def test_metrics_export_includes_runtime_and_plugin_series() -> None:
    """P2-BEYOND-003: runtime and plugin metrics are exported in Prometheus format."""

    class FakeServer:
        def __init__(self) -> None:
            self.running = True
            self._loaded_plugins = [
                LoadedPlugin(name="Auto Kick", dir_name="auto_kick_unassigned", status=PluginStatus.ENABLED),
                LoadedPlugin(name="Db Log", dir_name="db_log", status=PluginStatus.FAILED),
            ]
            self._periodic_tasks = [("auto_kick_unassigned", AsyncMock())]

    rcon = AsyncMock()
    rcon.connected = True
    service = WebsocketControlService(
        token="control_token",
        server=FakeServer(),
        rcon=rcon,
    )

    response = await service.process_metrics(token="control_token")

    assert response["ok"] is True
    metrics = response["result"]["metrics"]
    assert "squadpy_runtime_server_running 1" in metrics
    assert "squadpy_runtime_rcon_connected 1" in metrics
    assert "squadpy_runtime_plugins_loaded 2" in metrics
    assert 'squadpy_plugins_total{status="enabled"} 1' in metrics
    assert 'squadpy_plugins_total{status="failed"} 1' in metrics
    assert 'squadpy_plugin_status{plugin="auto_kick_unassigned",status="enabled"} 1' in metrics
    assert 'squadpy_plugin_status{plugin="db_log",status="failed"} 1' in metrics
