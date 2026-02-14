"""Async RCON client for Squad's UE4 RCON protocol."""

import asyncio
import logging
import re
from typing import Callable

from squadpy.log_parser.id_parser import parse_online_ids
from squadpy.rcon.protocol import (
    PacketType,
    RconPacket,
    encode_packet,
    decode_packet,
)
from squadpy.rcon.types import MapInfo, RconPlayer, RconSquad

logger = logging.getLogger("squadpy.rcon")

BUFFER_SIZE = 8192

_PLAYER_RE = re.compile(
    r"^ID: (?P<id>\d+) \| Online IDs:(?P<ids>[^|]+)\| Name: (?P<name>.+) \| "
    r"Team ID: (?P<team_id>\d+|N/A) \| Squad ID: (?P<squad_id>\d+|N/A) \| "
    r"Is Leader: (?P<is_leader>True|False) \| Role: (?P<role>.+?)(?:,?)$"
)

_TEAM_RE = re.compile(r"^Team ID: (?P<team_id>\d+) \((?P<team_name>.+)\)")
_SQUAD_RE = re.compile(
    r"^ID: (?P<id>\d+) \| Name: (?P<name>.+) \| Size: (?P<size>\d+) \| "
    r"Locked: (?P<locked>True|False) \| Creator Name: (?P<creator_name>.+) \| "
    r"Creator Online IDs:(?P<creator_ids>.+)$"
)

_CURRENT_MAP_RE = re.compile(
    r"^Current level is (?P<level>[^,]+), layer is (?P<layer>[^,]+)"
    r"(?:, factions (?P<factions>.+))?$"
)

_NEXT_MAP_RE = re.compile(
    r"^Next level is (?P<level>[^,]+), layer is (?P<layer>[^,]+)"
    r"(?:, factions (?P<factions>.+))?$"
)


def parse_players(response: str) -> list[RconPlayer]:
    """Parse a ListPlayers RCON response into RconPlayer objects."""
    players: list[RconPlayer] = []
    for line in response.splitlines():
        if line.startswith("----- Recently Disconnected"):
            break
        m = _PLAYER_RE.match(line)
        if not m:
            continue
        ids = parse_online_ids(m.group("ids"))
        team_raw = m.group("team_id")
        squad_raw = m.group("squad_id")
        players.append(RconPlayer(
            id=int(m.group("id")),
            steam_id=ids["steam_id"],
            eos_id=ids["eos_id"],
            name=m.group("name"),
            team_id=int(team_raw) if team_raw != "N/A" else 0,
            squad_id=int(squad_raw) if squad_raw != "N/A" else 0,
            is_leader=m.group("is_leader") == "True",
            role=m.group("role"),
        ))
    return players


def parse_squads(response: str) -> list[RconSquad]:
    """Parse a ListSquads RCON response into RconSquad objects."""
    squads: list[RconSquad] = []
    current_team_id = 0
    current_team_name = ""
    for line in response.splitlines():
        tm = _TEAM_RE.match(line)
        if tm:
            current_team_id = int(tm.group("team_id"))
            current_team_name = tm.group("team_name")
            continue
        sm = _SQUAD_RE.match(line)
        if not sm:
            continue
        ids = parse_online_ids(sm.group("creator_ids"))
        squads.append(RconSquad(
            id=int(sm.group("id")),
            name=sm.group("name"),
            size=int(sm.group("size")),
            locked=sm.group("locked") == "True",
            creator_name=sm.group("creator_name"),
            creator_steam_id=ids["steam_id"],
            creator_eos_id=ids["eos_id"],
            team_id=current_team_id,
            team_name=current_team_name,
        ))
    return squads


def parse_map(response: str, pattern: re.Pattern) -> MapInfo | None:
    """Parse a ShowCurrentMap or ShowNextMap response."""
    for line in response.splitlines():
        m = pattern.match(line.strip())
        if m:
            return MapInfo(
                level=m.group("level"),
                layer=m.group("layer"),
                factions=m.group("factions") or "",
            )
    return None


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

    # --- Convenience methods ---

    async def list_players(self) -> list[RconPlayer]:
        """Execute ListPlayers and return parsed results."""
        response = await self.execute("ListPlayers")
        return parse_players(response)

    async def list_squads(self) -> list[RconSquad]:
        """Execute ListSquads and return parsed results."""
        response = await self.execute("ListSquads")
        return parse_squads(response)

    async def broadcast(self, message: str) -> str:
        """Broadcast a message to all players."""
        return await self.execute(f"AdminBroadcast {message}")

    async def warn(self, player_id: str, message: str) -> str:
        """Warn a player by steam ID or EOS ID."""
        return await self.execute(f'AdminWarn "{player_id}" {message}')

    async def kick(self, player_id: str, reason: str) -> str:
        """Kick a player by steam ID or EOS ID."""
        return await self.execute(f'AdminKick "{player_id}" {reason}')

    async def ban(self, player_id: str, duration: str | int, reason: str) -> str:
        """Ban a player by steam ID or EOS ID."""
        return await self.execute(f'AdminBan "{player_id}" "{duration}" {reason}')

    async def switch_team(self, player_id: str) -> str:
        """Switch a player to the opposite team by steam ID or EOS ID."""
        return await self.execute(f"AdminForceTeamChange {player_id}")

    async def force_team_change(self, player_id: int | str) -> str:
        """Force a player onto the opposite team using numeric player ID."""
        try:
            parsed_player_id = int(player_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("player_id must be a positive integer") from exc

        if parsed_player_id <= 0:
            raise ValueError("player_id must be a positive integer")

        return await self.execute(f"AdminForceTeamChangeById {parsed_player_id}")

    async def set_fog_of_war(self, mode: int | bool | str) -> str:
        """Enable or disable fog of war using layer setting mode [0|1]."""
        if isinstance(mode, bool):
            parsed_mode = 1 if mode else 0
        elif isinstance(mode, int):
            parsed_mode = mode
        elif isinstance(mode, str) and mode.strip() in {"0", "1"}:
            parsed_mode = int(mode.strip())
        else:
            raise ValueError("mode must be 0 or 1")

        if parsed_mode not in {0, 1}:
            raise ValueError("mode must be 0 or 1")

        return await self.execute(f"AdminSetFogOfWar {parsed_mode}")

    async def show_current_map(self) -> MapInfo | None:
        """Get current map info."""
        response = await self.execute("ShowCurrentMap")
        return parse_map(response, _CURRENT_MAP_RE)

    async def show_next_map(self) -> MapInfo | None:
        """Get next map info. Returns None when next map is not defined."""
        response = await self.execute("ShowNextMap")
        if "not defined" in response.lower():
            return None
        return parse_map(response, _NEXT_MAP_RE)

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
