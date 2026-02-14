"""Tests for admin list source adapters and sync merge behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from squadpy.admin_lists import (
    AdminListEntry,
    AdminListSource,
    AdminListSyncEngine,
    LocalAdminListSource,
    RemoteAdminListSource,
    SftpAdminListSource,
    parse_admin_list_text,
)


def test_parse_admin_list_text_supports_csv_and_whitespace() -> None:
    parsed = parse_admin_list_text(
        """
        # comment
        76561198000000001,admin,primary
        76561198000000002 moderator alt account
        76561198000000003
        """,
        source="local",
        default_role="moderator",
    )

    assert [entry.steam_id for entry in parsed] == [
        "76561198000000001",
        "76561198000000002",
        "76561198000000003",
    ]
    assert parsed[0].role == "admin"
    assert parsed[0].note == "primary"
    assert parsed[1].role == "moderator"
    assert parsed[1].note == "alt account"
    assert parsed[2].role == "moderator"


async def test_local_source_reads_entries(tmp_path: Path) -> None:
    data_path = tmp_path / "admins.txt"
    data_path.write_text("76561198000000001,admin,primary\n", encoding="utf-8")

    source = LocalAdminListSource(name="local", path=data_path)
    entries = await source.fetch()

    assert entries == [
        AdminListEntry(
            steam_id="76561198000000001",
            role="admin",
            note="primary",
            source="local",
        )
    ]


@dataclass(slots=True)
class FakeHttpResponse:
    status: int
    body: str

    async def __aenter__(self) -> "FakeHttpResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return self.body

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError("HTTP error")


class FakeHttpSession:
    def __init__(self, response: FakeHttpResponse):
        self._response = response
        self.last_url = ""

    async def __aenter__(self) -> "FakeHttpSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str) -> FakeHttpResponse:
        self.last_url = url
        return self._response


async def test_remote_source_fetches_and_parses_entries() -> None:
    source = RemoteAdminListSource(
        name="remote",
        url="https://example.test/admins.txt",
        auth_token="token_123",
    )
    fake_session = FakeHttpSession(FakeHttpResponse(200, "76561198000000002,senior_admin,remote\n"))

    with patch("squadpy.admin_lists.sync.aiohttp.ClientSession", return_value=fake_session) as mock_client_session:
        entries = await source.fetch()

    assert entries == [
        AdminListEntry(
            steam_id="76561198000000002",
            role="senior_admin",
            note="remote",
            source="remote",
        )
    ]
    assert fake_session.last_url == "https://example.test/admins.txt"
    headers = mock_client_session.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer token_123"


class FakeSftpFile:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self) -> bytes:
        return self._data

    async def close(self) -> None:
        return None


class FakeSftpClient:
    def __init__(self, data: bytes):
        self._data = data

    async def open(self, _path: str, _mode: str) -> FakeSftpFile:
        return FakeSftpFile(self._data)

    async def exit(self) -> None:
        return None


class FakeConnection:
    def __init__(self, data: bytes):
        self._sftp = FakeSftpClient(data)

    async def start_sftp_client(self) -> FakeSftpClient:
        return self._sftp

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


async def test_sftp_source_fetches_and_parses_entries() -> None:
    source = SftpAdminListSource(
        name="sftp",
        host="sftp.example.test",
        port=22,
        username="tester",
        password="secret",
        path="/srv/admins.txt",
    )

    async_connect = AsyncMock(return_value=FakeConnection(b"76561198000000003,owner,sftp\n"))
    fake_asyncssh = SimpleNamespace(connect=async_connect)

    with patch("squadpy.admin_lists.sync._load_asyncssh", return_value=fake_asyncssh):
        entries = await source.fetch()

    assert entries == [
        AdminListEntry(
            steam_id="76561198000000003",
            role="owner",
            note="sftp",
            source="sftp",
        )
    ]
    async_connect.assert_awaited_once_with(
        "sftp.example.test",
        port=22,
        username="tester",
        password="secret",
        known_hosts=None,
    )


class StaticSource(AdminListSource):
    def __init__(self, *, name: str, entries: list[AdminListEntry]):
        super().__init__(name=name)
        self._entries = entries

    async def fetch(self) -> list[AdminListEntry]:
        return list(self._entries)


async def test_sync_engine_honors_precedence_and_records_conflicts() -> None:
    local = StaticSource(
        name="local",
        entries=[
            AdminListEntry("76561198000000100", "owner", "local owner", "local"),
        ],
    )
    remote = StaticSource(
        name="remote",
        entries=[
            AdminListEntry("76561198000000100", "moderator", "remote role", "remote"),
            AdminListEntry("76561198000000101", "admin", "remote only", "remote"),
        ],
    )
    sftp = StaticSource(
        name="sftp",
        entries=[
            AdminListEntry("76561198000000100", "trial_admin", "sftp role", "sftp"),
        ],
    )
    engine = AdminListSyncEngine(
        sources=[local, remote, sftp],
        precedence=["local", "remote", "sftp"],
    )

    result = await engine.sync()

    assert result.entries["76561198000000100"].role == "owner"
    assert result.entries["76561198000000100"].source == "local"
    assert result.entries["76561198000000101"].role == "admin"
    assert result.entries["76561198000000101"].source == "remote"
    assert len(result.conflicts) == 2
    assert {conflict.overridden_source for conflict in result.conflicts} == {"remote", "sftp"}

