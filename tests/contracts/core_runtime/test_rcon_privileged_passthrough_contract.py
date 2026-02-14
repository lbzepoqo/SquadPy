"""Contract tests for the P1 privileged passthrough wrapper."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.client import RconClient

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]

SHOW_CURRENT_MAP_REQUEST_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "show_current_map.txt"
)
END_MATCH_REQUEST_PATH = (
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


async def test_execute_privileged_contract_rejects_unauthorized_and_audits(
    client: RconClient,
) -> None:
    """P1-RCON-009: unauthorized passthrough commands are rejected and audited."""
    command = END_MATCH_REQUEST_PATH.read_text(encoding="utf-8").strip()

    with pytest.raises(PermissionError, match="Unauthorized privileged command"):
        await client.execute_privileged(
            command,
            actor="contract_tester",
            origin="contract",
            policy=lambda _candidate: False,
        )

    client.execute.assert_not_called()
    records = client.recent_privileged_audit_records()
    assert records
    assert records[-1]["actor"] == "contract_tester"
    assert records[-1]["origin"] == "contract"
    assert records[-1]["target"] == command
    assert records[-1]["outcome"] == "rejected"
    assert records[-1]["detail"] == "unauthorized"


async def test_execute_privileged_contract_allows_authorized_command(
    client: RconClient,
) -> None:
    """P1-RCON-009: authorized passthrough commands dispatch and are audited."""
    command = SHOW_CURRENT_MAP_REQUEST_PATH.read_text(encoding="utf-8").strip()
    expected_response = ACK_RESPONSE_PATH.read_text(encoding="utf-8").strip()

    client.execute.return_value = expected_response
    response = await client.execute_privileged(
        command,
        actor="contract_tester",
        origin="contract",
        policy=lambda candidate: candidate == command,
    )

    client.execute.assert_awaited_once_with(command)
    assert response == expected_response

    records = client.recent_privileged_audit_records()
    assert records
    assert records[-1]["actor"] == "contract_tester"
    assert records[-1]["origin"] == "contract"
    assert records[-1]["target"] == command
    assert records[-1]["outcome"] == "success"
