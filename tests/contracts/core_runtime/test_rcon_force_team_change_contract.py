"""Contract tests for the P0 force-team-change helper command surface."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.client import RconClient

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p0]

FORCE_TEAM_CHANGE_REQUEST_TEMPLATE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "force_team_change.txt"
)
ACK_RESPONSE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "responses" / "admin_ack_ok.txt"
)
INVALID_ID_RESPONSE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "rcon"
    / "responses"
    / "admin_ack_failure_invalid_id.txt"
)


@pytest.fixture
def client() -> RconClient:
    rcon_client = RconClient(host="127.0.0.1", port=21114, password="test")
    rcon_client._connected = True
    rcon_client.execute = AsyncMock()
    return rcon_client


async def test_force_team_change_contract_valid_id_command_and_response(
    client: RconClient,
) -> None:
    """P0-RCON-003: helper emits exact by-id command and returns success response."""
    request_template = FORCE_TEAM_CHANGE_REQUEST_TEMPLATE_PATH.read_text(
        encoding="utf-8",
    ).strip()
    expected_response = ACK_RESPONSE_PATH.read_text(encoding="utf-8").strip()
    expected_command = request_template.format(player_id=123)

    client.execute.return_value = expected_response
    response = await client.force_team_change(123)

    client.execute.assert_awaited_once_with(expected_command)
    assert response == expected_response


async def test_force_team_change_contract_invalid_id_response_passthrough(
    client: RconClient,
) -> None:
    """P0-RCON-003: helper preserves server invalid-id responses."""
    request_template = FORCE_TEAM_CHANGE_REQUEST_TEMPLATE_PATH.read_text(
        encoding="utf-8",
    ).strip()
    expected_response = INVALID_ID_RESPONSE_PATH.read_text(encoding="utf-8").strip()
    expected_command = request_template.format(player_id=999999)

    client.execute.return_value = expected_response
    response = await client.force_team_change(999999)

    client.execute.assert_awaited_once_with(expected_command)
    assert response == expected_response
