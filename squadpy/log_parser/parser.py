"""LogParser — matches log lines against patterns and emits events."""

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING

from squadpy.events.emitter import EventBus
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line
from squadpy.log_parser.reader import LogReader
from squadpy.observability import get_trace_recorder

if TYPE_CHECKING:
    from squadpy.rcon.client import RconClient

logger = logging.getLogger("squadpy.log_parser")


class LogParser:
    """Consumes lines from a LogReader, matches patterns, emits events."""

    def __init__(
        self,
        reader: LogReader,
        event_bus: EventBus,
        rcon_client: "RconClient | None" = None,
        player_cache_poll_seconds: float = 30.0,
    ):
        self.reader = reader
        self.event_bus = event_bus
        self.event_store = EventStore()
        self._rcon = rcon_client
        self._player_cache_poll_seconds = player_cache_poll_seconds
        self._player_cache_task = None

    async def run(self) -> None:
        """Main loop: read lines, match patterns, emit events."""
        await self.reader.start()
        if self._rcon is not None:
            await self._refresh_player_cache_once()
            self._player_cache_task = asyncio.create_task(self._poll_player_cache())
        try:
            async for line in self.reader.tail():
                trace_started_epoch_ms = int(time.time() * 1000)
                trace_started_perf = time.perf_counter()
                trace_status = "ok"
                matched = False
                emitted_events = 0
                pending_events = 0
                try:
                    event = match_line(line, self.event_store)
                    if event is not None:
                        matched = True
                        await self.event_bus.emit(event)
                        emitted_events += 1
                    drained = self.event_store.drain_pending_events()
                    pending_events = len(drained)
                    for pending in drained:
                        await self.event_bus.emit(pending)
                        emitted_events += 1
                except Exception:
                    trace_status = "error"
                    logger.exception("Error parsing line: %s", line[:200])
                finally:
                    get_trace_recorder().record_span(
                        name="log_parser.process_line",
                        started_at_epoch_ms=trace_started_epoch_ms,
                        duration_ms=(time.perf_counter() - trace_started_perf) * 1000.0,
                        status=trace_status,
                        attributes={
                            "matched": matched,
                            "emitted_events": emitted_events,
                            "pending_events": pending_events,
                        },
                    )
        finally:
            if self._player_cache_task is not None:
                self._player_cache_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._player_cache_task
            await self.reader.stop()

    async def _poll_player_cache(self) -> None:
        """Keep parser caches warm from RCON ListPlayers/ListSquads."""
        while True:
            await asyncio.sleep(self._player_cache_poll_seconds)
            await self._refresh_player_cache_once()

    async def _refresh_player_cache_once(self) -> None:
        """Fetch ListPlayers/ListSquads once and merge into parser state."""
        if self._rcon is None:
            return

        try:
            players = await self._rcon.list_players()
        except Exception:
            logger.exception("Failed to refresh player cache from RCON ListPlayers")
            return

        for player in players:
            if player.eos_id:
                record = self.event_store.players.setdefault(player.eos_id, {})
                record["steam_id"] = player.steam_id
                record["name"] = player.name
                record["team_id"] = player.team_id
            self.event_store.player_teams_by_name[player.name] = player.team_id

        if not hasattr(self._rcon, "list_squads"):
            return

        try:
            squads = await self._rcon.list_squads()
        except Exception:
            logger.exception("Failed to refresh squad cache from RCON ListSquads")
            return

        for squad in squads:
            team_name = squad.team_name.strip()
            if team_name:
                self.event_store.team_ids_by_name[team_name] = squad.team_id
