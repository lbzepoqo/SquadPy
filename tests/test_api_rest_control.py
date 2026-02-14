"""Tests for authenticated REST control endpoints."""

from unittest.mock import AsyncMock

from squadpy.api.websocket_control import WebsocketControlService


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
        assert "/api/health" in paths
        assert "/api/status" in paths
        assert "/api/command" in paths
        assert "/api/webhook/command" in paths
