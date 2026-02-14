"""Contract tests for typed RCON runtime error taxonomy."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from squadpy.rcon.client import (
    RconAuthenticationError,
    RconClient,
    RconCommandTimeoutError,
    RconConnectionError,
    RconDisconnectedError,
    RconError,
)

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p1]


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, RconCommandTimeoutError):
        return "command_timeout"
    if isinstance(exc, RconDisconnectedError):
        return "disconnected"
    if isinstance(exc, RconConnectionError):
        return "connection"
    if isinstance(exc, RconAuthenticationError):
        return "authentication"
    return "unknown"


async def _capture_error(coro) -> RconError:
    with pytest.raises(RconError) as exc_info:
        await coro
    return exc_info.value


async def test_error_taxonomy_contract_supports_class_based_branching() -> None:
    """P1-RT-003: callers can branch on typed subclasses for failure handling."""
    disconnected_client = RconClient(host="127.0.0.1", port=21114, password="test")
    disconnected_error = await _capture_error(disconnected_client.execute("ListPlayers"))
    assert _classify_error(disconnected_error) == "disconnected"

    connection_client = RconClient(host="127.0.0.1", port=21114, password="test")
    with patch(
        "squadpy.rcon.client.asyncio.open_connection",
        side_effect=OSError("connect failed"),
    ):
        connection_error = await _capture_error(connection_client.connect())
    assert _classify_error(connection_error) == "connection"

    timeout_client = RconClient(host="127.0.0.1", port=21114, password="test")
    timeout_client._connected = True
    timeout_client._reconnecting = False
    timeout_client._reconnect_event.set()
    timeout_client._writer = AsyncMock()
    timeout_client._writer.write = Mock()
    timeout_client._writer.drain = AsyncMock()
    with patch(
        "squadpy.rcon.client.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        timeout_error = await _capture_error(timeout_client.execute("ListPlayers"))
    assert _classify_error(timeout_error) == "command_timeout"

    auth_client = RconClient(host="127.0.0.1", port=21114, password="test")
    auth_client._writer = AsyncMock()
    auth_client._writer.write = Mock()
    auth_client._writer.drain = AsyncMock()
    with patch(
        "squadpy.rcon.client.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        auth_error = await _capture_error(auth_client._authenticate())
    assert _classify_error(auth_error) == "authentication"
