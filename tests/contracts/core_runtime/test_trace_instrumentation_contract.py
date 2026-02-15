"""Contract tests for critical-path trace instrumentation."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from squadpy.events.emitter import EventBus
from squadpy.log_parser import LogParser, LogReader
from squadpy.observability import get_trace_recorder
from squadpy.rcon.client import RconClient
from squadpy.rcon.protocol import PacketType, RconPacket

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]


class _SingleLineReader(LogReader):
    def __init__(self, line: str):
        self._line = line
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def tail(self):
        if self._running:
            yield self._line


async def test_trace_instrumentation_contract_captures_rcon_and_parser_latency() -> None:
    """P2-BEYOND-004: traces capture RCON command latency and parser timing."""
    recorder = get_trace_recorder()
    recorder.clear()

    client = RconClient(host="127.0.0.1", port=21114, password="test", auto_reconnect=False)
    client._connected = True
    client._reconnect_event.set()
    client._writer = AsyncMock()
    client._writer.write = Mock()
    client._writer.drain = AsyncMock()

    command_task = asyncio.create_task(client.execute("ListPlayers"))
    await asyncio.sleep(0)
    request_id = client._packet_id_counter
    client._handle_response_packet(
        RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="players")
    )
    client._handle_response_packet(
        RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
    )
    await command_task

    parser_line = (
        "[2026.02.06-15.02.16:900][771]LogSquad: USQGameState: Server Tick Rate: 63.78"
    )
    parser = LogParser(
        reader=_SingleLineReader(parser_line),
        event_bus=EventBus(),
    )
    await parser.run()

    spans = recorder.recent_spans(limit=20)
    span_names = {span["name"] for span in spans}
    assert "rcon.execute" in span_names
    assert "log_parser.process_line" in span_names

    rcon_span = next(span for span in spans if span["name"] == "rcon.execute")
    parser_span = next(span for span in spans if span["name"] == "log_parser.process_line")
    assert rcon_span["duration_ms"] >= 0
    assert parser_span["duration_ms"] >= 0
