"""Async RCON client for Squad's UE4 RCON protocol."""

import asyncio
import logging
from typing import Callable

from squadpy.rcon.protocol import (
    PacketType,
    RconPacket,
    encode_packet,
    decode_packet,
)

logger = logging.getLogger("squadpy.rcon")

BUFFER_SIZE = 8192


class RconError(Exception):
    """General RCON error."""


class RconAuthError(RconError):
    """Authentication failed."""


class RconClient:
    """Async RCON client for Squad servers."""

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        auto_reconnect: bool = True,
        max_retries: int = 4,
        retry_delay: float = 5.0,
        command_timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.auto_reconnect = auto_reconnect
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._command_timeout = command_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._packet_id_counter = 0
        self._buffer = bytearray()
        self._pending_requests: dict[int, asyncio.Future[str]] = {}
        self._response_buffers: dict[int, list[str]] = {}
        self._connected = False
        self._reconnecting = False
        self._reconnect_event: asyncio.Event = asyncio.Event()
        self._reconnect_event.set()
        self._reader_task: asyncio.Task | None = None

        self.on_chat: Callable[[str], None] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def _next_packet_id(self) -> int:
        self._packet_id_counter += 1
        if self._packet_id_counter >= 2**31:
            self._packet_id_counter = 1
        return self._packet_id_counter

    def _get_retry_delay(self, attempt: int) -> float:
        return self._retry_delay * (2 ** attempt)

    async def connect(self) -> None:
        logger.info("Connecting to RCON at %s:%d", self.host, self.port)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self._command_timeout,
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise RconError(f"Failed to connect to {self.host}:{self.port}: {e}") from e

        self._reader = reader
        self._writer = writer
        self._connected = True
        self._buffer.clear()

        self._reader_task = asyncio.create_task(self._read_loop())
        await self._authenticate()
        logger.info("RCON connected and authenticated")

    async def _authenticate(self) -> None:
        assert self._writer is not None
        auth_id = self._next_packet_id()
        packet = encode_packet(PacketType.AUTH, auth_id, self.password)
        self._writer.write(packet)
        await self._writer.drain()

        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_requests[auth_id] = future
        self._response_buffers[auth_id] = []

        try:
            await asyncio.wait_for(future, timeout=self._command_timeout)
        except asyncio.TimeoutError:
            raise RconAuthError("Authentication timed out")

    async def execute(self, command: str) -> str:
        if not self._connected:
            raise RconError("Not connected")

        await self._reconnect_event.wait()

        request_id = self._next_packet_id()
        cmd_packet = encode_packet(PacketType.EXEC_COMMAND, request_id, command)
        end_packet = encode_packet(PacketType.EXEC_COMMAND, request_id, "")

        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        self._response_buffers[request_id] = []

        assert self._writer is not None
        self._writer.write(cmd_packet + end_packet)
        await self._writer.drain()

        try:
            return await asyncio.wait_for(future, timeout=self._command_timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            self._response_buffers.pop(request_id, None)
            raise RconError(f"Command timed out: {command}")

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while self._connected:
                data = await self._reader.read(BUFFER_SIZE)
                if not data:
                    logger.warning("RCON connection closed by server")
                    await self._handle_disconnect()
                    return
                self._buffer.extend(data)
                self._process_buffer()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("RCON read error: %s", e)
            await self._handle_disconnect()

    def _process_buffer(self) -> None:
        while len(self._buffer) > 0:
            result = decode_packet(bytes(self._buffer))
            if result is None:
                break
            packet, consumed = result
            del self._buffer[:consumed]

            if packet.type == PacketType.CHAT_VALUE:
                self._handle_chat_packet(packet)
            elif packet.type == PacketType.AUTH_RESPONSE:
                self._handle_auth_response(packet)
            else:
                self._handle_response_packet(packet)

    def _handle_auth_response(self, packet: RconPacket) -> None:
        if packet.id in self._pending_requests:
            future = self._pending_requests.pop(packet.id)
            self._response_buffers.pop(packet.id, None)
            if packet.id == -1:
                future.set_exception(RconAuthError("Authentication failed"))
            elif not future.done():
                future.set_result("")

    def _handle_response_packet(self, packet: RconPacket) -> None:
        if packet.is_follow_response:
            return

        request_id = packet.id
        if request_id not in self._pending_requests:
            return

        if packet.body == "":
            future = self._pending_requests.pop(request_id)
            parts = self._response_buffers.pop(request_id, [])
            if not future.done():
                future.set_result("".join(parts))
        else:
            self._response_buffers.setdefault(request_id, []).append(packet.body)

    def _handle_chat_packet(self, packet: RconPacket) -> None:
        if self.on_chat is not None:
            try:
                self.on_chat(packet.body)
            except Exception:
                logger.exception("Error in chat callback")

    async def _handle_disconnect(self) -> None:
        self._connected = False
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(RconError("Connection lost"))
        self._pending_requests.clear()
        self._response_buffers.clear()

        if self.auto_reconnect:
            await self._reconnect()

    async def _reconnect(self) -> None:
        self._reconnecting = True
        self._reconnect_event.clear()

        for attempt in range(self._max_retries):
            delay = self._get_retry_delay(attempt)
            logger.info("Reconnecting in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, self._max_retries)
            await asyncio.sleep(delay)

            try:
                await self.connect()
                self._reconnecting = False
                self._reconnect_event.set()
                logger.info("Reconnected successfully")
                return
            except RconError as e:
                logger.warning("Reconnect attempt %d failed: %s", attempt + 1, e)

        self._reconnecting = False
        self._reconnect_event.set()
        logger.error("Failed to reconnect after %d attempts", self._max_retries)

    async def close(self) -> None:
        self._connected = False
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        logger.info("RCON connection closed")
