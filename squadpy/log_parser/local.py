"""Local file log reader -- async tail implementation."""

import asyncio
import io
import logging
import os
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Any

try:
    from watchfiles import awatch
except ModuleNotFoundError:  # pragma: no cover - exercised when optional dep missing
    awatch = None

from squadpy.log_parser.reader import LogReader

logger = logging.getLogger("squadpy.log_parser.local")


class LocalLogReader(LogReader):
    """Tails a local log file, yielding new lines as they appear.

    Handles common log maintenance patterns while running:
    - file rotation (path points to a new inode)
    - in-place truncation (copytruncate)
    """

    def __init__(self, path: str, poll_interval: float = 1.0):
        self._path = Path(path)
        self._poll_interval = poll_interval
        self._running = False
        self._file: io.TextIOWrapper | None = None
        self._watch_events: AsyncGenerator[set[tuple[Any, str]], None] | None = None

    async def start(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Log file not found: {self._path}")
        self._file = self._open_file(seek_to_end=True)
        self._watch_events = self._build_watcher()
        self._running = True
        logger.info("Tailing local log: %s", self._path)

    async def stop(self) -> None:
        self._running = False

        if self._watch_events is not None:
            try:
                await self._watch_events.aclose()
            except Exception:
                logger.debug("Failed to close local log watcher", exc_info=True)
            finally:
                self._watch_events = None

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
                if self._refresh_file_handle():
                    continue
                await self._wait_for_update()

    def _open_file(self, seek_to_end: bool) -> io.TextIOWrapper:
        file_obj = open(self._path, "r", encoding="utf-8", errors="replace")
        if seek_to_end:
            file_obj.seek(0, io.SEEK_END)
        return file_obj

    def _refresh_file_handle(self) -> bool:
        if self._file is None:
            return False

        try:
            path_stat = self._path.stat()
        except FileNotFoundError:
            # Rotation can briefly remove the path before the new file appears.
            return False

        try:
            file_stat = os.fstat(self._file.fileno())
        except OSError:
            return False

        if (path_stat.st_dev, path_stat.st_ino) != (file_stat.st_dev, file_stat.st_ino):
            try:
                new_file = self._open_file(seek_to_end=False)
            except OSError:
                return False
            old_file = self._file
            self._file = new_file
            old_file.close()
            logger.info("Detected log rotation; reopened file: %s", self._path)
            return True

        if path_stat.st_size < self._file.tell():
            self._file.seek(0)
            logger.info("Detected log truncation; reset file position: %s", self._path)
            return True

        return False

    def _build_watcher(self) -> AsyncGenerator[set[tuple[Any, str]], None] | None:
        if awatch is None:
            return None

        return awatch(
            self._path.parent,
            recursive=False,
            debounce=0,
            step=50,
        )

    async def _wait_for_update(self) -> None:
        if self._watch_events is None:
            await asyncio.sleep(self._poll_interval)
            return

        try:
            await asyncio.wait_for(anext(self._watch_events), timeout=self._poll_interval)
        except asyncio.TimeoutError:
            return
        except StopAsyncIteration:
            self._watch_events = None
            await asyncio.sleep(self._poll_interval)
        except Exception:
            logger.debug("Local file watcher failed; falling back to polling", exc_info=True)
            self._watch_events = None
            await asyncio.sleep(self._poll_interval)
