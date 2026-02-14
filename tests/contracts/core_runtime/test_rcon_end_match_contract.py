"""Contract tests for the P1 end-match helper command surface."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.client import RconClient

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]

END_MATCH_REQUEST_TEMPLATE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "end_match.txt"
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


async def test_end_match_contract_command_and_response_passthrough(
    client: RconClient,
) -> None:
    """P1-RCON-008: helper emits exact command string and returns RCON response."""
    expected_command = END_MATCH_REQUEST_TEMPLATE_PATH.read_text(
        encoding="utf-8",
    ).strip()
    expected_response = ACK_RESPONSE_PATH.read_text(encoding="utf-8").strip()

    client.execute.return_value = expected_response
    response = await client.end_match(confirm=True)

    client.execute.assert_awaited_once_with(expected_command)
    assert response == expected_response


async def test_end_match_contract_requires_confirmation_guard(client: RconClient) -> None:
    """P1-RCON-008: helper refuses to run without explicit confirmation."""
    with pytest.raises(ValueError, match="confirm=True"):
        await client.end_match()
    client.execute.assert_not_called()
