"""Tests for webhook signature verification and dispatch."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock

from squadpy.api.websocket_control import WebsocketControlService


def _sign(secret: str, timestamp: str, raw_body: str) -> str:
    payload = f"{timestamp}.{raw_body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


class TestWebhookSignaturePolicy:
    async def test_valid_signature_dispatches_command(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            webhook_signing_enabled=True,
            webhook_signing_secret="webhook_secret",
        )
        payload = {"request_id": "wh-1", "command": "ListPlayers", "actor": "webhook_actor"}
        raw_body = json.dumps(payload, separators=(",", ":"))
        timestamp = "1700000000"
        signature = _sign("webhook_secret", timestamp, raw_body)
        service._epoch_seconds = lambda: 1700000000  # type: ignore[assignment]

        response = await service.process_webhook_command(
            payload,
            raw_body=raw_body,
            signature=f"sha256={signature}",
            timestamp=timestamp,
            actor="webhook_actor",
        )

        rcon.execute.assert_awaited_once_with("ListPlayers")
        assert response["ok"] is True
        assert response["request_id"] == "wh-1"
        assert response["result"]["response"] == "ACK"

    async def test_invalid_signature_is_rejected(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            webhook_signing_enabled=True,
            webhook_signing_secret="webhook_secret",
        )
        payload = {"request_id": "wh-2", "command": "ListPlayers"}
        raw_body = json.dumps(payload, separators=(",", ":"))
        service._epoch_seconds = lambda: 1700000000  # type: ignore[assignment]

        response = await service.process_webhook_command(
            payload,
            raw_body=raw_body,
            signature="sha256=invalid",
            timestamp="1700000000",
        )

        rcon.execute.assert_not_awaited()
        assert response["ok"] is False
        assert response["request_id"] == "wh-2"
        assert response["code"] == "invalid_signature"
        assert service._http_status(response) == 401

    async def test_stale_timestamp_is_rejected(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            webhook_signing_enabled=True,
            webhook_signing_secret="webhook_secret",
            webhook_max_age_seconds=60,
        )
        payload = {"request_id": "wh-3", "command": "ListPlayers"}
        raw_body = json.dumps(payload, separators=(",", ":"))
        timestamp = "1700000000"
        signature = _sign("webhook_secret", timestamp, raw_body)
        service._epoch_seconds = lambda: 1700000200  # type: ignore[assignment]

        response = await service.process_webhook_command(
            payload,
            raw_body=raw_body,
            signature=signature,
            timestamp=timestamp,
        )

        rcon.execute.assert_not_awaited()
        assert response["ok"] is False
        assert response["request_id"] == "wh-3"
        assert response["code"] == "invalid_signature"

    async def test_disabled_policy_returns_unavailable(self):
        rcon = AsyncMock()
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            webhook_signing_enabled=False,
            webhook_signing_secret="",
        )
        payload = {"request_id": "wh-4", "command": "ListPlayers"}

        response = await service.process_webhook_command(
            payload,
            raw_body=json.dumps(payload),
            signature="sha256=unused",
            timestamp="1700000000",
        )

        assert response["ok"] is False
        assert response["request_id"] == "wh-4"
        assert response["code"] == "unavailable"
