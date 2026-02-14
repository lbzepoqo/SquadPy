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

    def test_routes_include_health_status_and_command(self):
        service = WebsocketControlService(token="secret_token")
        app = service._build_app()
        paths = {route.resource.canonical for route in app.router.routes()}
        assert "/api/health" in paths
        assert "/api/status" in paths
        assert "/api/command" in paths
