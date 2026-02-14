"""Contract tests for the P0 switch-team helper command surface."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.client import RconClient

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p0]

SWITCH_TEAM_REQUEST_TEMPLATE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "switch_team.txt"
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


async def test_switch_team_contract_command_and_response_passthrough(
    client: RconClient,
) -> None:
    """P0-RCON-002: helper emits exact command string and returns RCON response."""
    request_template = SWITCH_TEAM_REQUEST_TEMPLATE_PATH.read_text(
        encoding="utf-8",
    ).strip()
    expected_response = ACK_RESPONSE_PATH.read_text(encoding="utf-8").strip()
    expected_command = request_template.format(player_id="76561198000000000")

    client.execute.return_value = expected_response
    response = await client.switch_team("76561198000000000")

    client.execute.assert_awaited_once_with(expected_command)
    assert response == expected_response
