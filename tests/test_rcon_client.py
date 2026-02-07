"""Tests for the async RCON client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.rcon.client import RconClient, RconError, RconAuthError
from squadpy.rcon.protocol import (
    PacketType,
    RconPacket,
    encode_packet,
)


class TestRconClient:
    @pytest.fixture
    def client(self):
        return RconClient(host="127.0.0.1", port=21114, password="test")

    async def test_initial_state(self, client):
        assert not client.connected

    async def test_execute_when_not_connected_raises(self, client):
        with pytest.raises(RconError, match="Not connected"):
            await client.execute("ListPlayers")

    async def test_packet_id_increments(self, client):
        id1 = client._next_packet_id()
        id2 = client._next_packet_id()
        assert id2 == id1 + 1

    async def test_packet_id_wraps(self, client):
        client._packet_id_counter = 2**31 - 1
        next_id = client._next_packet_id()
        assert next_id == 1


class TestRconProtocolHandler:
    """Test the protocol handling logic with simulated data."""

    @pytest.fixture
    def client(self):
        return RconClient(host="127.0.0.1", port=21114, password="test")

    async def test_single_packet_response(self, client):
        request_id = 1
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = []

        response_body = "Player list here"
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body=response_body)
        )
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

        result = await asyncio.wait_for(future, timeout=1.0)
        assert result == response_body

    async def test_multi_packet_response(self, client):
        request_id = 1
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = []

        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="part1")
        )
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="part2")
        )
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

        result = await asyncio.wait_for(future, timeout=1.0)
        assert result == "part1part2"

    async def test_chat_packet_callback(self, client):
        received = []
        client.on_chat = lambda body: received.append(body)

        client._handle_chat_packet(
            RconPacket(id=0, type=PacketType.CHAT_VALUE, body="Player: hello")
        )

        assert received == ["Player: hello"]

    async def test_follow_response_ignored(self, client):
        request_id = 1
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = []

        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="data")
        )
        # Follow response — should be ignored
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="",
                       is_follow_response=True)
        )
        # Actual end marker
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

        result = await asyncio.wait_for(future, timeout=1.0)
        assert result == "data"


class TestRconReconnect:
    @pytest.fixture
    def client(self):
        return RconClient(
            host="127.0.0.1", port=21114, password="test",
            auto_reconnect=True, max_retries=3, retry_delay=0.01,
        )

    async def test_reconnect_delays_are_exponential(self, client):
        delays = [client._get_retry_delay(i) for i in range(4)]
        assert delays[0] == client._retry_delay
        assert delays[1] == client._retry_delay * 2
        assert delays[2] == client._retry_delay * 4
        assert delays[3] == client._retry_delay * 8
