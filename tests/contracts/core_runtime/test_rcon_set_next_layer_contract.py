"""Contract tests for the P0 set-next-layer helper command surface."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.client import RconClient

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p0]

SET_NEXT_LAYER_REQUEST_TEMPLATE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "set_next_layer.txt"
)
ACK_RESPONSE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "responses" / "admin_ack_ok.txt"
)


@pytest.fixture
def client() -> RconClient:
    rcon_client = RconClient(host="127.0.0.1", port=21114, password="test")
    rcon_client._connected = True
    rcon_client.execute = AsyncMock()
    return rcon_client


async def test_set_next_layer_contract_command_and_response_passthrough(
    client: RconClient,
) -> None:
    """P0-RCON-005: helper emits exact command template and returns RCON response."""
    request_template = SET_NEXT_LAYER_REQUEST_TEMPLATE_PATH.read_text(
        encoding="utf-8",
    ).strip()
    expected_response = ACK_RESPONSE_PATH.read_text(encoding="utf-8").strip()
    layer = "Sumari_Seed_v1 RGF+Support INS"
    expected_command = request_template.format(layer=layer)

    client.execute.return_value = expected_response
    response = await client.set_next_layer(layer)

    client.execute.assert_awaited_once_with(expected_command)
    assert response == expected_response


async def test_set_next_layer_contract_rejects_unsafe_layer(client: RconClient) -> None:
    """P0-RCON-005: helper rejects unsafe command input before dispatch."""
    with pytest.raises(ValueError, match="letters, numbers, spaces"):
        await client.set_next_layer("Sumari_Seed_v1;AdminEndMatch")
    client.execute.assert_not_called()
