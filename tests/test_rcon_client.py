"""Tests for the async RCON client."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from squadpy.rcon.client import (
    RconAuthError,
    RconAuthenticationError,
    RconClient,
    RconCommandTimeoutError,
    RconConnectionError,
    RconDisconnectedError,
    RconError,
)
from squadpy.rcon.protocol import (
    PacketType,
    RconPacket,
)


class TestRconClient:
    @pytest.fixture
    def client(self):
        return RconClient(host="127.0.0.1", port=21114, password="test")

    async def test_initial_state(self, client):
        assert not client.connected

    async def test_execute_when_not_connected_raises(self, client):
        with pytest.raises(RconDisconnectedError, match="Not connected"):
            await client.execute("ListPlayers")

    async def test_packet_id_increments(self, client):
        id1 = client._next_packet_id()
        id2 = client._next_packet_id()
        assert id2 == id1 + 1

    async def test_packet_id_wraps(self, client):
        client._packet_id_counter = 2**31 - 1
        next_id = client._next_packet_id()
        assert next_id == 1

    async def test_connect_failure_raises_connection_error(self, client):
        with patch(
            "squadpy.rcon.client.asyncio.open_connection",
            side_effect=OSError("connect failed"),
        ):
            with pytest.raises(RconConnectionError, match="Failed to connect"):
                await client.connect()

    async def test_authenticate_timeout_raises_auth_error(self, client):
        client._writer = AsyncMock()
        client._writer.write = Mock()
        client._writer.drain = AsyncMock()

        with patch(
            "squadpy.rcon.client.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            with pytest.raises(RconAuthenticationError, match="Authentication timed out"):
                await client._authenticate()

        assert client._pending_requests == {}
        assert client._response_buffers == {}

    async def test_execute_timeout_raises_command_timeout_error(self, client):
        client._connected = True
        client._reconnecting = False
        client._reconnect_event.set()
        client._writer = AsyncMock()
        client._writer.write = Mock()
        client._writer.drain = AsyncMock()

        with patch(
            "squadpy.rcon.client.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            with pytest.raises(RconCommandTimeoutError, match="Command timed out"):
                await client.execute("ListPlayers")


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

    async def test_out_of_order_responses_resolve_correct_futures(self, client):
        future_a = asyncio.get_event_loop().create_future()
        future_b = asyncio.get_event_loop().create_future()
        request_a = 101
        request_b = 202
        client._pending_requests[request_a] = future_a
        client._response_buffers[request_a] = []
        client._pending_requests[request_b] = future_b
        client._response_buffers[request_b] = []

        # Complete request B before request A.
        client._handle_response_packet(
            RconPacket(id=request_b, type=PacketType.RESPONSE_VALUE, body="resp-b")
        )
        client._handle_response_packet(
            RconPacket(id=request_b, type=PacketType.RESPONSE_VALUE, body="")
        )
        client._handle_response_packet(
            RconPacket(id=request_a, type=PacketType.RESPONSE_VALUE, body="resp-a")
        )
        client._handle_response_packet(
            RconPacket(id=request_a, type=PacketType.RESPONSE_VALUE, body="")
        )

        assert await asyncio.wait_for(future_a, timeout=1.0) == "resp-a"
        assert await asyncio.wait_for(future_b, timeout=1.0) == "resp-b"

    async def test_auth_failure_response_sets_auth_error(self, client):
        request_id = 5
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = []
        client._auth_request_id = request_id

        client._handle_auth_response(
            RconPacket(id=-1, type=PacketType.AUTH_RESPONSE, body="")
        )

        with pytest.raises(RconAuthError, match="Authentication failed"):
            await future


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

    async def test_handle_disconnect_clears_pending_requests(self):
        client = RconClient(
            host="127.0.0.1",
            port=21114,
            password="test",
            auto_reconnect=False,
        )
        client._connected = True

        request_id = 99
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = ["partial"]

        await client._handle_disconnect()

        assert client.connected is False
        assert client._pending_requests == {}
        assert client._response_buffers == {}
        with pytest.raises(RconDisconnectedError, match="Connection lost"):
            await future

    async def test_handle_disconnect_calls_reconnect_when_enabled(self, client):
        client._connected = True
        client._reconnect = AsyncMock()

        await client._handle_disconnect()

        client._reconnect.assert_awaited_once()

    async def test_reconnect_succeeds_after_retry(self, client):
        client.connect = AsyncMock(side_effect=[RconError("try 1 failed"), None])
        sleep_mock = AsyncMock()

        with patch("squadpy.rcon.client.asyncio.sleep", new=sleep_mock):
            await client._reconnect()

        assert client.connect.await_count == 2
        assert sleep_mock.await_count == 2
        assert client._reconnecting is False
        assert client._reconnect_event.is_set()

    async def test_reconnect_failure_restores_event(self, client):
        client.connect = AsyncMock(side_effect=RconError("always fails"))
        sleep_mock = AsyncMock()

        with patch("squadpy.rcon.client.asyncio.sleep", new=sleep_mock):
            await client._reconnect()

        assert client.connect.await_count == client._max_retries
        assert sleep_mock.await_count == client._max_retries
        assert client._reconnecting is False
        assert client._reconnect_event.is_set()

    async def test_execute_waits_for_reconnect_and_replays_command(self, client):
        client._connected = False
        client._reconnecting = True
        client._reconnect_event.clear()
        client._writer = AsyncMock()
        client._writer.write = Mock()
        client._writer.drain = AsyncMock()

        execute_task = asyncio.create_task(client.execute("ListPlayers"))
        await asyncio.sleep(0)
        assert not execute_task.done()

        client._connected = True
        client._reconnecting = False
        client._reconnect_event.set()
        await asyncio.sleep(0)

        request_id = client._packet_id_counter
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="ok")
        )
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

        assert await execute_task == "ok"
        client._writer.write.assert_called_once()
        client._writer.drain.assert_awaited_once()

    async def test_concurrent_execute_out_of_order_completion(self, client):
        client._connected = True
        client._reconnecting = False
        client._reconnect_event.set()
        client._writer = AsyncMock()
        client._writer.write = Mock()
        client._writer.drain = AsyncMock()

        task_players = asyncio.create_task(client.execute("ListPlayers"))
        await asyncio.sleep(0)
        request_id_players = next(iter(client._pending_requests.keys()))

        task_squads = asyncio.create_task(client.execute("ListSquads"))
        await asyncio.sleep(0)
        request_id_squads = next(
            rid for rid in client._pending_requests.keys() if rid != request_id_players
        )

        # Return squad response first, then players response.
        client._handle_response_packet(
            RconPacket(
                id=request_id_squads,
                type=PacketType.RESPONSE_VALUE,
                body="squads-response",
            )
        )
        client._handle_response_packet(
            RconPacket(id=request_id_squads, type=PacketType.RESPONSE_VALUE, body="")
        )
        client._handle_response_packet(
            RconPacket(
                id=request_id_players,
                type=PacketType.RESPONSE_VALUE,
                body="players-response",
            )
        )
        client._handle_response_packet(
            RconPacket(id=request_id_players, type=PacketType.RESPONSE_VALUE, body="")
        )

        players_result = await task_players
        squads_result = await task_squads

        assert players_result == "players-response"
        assert squads_result == "squads-response"
        assert client._writer.write.call_count == 2
        assert client._writer.drain.await_count == 2

    async def test_high_concurrency_reverse_order_completion(self, client):
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
            task = asyncio.create_task(client.execute(f"Command-{idx}"))
            tasks.append(task)
            await asyncio.sleep(0)
            new_ids = set(client._pending_requests.keys()) - seen_request_ids
            assert len(new_ids) == 1
            request_id = new_ids.pop()
            seen_request_ids.add(request_id)
            expected_by_request[request_id] = f"response-{idx}"

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
