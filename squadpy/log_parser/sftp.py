"""SFTP log reader -- async tail implementation over remote files."""

import asyncio
import importlib
import inspect
import logging
from collections.abc import AsyncIterator
from typing import Any

from squadpy.log_parser.reader import LogReader

logger = logging.getLogger("squadpy.log_parser.sftp")


def _load_asyncssh() -> Any:
    try:
        return importlib.import_module("asyncssh")
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "SFTP log reader requires 'asyncssh'. Install with: pip install asyncssh"
        ) from e


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class SFTPLogReader(LogReader):
    """Tails a remote log file via SFTP, yielding newly appended lines."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        path: str,
        poll_interval: float = 1.0,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._path = path
        self._poll_interval = poll_interval

        self._running = False
        self._conn: Any | None = None
        self._sftp: Any | None = None
        self._offset = 0
        self._line_buffer = ""
        self._asyncssh: Any | None = None

    async def start(self) -> None:
        self._asyncssh = _load_asyncssh()
        try:
            await self._connect(seek_to_end=True)
        except Exception:
            await self._disconnect()
            raise
        self._running = True
        logger.info("Tailing SFTP log: %s@%s:%s", self._username, self._host, self._path)

    async def stop(self) -> None:
        self._running = False
        await self._disconnect()

    async def tail(self) -> AsyncIterator[str]:
        while self._running:
            if self._sftp is None:
                await asyncio.sleep(self._poll_interval)
                continue

            try:
                chunk = await self._read_new_bytes()
            except Exception as e:
                logger.warning("SFTP read failed, reconnecting: %s", e)
                await self._disconnect()
                await asyncio.sleep(self._poll_interval)
                if not self._running:
                    break
                try:
                    await self._connect(seek_to_end=False)
                except Exception as reconnect_error:
                    logger.warning("SFTP reconnect failed: %s", reconnect_error)
                continue

            if not chunk:
                await asyncio.sleep(self._poll_interval)
                continue

            self._line_buffer += chunk.decode("utf-8", errors="replace")
            while True:
                idx = self._line_buffer.find("\n")
                if idx < 0:
                    break
                line = self._line_buffer[:idx].rstrip("\r")
                self._line_buffer = self._line_buffer[idx + 1:]
                if line:
                    yield line

    async def _connect(self, seek_to_end: bool) -> None:
        assert self._asyncssh is not None

        conn = await self._asyncssh.connect(
            self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            known_hosts=None,
        )
        sftp = await _maybe_await(conn.start_sftp_client())
        self._conn = conn
        self._sftp = sftp

        attrs = await _maybe_await(sftp.stat(self._path))
        size = int(getattr(attrs, "size", 0) or 0)

        if seek_to_end:
            self._offset = size
            self._line_buffer = ""
        elif size < self._offset:
            # Log rotated/truncated while disconnected.
            self._offset = 0
            self._line_buffer = ""

    async def _disconnect(self) -> None:
        if self._sftp is not None:
            try:
                close_sftp = getattr(self._sftp, "exit", None) or getattr(self._sftp, "close", None)
                if close_sftp is not None:
                    await _maybe_await(close_sftp())
            except Exception:
                logger.debug("Ignoring SFTP client close failure", exc_info=True)
            finally:
                self._sftp = None

        if self._conn is not None:
            try:
                close_conn = getattr(self._conn, "close", None)
                if close_conn is not None:
                    close_conn()
                wait_closed = getattr(self._conn, "wait_closed", None)
                if wait_closed is not None:
                    await _maybe_await(wait_closed())
            except Exception:
                logger.debug("Ignoring SSH connection close failure", exc_info=True)
            finally:
                self._conn = None

    async def _read_new_bytes(self) -> bytes:
        assert self._sftp is not None

        attrs = await _maybe_await(self._sftp.stat(self._path))
        size = int(getattr(attrs, "size", 0) or 0)

        if size < self._offset:
            # File was rotated/truncated. Start from beginning of new file.
            self._offset = 0
            self._line_buffer = ""

        if size == self._offset:
            return b""

        file_obj = await _maybe_await(self._sftp.open(self._path, "rb"))
        try:
            await _maybe_await(file_obj.seek(self._offset))
            data = await _maybe_await(file_obj.read(size - self._offset))
        finally:
            close_file = getattr(file_obj, "close", None)
            if close_file is not None:
                await _maybe_await(close_file())

        if not data:
            return b""

        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")

        self._offset += len(data)
        return data
