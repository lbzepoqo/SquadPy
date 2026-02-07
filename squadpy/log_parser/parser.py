"""LogParser — matches log lines against patterns and emits events."""

import logging

from squadpy.events.emitter import EventBus
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line
from squadpy.log_parser.reader import LogReader

logger = logging.getLogger("squadpy.log_parser")


class LogParser:
    """Consumes lines from a LogReader, matches patterns, emits events."""

    def __init__(self, reader: LogReader, event_bus: EventBus):
        self.reader = reader
        self.event_bus = event_bus
        self.event_store = EventStore()

    async def run(self) -> None:
        """Main loop: read lines, match patterns, emit events."""
        await self.reader.start()
        try:
            async for line in self.reader.tail():
                try:
                    event = match_line(line, self.event_store)
                    if event is not None:
                        await self.event_bus.emit(event)
                except Exception:
                    logger.exception("Error parsing line: %s", line[:200])
        finally:
            await self.reader.stop()
