"""Tests for control API audit record behavior."""

import json
from unittest.mock import AsyncMock

from squadpy.api.websocket_control import WebsocketControlService


class TestControlApiAudit:
    async def test_audit_records_successful_command(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
        )

        await service.process_command(
            {"command": "ListPlayers"},
            token="secret_token",
            origin="rest",
            actor="admin_user",
        )

        records = service.recent_audit_records()
        assert records
        latest = records[-1]
        assert latest["actor"] == "admin_user"
        assert latest["origin"] == "rest"
        assert latest["target"] == "ListPlayers"
        assert latest["outcome"] == "success"

    async def test_audit_records_rejected_command(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
        )

        await service.process_command(
            {"command": "ListPlayers"},
            token="wrong_token",
            origin="rest",
            actor="unknown_actor",
        )

        records = service.recent_audit_records()
        assert records
        latest = records[-1]
        assert latest["actor"] == "unknown_actor"
        assert latest["origin"] == "rest"
        assert latest["target"] == "rcon.execute"
        assert latest["outcome"] == "rejected"
        assert latest["detail"] == "unauthorized"

    async def test_audit_records_forbidden_role_command(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health"],
                "admin": ["*"],
            },
        )

        await service.process_command(
            {"command": "ListPlayers"},
            token="secret_token",
            origin="rest",
            actor="observer_user",
            role="observer",
        )

        records = service.recent_audit_records()
        assert records
        latest = records[-1]
        assert latest["actor"] == "observer_user"
        assert latest["origin"] == "rest"
        assert latest["target"] == "rcon.execute"
        assert latest["outcome"] == "rejected"
        assert latest["detail"] == "forbidden role=observer permission=rcon.execute"

    async def test_audit_records_invalid_webhook_signature(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="ACK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            webhook_signing_enabled=True,
            webhook_signing_secret="webhook_secret",
        )
        payload = {"request_id": "wh-audit", "command": "ListPlayers", "actor": "webhook_actor"}
        raw_body = json.dumps(payload, separators=(",", ":"))
        timestamp = "1700000000"
        service._epoch_seconds = lambda: 1700000000  # type: ignore[assignment]

        await service.process_webhook_command(
            payload,
            raw_body=raw_body,
            signature="sha256=not_valid",
            timestamp=timestamp,
            actor="webhook_actor",
        )

        records = service.recent_audit_records()
        assert records
        latest = records[-1]
        assert latest["actor"] == "webhook_actor"
        assert latest["origin"] == "webhook"
        assert latest["target"] == "webhook.command"
        assert latest["outcome"] == "rejected"
        assert latest["detail"] == "invalid signature"
