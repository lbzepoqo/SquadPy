"""Contract tests for reconnect replay behavior in RCON command execution."""

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
LIST_PLAYERS_RESPONSE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "rcon"
    / "responses"
    / "list_players_sample_1.txt"
)


async def test_reconnect_replay_contract_flushes_queued_command() -> None:
    """P0-RT-001: command queued during reconnect flushes once reconnect completes."""
    command = LIST_PLAYERS_REQUEST_PATH.read_text(encoding="utf-8").strip()
    response_payload = LIST_PLAYERS_RESPONSE_PATH.read_text(encoding="utf-8")

    client = RconClient(
        host="127.0.0.1",
        port=21114,
        password="test",
        auto_reconnect=True,
    )
    client._connected = False
    client._reconnecting = True
    client._reconnect_event.clear()
    client._writer = AsyncMock()
    client._writer.write = Mock()
    client._writer.drain = AsyncMock()

    request_task = asyncio.create_task(client.execute(command))
    await asyncio.sleep(0)
    assert not request_task.done()

    client._connected = True
    client._reconnecting = False
    client._reconnect_event.set()
    await asyncio.sleep(0)

    request_id = client._packet_id_counter
    client._handle_response_packet(
        RconPacket(
            id=request_id,
            type=PacketType.RESPONSE_VALUE,
            body=response_payload,
        )
    )
    client._handle_response_packet(
        RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
    )

    replayed_response = await request_task
    assert replayed_response == response_payload
    client._writer.write.assert_called_once()
    client._writer.drain.assert_awaited_once()
