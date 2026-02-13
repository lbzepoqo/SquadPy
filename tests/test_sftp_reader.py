"""Tests for the SFTP log reader."""

import asyncio

import pytest

from squadpy.log_parser.sftp import SFTPLogReader


class _FakeAttrs:
    def __init__(self, size: int):
        self.size = size


class _FakeStorage:
    def __init__(self, path: str, initial: bytes):
        self.path = path
        self.data = bytearray(initial)


class _FakeRemoteFile:
    def __init__(self, storage: _FakeStorage):
        self._storage = storage
        self._offset = 0

    async def seek(self, offset: int):
        self._offset = offset

    async def read(self, size: int):
        end = self._offset + size
        chunk = bytes(self._storage.data[self._offset:end])
        self._offset += len(chunk)
        return chunk

    async def close(self):
        return None


class _FakeSFTPClient:
    def __init__(self, storage: _FakeStorage):
        self._storage = storage
        self.closed = False

    async def stat(self, path: str):
        if path != self._storage.path:
            raise FileNotFoundError(path)
        return _FakeAttrs(len(self._storage.data))

    async def open(self, path: str, _mode: str):
        if path != self._storage.path:
            raise FileNotFoundError(path)
        return _FakeRemoteFile(self._storage)

    async def exit(self):
        self.closed = True


class _FakeConn:
    def __init__(self, sftp_client: _FakeSFTPClient):
        self._sftp_client = sftp_client
        self.closed = False

    async def start_sftp_client(self):
        return self._sftp_client

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


class _FakeAsyncSSH:
    def __init__(self, conn: _FakeConn):
        self._conn = conn
        self.connect_calls = []

    async def connect(self, host, port, username, password, known_hosts):
        self.connect_calls.append({
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "known_hosts": known_hosts,
        })
        return self._conn


class TestSFTPLogReader:
    async def test_start_requires_asyncssh(self, monkeypatch):
        reader = SFTPLogReader(
            host="example.com",
            port=22,
            username="user",
            password="pass",
            path="/var/log/SquadGame.log",
            poll_interval=0.01,
        )

        def _raise_import_error():
            raise RuntimeError("SFTP log reader requires 'asyncssh'. Install with: pip install asyncssh")

        monkeypatch.setattr("squadpy.log_parser.sftp._load_asyncssh", _raise_import_error)

        with pytest.raises(RuntimeError, match="requires 'asyncssh'"):
            await reader.start()

    async def test_tails_new_lines(self, monkeypatch):
        storage = _FakeStorage("/var/log/SquadGame.log", b"old line 1\nold line 2\n")
        sftp_client = _FakeSFTPClient(storage)
        conn = _FakeConn(sftp_client)
        fake_asyncssh = _FakeAsyncSSH(conn)

        reader = SFTPLogReader(
            host="example.com",
            port=22,
            username="user",
            password="pass",
            path=storage.path,
            poll_interval=0.01,
        )
        monkeypatch.setattr("squadpy.log_parser.sftp._load_asyncssh", lambda: fake_asyncssh)

        await reader.start()
        lines: list[str] = []

        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.03)
        storage.data.extend(b"line A\nline B\n")

        await asyncio.wait_for(task, timeout=1.0)
        assert lines == ["line A", "line B"]
        await reader.stop()
        assert sftp_client.closed is True
        assert conn.closed is True

    async def test_handles_truncated_file(self, monkeypatch):
        storage = _FakeStorage("/var/log/SquadGame.log", b"existing\n")
        sftp_client = _FakeSFTPClient(storage)
        conn = _FakeConn(sftp_client)
        fake_asyncssh = _FakeAsyncSSH(conn)

        reader = SFTPLogReader(
            host="example.com",
            port=22,
            username="user",
            password="pass",
            path=storage.path,
            poll_interval=0.01,
        )
        monkeypatch.setattr("squadpy.log_parser.sftp._load_asyncssh", lambda: fake_asyncssh)

        await reader.start()
        lines: list[str] = []

        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.03)
        storage.data.extend(b"line before rotate\n")

        await asyncio.sleep(0.03)
        storage.data = bytearray(b"line after rotate\n")

        await asyncio.wait_for(task, timeout=1.0)
        assert lines == ["line before rotate", "line after rotate"]
        await reader.stop()
