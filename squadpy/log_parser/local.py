"""Local file log reader -- async tail implementation."""

import asyncio
import io
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from squadpy.log_parser.reader import LogReader

logger = logging.getLogger("squadpy.log_parser.local")


class LocalLogReader(LogReader):
    """Tails a local log file, yielding new lines as they appear."""

    def __init__(self, path: str, poll_interval: float = 1.0):
        self._path = Path(path)
        self._poll_interval = poll_interval
        self._running = False
        self._file: io.TextIOWrapper | None = None

    async def start(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Log file not found: {self._path}")
        self._file = open(self._path, "r", encoding="utf-8", errors="replace")
        self._file.seek(0, 2)  # seek to end
        self._running = True
        logger.info("Tailing local log: %s", self._path)

    async def stop(self) -> None:
        self._running = False
        if self._file:
            self._file.close()
            self._file = None

    async def tail(self) -> AsyncIterator[str]:
        while self._running and self._file is not None:
            line = self._file.readline()
            if line:
                stripped = line.rstrip("\n\r")
                if stripped:
                    yield stripped
            else:
                await asyncio.sleep(self._poll_interval)
