"""Tests for authenticated REST control endpoints."""

from unittest.mock import AsyncMock

from squadpy.api.websocket_control import WebsocketControlService
from squadpy.layers import LayerCatalog
from squadpy.observability import get_trace_recorder
from squadpy.plugin_loader import LoadedPlugin, PluginStatus


class TestRestControlEndpoints:
    async def test_health_requires_auth(self):
        service = WebsocketControlService(token="secret_token")
        response = await service.process_health(token="bad_token")
        assert response["ok"] is False
        assert response["code"] == "unauthorized"

    async def test_health_returns_ok_when_authorized(self):
        service = WebsocketControlService(token="secret_token")
        response = await service.process_health(token="secret_token")
        assert response["ok"] is True
        assert response["result"]["status"] == "ok"
        assert response["result"]["ready"] is True

    async def test_health_reports_degraded_when_required_dependency_is_unhealthy(self):
        server = AsyncMock()
        server.running = True
        rcon = AsyncMock()
        rcon.connected = False
        service = WebsocketControlService(
            token="secret_token",
            server=server,
            rcon=rcon,
        )

        response = await service.process_health(token="secret_token")

        assert response["ok"] is True
        assert response["result"]["status"] == "degraded"
        assert response["result"]["ready"] is False
        assert response["result"]["dependencies"]["rcon"]["healthy"] is False

    async def test_status_endpoint_reports_rcon_and_server_state(self):
        server = AsyncMock()
        server.running = True
        rcon = AsyncMock()
        rcon.connected = True
        service = WebsocketControlService(
            token="secret_token",
            server=server,
            rcon=rcon,
        )

        response = await service.process_status(token="secret_token")

        assert response["ok"] is True
        assert response["result"]["service"] == "control_api"
        assert response["result"]["rcon_connected"] is True
        assert response["result"]["server_running"] is True
        assert response["result"]["ready"] is True

    async def test_readiness_returns_unavailable_when_required_dependency_is_unhealthy(self):
        server = AsyncMock()
        server.running = True
        rcon = AsyncMock()
        rcon.connected = False
        service = WebsocketControlService(
            token="secret_token",
            server=server,
            rcon=rcon,
        )

        response = await service.process_readiness(token="secret_token")

        assert response["ok"] is False
        assert response["code"] == "unavailable"
        assert response["result"]["status"] == "not_ready"
        assert response["result"]["ready"] is False
        assert response["result"]["dependencies"]["rcon"]["healthy"] is False
        assert service._http_status(response) == 503

    async def test_readiness_returns_ready_when_required_dependencies_are_healthy(self):
        server = AsyncMock()
        server.running = True
        rcon = AsyncMock()
        rcon.connected = True
        service = WebsocketControlService(
            token="secret_token",
            server=server,
            rcon=rcon,
        )

        response = await service.process_readiness(token="secret_token")

        assert response["ok"] is True
        assert response["result"]["status"] == "ready"
        assert response["result"]["ready"] is True

    async def test_metrics_requires_auth(self):
        service = WebsocketControlService(token="secret_token")
        response = await service.process_metrics(token="bad_token")
        assert response["ok"] is False
        assert response["code"] == "unauthorized"

    async def test_metrics_exposes_runtime_and_plugin_series(self):
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
            token="secret_token",
            server=FakeServer(),
            rcon=rcon,
        )

        response = await service.process_metrics(token="secret_token")

        assert response["ok"] is True
        metrics = response["result"]["metrics"]
        assert "squadpy_runtime_server_running 1" in metrics
        assert "squadpy_runtime_rcon_connected 1" in metrics
        assert "squadpy_runtime_plugins_loaded 2" in metrics
        assert 'squadpy_plugins_total{status="enabled"} 1' in metrics
        assert 'squadpy_plugins_total{status="failed"} 1' in metrics
        assert 'squadpy_plugin_status{plugin="auto_kick_unassigned",status="enabled"} 1' in metrics
        assert 'squadpy_plugin_status{plugin="db_log",status="failed"} 1' in metrics

    async def test_traces_requires_auth(self):
        service = WebsocketControlService(token="secret_token")
        response = await service.process_traces(token="bad_token")
        assert response["ok"] is False
        assert response["code"] == "unauthorized"

    async def test_traces_returns_recent_spans(self):
        recorder = get_trace_recorder()
        recorder.clear()
        recorder.record_span(
            name="rcon.execute",
            started_at_epoch_ms=1708040000000,
            duration_ms=12.0,
            status="ok",
            attributes={"command": "ListPlayers"},
        )
        recorder.record_span(
            name="log_parser.process_line",
            started_at_epoch_ms=1708040000100,
            duration_ms=1.7,
            status="ok",
            attributes={"matched": True},
        )

        service = WebsocketControlService(token="secret_token")
        response = await service.process_traces(token="secret_token")

        assert response["ok"] is True
        assert response["result"]["summary"]["total"] >= 2
        span_names = [span["name"] for span in response["result"]["spans"]]
        assert "rcon.execute" in span_names
        assert "log_parser.process_line" in span_names

    async def test_command_endpoint_dispatches_when_authorized(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
        )

        response = await service.process_command(
            {"request_id": "r1", "command": "ShowCurrentMap"},
            token="secret_token",
        )

        rcon.execute.assert_awaited_once_with("ShowCurrentMap")
        assert response["ok"] is True
        assert response["request_id"] == "r1"
        assert response["result"]["response"] == "ACK"

    async def test_layer_query_endpoint_returns_catalog_results_when_authorized(self):
        class FakeLayerService:
            def __init__(self):
                self.source_url = "https://example.test/layers.json"
                self.catalog = LayerCatalog(
                    layers=frozenset({"Narva_RAAS_v1"}),
                    factions=frozenset({"USA"}),
                    vehicles_by_class={"HELICOPTER": frozenset({"MI8 Transport"})},
                    melee_weapons=frozenset({"BP_Knife_Combat_C"}),
                )

            def health(self):
                return {"status": "healthy"}

        service = WebsocketControlService(
            token="secret_token",
            layer_catalog_service=FakeLayerService(),
        )

        response = await service.process_layer_query(
            {
                "request_id": "layers-1",
                "query": {
                    "layer": "narva_raas_v1",
                    "faction": "usa",
                    "vehicle_class": "helicopter",
                },
            },
            token="secret_token",
        )

        assert response["ok"] is True
        assert response["request_id"] == "layers-1"
        assert response["result"]["has_layer"] is True
        assert response["result"]["has_faction"] is True
        assert response["result"]["vehicle_names"] == ["MI8 Transport"]
        assert response["result"]["health"]["status"] == "healthy"

    async def test_rbac_denies_layer_query_for_role_without_permission(self):
        class FakeLayerService:
            catalog = LayerCatalog(
                layers=frozenset({"Narva_RAAS_v1"}),
                factions=frozenset({"USA"}),
            )

            @staticmethod
            def health():
                return {"status": "healthy"}

        service = WebsocketControlService(
            token="secret_token",
            layer_catalog_service=FakeLayerService(),
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.status"],
                "admin": ["*"],
            },
        )

        response = await service.process_layer_query(
            {
                "request_id": "layers-deny",
                "query": {"layer": "narva_raas_v1"},
            },
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is False
        assert response["code"] == "forbidden"
        assert service._http_status(response) == 403

    async def test_rbac_denies_status_for_role_without_permission(self):
        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health"],
                "admin": ["*"],
            },
        )

        response = await service.process_status_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is False
        assert response["code"] == "forbidden"
        assert service._http_status(response) == 403

    async def test_rbac_denies_readiness_for_role_without_permission(self):
        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.status"],
                "admin": ["*"],
            },
        )

        response = await service.process_readiness_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is False
        assert response["code"] == "forbidden"
        assert service._http_status(response) == 403

    async def test_rbac_allows_readiness_for_role_with_permission(self):
        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.readiness", "control.status"],
            },
        )

        response = await service.process_readiness_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is True
        assert response["result"]["status"] == "ready"

    async def test_rbac_denies_metrics_for_role_without_permission(self):
        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.status"],
                "admin": ["*"],
            },
        )

        response = await service.process_metrics_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is False
        assert response["code"] == "forbidden"
        assert service._http_status(response) == 403

    async def test_rbac_allows_metrics_for_role_with_permission(self):
        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.metrics", "control.status"],
            },
        )

        response = await service.process_metrics_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is True
        assert "squadpy_runtime_ready" in response["result"]["metrics"]

    async def test_rbac_denies_traces_for_role_without_permission(self):
        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.status"],
                "admin": ["*"],
            },
        )

        response = await service.process_traces_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is False
        assert response["code"] == "forbidden"
        assert service._http_status(response) == 403

    async def test_rbac_allows_traces_for_role_with_permission(self):
        recorder = get_trace_recorder()
        recorder.clear()
        recorder.record_span(
            name="rcon.execute",
            started_at_epoch_ms=1708040000000,
            duration_ms=9.0,
            status="ok",
            attributes={"command": "ListPlayers"},
        )

        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.traces"],
            },
        )

        response = await service.process_traces_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is True
        assert response["result"]["summary"]["total"] >= 1

    async def test_rbac_allows_status_for_role_with_permission(self):
        service = WebsocketControlService(
            token="secret_token",
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.status"],
            },
        )

        response = await service.process_status_with_role(
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is True
        assert response["result"]["service"] == "control_api"

    def test_routes_include_health_status_and_command(self):
        service = WebsocketControlService(token="secret_token")
        app = service._build_app()
        paths: set[str] = set()
        for route in app.router.routes():
            resource = route.resource
            if resource is None:
                continue
            canonical = getattr(resource, "canonical", "")
            if canonical:
                paths.add(canonical)
        assert "/metrics" in paths
        assert "/api/health" in paths
        assert "/api/readiness" in paths
        assert "/api/traces" in paths
        assert "/api/status" in paths
        assert "/api/command" in paths
        assert "/api/layers/query" in paths
        assert "/api/webhook/command" in paths
