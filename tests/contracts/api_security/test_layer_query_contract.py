"""Contract tests for authenticated layer catalog query access."""

import pytest

from squadpy.api.websocket_control import WebsocketControlService
from squadpy.layers import LayerCatalog

pytestmark = [pytest.mark.contract, pytest.mark.api_security]


class _FakeLayerService:
    source_url = "https://example.test/layers.json"
    catalog = LayerCatalog(
        layers=frozenset({"Narva_RAAS_v1"}),
        factions=frozenset({"USA"}),
        vehicles_by_class={"HELICOPTER": frozenset({"MI8 Transport"})},
    )

    @staticmethod
    def health() -> dict[str, str]:
        return {"status": "healthy"}


async def test_authenticated_layer_query_contract() -> None:
    """P2-LAYER-005: authorized callers can query shared layer metadata."""
    service = WebsocketControlService(
        token="control_token",
        layer_catalog_service=_FakeLayerService(),
    )

    response = await service.process_layer_query(
        {
            "request_id": "layer-q-1",
            "query": {"layer": "narva_raas_v1", "faction": "usa", "vehicle_class": "helicopter"},
        },
        token="control_token",
    )

    assert response["ok"] is True
    assert response["request_id"] == "layer-q-1"
    assert response["result"]["has_layer"] is True
    assert response["result"]["has_faction"] is True
    assert response["result"]["vehicle_names"] == ["MI8 Transport"]


async def test_layer_query_forbidden_contract() -> None:
    """P2-LAYER-005: role without layers.query permission is denied."""
    service = WebsocketControlService(
        token="control_token",
        layer_catalog_service=_FakeLayerService(),
        rbac_enabled=True,
        rbac_default_role="observer",
        rbac_role_permissions={
            "observer": ["control.health", "control.status"],
            "admin": ["*"],
        },
    )

    response = await service.process_layer_query(
        {
            "request_id": "layer-q-2",
            "query": {"layer": "narva_raas_v1"},
        },
        token="control_token",
        role="observer",
    )

    assert response["ok"] is False
    assert response["request_id"] == "layer-q-2"
    assert response["code"] == "forbidden"
