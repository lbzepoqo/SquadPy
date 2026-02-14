"""Contract tests for the P1 set-team helper command surface."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.client import RconClient
from squadpy.rcon.types import RconPlayer

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]

SET_TEAM_REQUEST_TEMPLATE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "set_team.txt"
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


async def test_set_team_contract_command_and_response_passthrough(
    client: RconClient,
) -> None:
    """P1-RCON-007: helper emits exact command string and returns RCON response."""
    request_template = SET_TEAM_REQUEST_TEMPLATE_PATH.read_text(
        encoding="utf-8",
    ).strip()
    expected_response = ACK_RESPONSE_PATH.read_text(encoding="utf-8").strip()
    expected_command = request_template.format(player_id=123)

    client.list_players = AsyncMock(return_value=[
        RconPlayer(
            id=123,
            steam_id="76561198000000000",
            eos_id="eos-123",
            name="Player123",
            team_id=1,
            squad_id=1,
            is_leader=False,
            role="Rifleman",
        ),
    ])
    client.execute.return_value = expected_response
    response = await client.set_team(123, 2)

    client.execute.assert_awaited_once_with(expected_command)
    assert response == expected_response


async def test_set_team_contract_rejects_invalid_team_enum(client: RconClient) -> None:
    """P1-RCON-007: helper rejects unsupported team enum values."""
    with pytest.raises(ValueError, match="team must be one of"):
        await client.set_team(123, "team3")
    client.execute.assert_not_called()
