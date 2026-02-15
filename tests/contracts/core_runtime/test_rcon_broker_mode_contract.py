"""Contract test for authenticated RCON broker mode."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.broker import RconBroker
from squadpy.rcon.client import RconClient

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]


async def test_rcon_broker_mode_contract_supports_many_clients_one_upstream() -> None:
    """P2-BEYOND-002: one upstream RCON socket serves many authenticated clients."""
    upstream = cast(RconClient, AsyncMock(spec=RconClient))
    upstream.execute = AsyncMock(side_effect=["players", "squads", "ok"])

    broker = RconBroker(
        upstream,
        clients={
            "alpha": "token-alpha",
            "bravo": "token-bravo",
            "charlie": "token-charlie",
        },
    )

    responses = await asyncio.gather(
        broker.execute(token="token-alpha", command="ListPlayers"),
        broker.execute(token="token-bravo", command="ListSquads"),
        broker.execute(token="token-charlie", command="ShowCurrentMap"),
    )

    assert broker.upstream is upstream
    assert responses == ["players", "squads", "ok"]
    assert upstream.execute.await_count == 3

    records = broker.recent_audit_records()
    assert len(records) == 3
    assert {record["client_id"] for record in records} == {"alpha", "bravo", "charlie"}
    assert all(record["outcome"] == "success" for record in records)
