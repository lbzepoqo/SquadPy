"""Tests for websocket control service authentication and dispatch."""

from unittest.mock import AsyncMock

from squadpy.api.websocket_control import WebsocketControlService


class TestWebsocketControlService:
    async def test_dispatches_rcon_execute_when_authorized(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="OK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
        )

        response = await service.process_payload(
            {"request_id": "abc", "action": "rcon.execute", "command": "ListPlayers"},
            token="secret_token",
        )

        rcon.execute.assert_awaited_once_with("ListPlayers")
        assert response["ok"] is True
        assert response["request_id"] == "abc"
        assert response["result"]["response"] == "OK"

    async def test_rejects_unauthorized_dispatch(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="OK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
        )

        response = await service.process_payload(
            {"request_id": "x1", "action": "rcon.execute", "command": "ListPlayers"},
            token="bad_token",
        )

        rcon.execute.assert_not_awaited()
        assert response["ok"] is False
        assert response["request_id"] == "x1"
        assert response["code"] == "unauthorized"

    async def test_missing_command_is_invalid_request(self):
        rcon = AsyncMock()
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
        )
        response = await service.process_payload(
            {"action": "rcon.execute"},
            token="secret_token",
        )
        assert response["ok"] is False
        assert response["code"] == "invalid_request"

    async def test_unknown_action_rejected(self):
        rcon = AsyncMock()
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
        )
        response = await service.process_payload(
            {"action": "unknown.action"},
            token="secret_token",
        )
        assert response["ok"] is False
        assert response["code"] == "unknown_action"
