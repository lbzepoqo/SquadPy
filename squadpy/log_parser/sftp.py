"""SFTP log reader — requires asyncssh."""

from collections.abc import AsyncIterator

from squadpy.log_parser.reader import LogReader


class SFTPLogReader(LogReader):
    """Reads Squad logs from a remote server via SFTP."""

    def __init__(self, host: str, port: int, username: str, password: str,
                 path: str, poll_interval: float = 1.0):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._path = path
        self._poll_interval = poll_interval

    async def start(self) -> None:
        raise NotImplementedError(
            "SFTP log reader requires 'asyncssh' package. "
            "Install with: pip install asyncssh"
        )

    async def stop(self) -> None:
        pass

    async def tail(self) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # make it a generator
