"""Contract tests for out-of-order response handling in RCON execution."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from squadpy.rcon.client import RconClient
from squadpy.rcon.protocol import PacketType, RconPacket

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p0]

LIST_PLAYERS_REQUEST_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "list_players.txt"
)
LIST_SQUADS_REQUEST_PATH = (
    Path(__file__).parents[1] / "fixtures" / "rcon" / "requests" / "list_squads.txt"
)
LIST_PLAYERS_RESPONSE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "rcon"
    / "responses"
    / "list_players_sample_1.txt"
)
LIST_SQUADS_RESPONSE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "rcon"
    / "responses"
    / "list_squads_sample_1.txt"
)


async def test_out_of_order_response_stress_contract() -> None:
    """P0-RT-002: request correlation remains deterministic under concurrency."""
    list_players_cmd = LIST_PLAYERS_REQUEST_PATH.read_text(encoding="utf-8").strip()
    list_squads_cmd = LIST_SQUADS_REQUEST_PATH.read_text(encoding="utf-8").strip()
    list_players_response = LIST_PLAYERS_RESPONSE_PATH.read_text(encoding="utf-8")
    list_squads_response = LIST_SQUADS_RESPONSE_PATH.read_text(encoding="utf-8")

    client = RconClient(host="127.0.0.1", port=21114, password="test")
    client._connected = True
    client._reconnecting = False
    client._reconnect_event.set()
    client._writer = AsyncMock()
    client._writer.write = Mock()
    client._writer.drain = AsyncMock()

    tasks: list[asyncio.Task[str]] = []
    expected_by_request: dict[int, str] = {}
    seen_request_ids: set[int] = set()

    for idx in range(12):
        command = list_players_cmd if idx % 2 == 0 else list_squads_cmd
        expected = list_players_response if idx % 2 == 0 else list_squads_response
        task = asyncio.create_task(client.execute(command))
        tasks.append(task)
        await asyncio.sleep(0)
        new_ids = set(client._pending_requests.keys()) - seen_request_ids
        assert len(new_ids) == 1
        request_id = new_ids.pop()
        seen_request_ids.add(request_id)
        expected_by_request[request_id] = expected

    for request_id in sorted(expected_by_request.keys(), reverse=True):
        client._handle_response_packet(
            RconPacket(
                id=request_id,
                type=PacketType.RESPONSE_VALUE,
                body=expected_by_request[request_id],
            )
        )
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

    results = await asyncio.gather(*tasks)
    assert sorted(results) == sorted(expected_by_request.values())
    assert client._writer.write.call_count == 12
    assert client._writer.drain.await_count == 12
