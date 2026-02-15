"""Tests for websocket control service authentication and dispatch."""

from unittest.mock import AsyncMock

from squadpy.api.websocket_control import WebsocketControlService
from squadpy.layers import LayerCatalog


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

    async def test_rbac_denies_rcon_execute_for_disallowed_role(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="OK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.status"],
                "admin": ["*"],
            },
        )

        response = await service.process_payload(
            {"request_id": "rbac-deny", "action": "rcon.execute", "command": "ListPlayers"},
            token="secret_token",
            role="observer",
        )

        rcon.execute.assert_not_awaited()
        assert response["ok"] is False
        assert response["request_id"] == "rbac-deny"
        assert response["code"] == "forbidden"

    async def test_rbac_allows_rcon_execute_for_permitted_role(self):
        rcon = AsyncMock()
        rcon.execute = AsyncMock(return_value="OK")
        service = WebsocketControlService(
            token="secret_token",
            rcon=rcon,
            rbac_enabled=True,
            rbac_default_role="observer",
            rbac_role_permissions={
                "observer": ["control.health", "control.status"],
                "admin": ["rcon.execute"],
            },
        )

        response = await service.process_payload(
            {"request_id": "rbac-allow", "action": "rcon.execute", "command": "ListPlayers"},
            token="secret_token",
            role="admin",
        )

        rcon.execute.assert_awaited_once_with("ListPlayers")
        assert response["ok"] is True
        assert response["request_id"] == "rbac-allow"

    async def test_dispatches_layer_query_when_authorized(self):
        class FakeLayerService:
            catalog = LayerCatalog(
                layers=frozenset({"Gorodok_RAAS_v1"}),
                factions=frozenset({"RGF"}),
                vehicles_by_class={"HELICOPTER": frozenset({"MI8 Transport"})},
            )

            @staticmethod
            def health():
                return {"status": "healthy"}

        service = WebsocketControlService(
            token="secret_token",
            layer_catalog_service=FakeLayerService(),
        )

        response = await service.process_payload(
            {
                "request_id": "layers-ws",
                "action": "layers.query",
                "query": {
                    "layer": "gorodok_raas_v1",
                    "faction": "rgf",
                    "vehicle_class": "helicopter",
                },
            },
            token="secret_token",
        )

        assert response["ok"] is True
        assert response["request_id"] == "layers-ws"
        assert response["result"]["has_layer"] is True
        assert response["result"]["has_faction"] is True
        assert response["result"]["vehicle_names"] == ["MI8 Transport"]
        assert response["result"]["health"]["status"] == "healthy"

    async def test_rbac_denies_layer_query_for_disallowed_role(self):
        class FakeLayerService:
            catalog = LayerCatalog(layers=frozenset({"Gorodok_RAAS_v1"}))

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
                "admin": ["layers.query"],
            },
        )

        response = await service.process_payload(
            {
                "request_id": "layers-ws-deny",
                "action": "layers.query",
                "query": {"layer": "gorodok_raas_v1"},
            },
            token="secret_token",
            role="observer",
        )

        assert response["ok"] is False
        assert response["request_id"] == "layers-ws-deny"
        assert response["code"] == "forbidden"
