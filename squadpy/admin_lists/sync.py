"""Admin list source adapters and merge/sync engine."""

from __future__ import annotations

import importlib
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp


def _load_asyncssh() -> Any:
    try:
        return importlib.import_module("asyncssh")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "SFTP admin list source requires 'asyncssh'. Install with: pip install asyncssh"
        ) from exc


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass(slots=True, frozen=True)
class AdminListEntry:
    steam_id: str
    role: str
    note: str
    source: str


@dataclass(slots=True, frozen=True)
class AdminListConflict:
    steam_id: str
    chosen_source: str
    chosen_role: str
    overridden_source: str
    overridden_role: str


@dataclass(slots=True)
class AdminListSyncResult:
    entries: dict[str, AdminListEntry]
    conflicts: list[AdminListConflict]


class AdminListSource(ABC):
    """Base class for admin-list data sources."""

    def __init__(self, *, name: str, default_role: str = "admin"):
        self.name = name
        self.default_role = default_role.strip() or "admin"

    @abstractmethod
    async def fetch(self) -> list[AdminListEntry]:
        """Fetch and parse all entries from this source."""


class LocalAdminListSource(AdminListSource):
    def __init__(self, *, name: str, path: str | Path, default_role: str = "admin"):
        super().__init__(name=name, default_role=default_role)
        self._path = Path(path)

    async def fetch(self) -> list[AdminListEntry]:
        if not self._path.exists():
            return []
        text = self._path.read_text(encoding="utf-8")
        return parse_admin_list_text(text, source=self.name, default_role=self.default_role)


class RemoteAdminListSource(AdminListSource):
    def __init__(
        self,
        *,
        name: str,
        url: str,
        auth_token: str = "",
        timeout_seconds: float = 8.0,
        default_role: str = "admin",
    ):
        super().__init__(name=name, default_role=default_role)
        self._url = url.strip()
        self._auth_token = auth_token.strip()
        self._timeout_seconds = timeout_seconds if timeout_seconds > 0 else 8.0

    async def fetch(self) -> list[AdminListEntry]:
        headers = {"Accept": "text/plain"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(self._url) as response:
                response.raise_for_status()
                text = await response.text()

        return parse_admin_list_text(text, source=self.name, default_role=self.default_role)


class SftpAdminListSource(AdminListSource):
    def __init__(
        self,
        *,
        name: str,
        host: str,
        port: int,
        username: str,
        password: str,
        path: str,
        default_role: str = "admin",
    ):
        super().__init__(name=name, default_role=default_role)
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._path = path

    async def fetch(self) -> list[AdminListEntry]:
        asyncssh = _load_asyncssh()
        conn: Any = None
        sftp: Any = None
        file_obj: Any = None
        try:
            conn = await asyncssh.connect(
                self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                known_hosts=None,
            )
            sftp = await _maybe_await(conn.start_sftp_client())
            file_obj = await _maybe_await(sftp.open(self._path, "rb"))
            raw = await _maybe_await(file_obj.read())
        finally:
            if file_obj is not None:
                close_file = getattr(file_obj, "close", None)
                if close_file is not None:
                    await _maybe_await(close_file())
            if sftp is not None:
                close_sftp = getattr(sftp, "exit", None) or getattr(sftp, "close", None)
                if close_sftp is not None:
                    await _maybe_await(close_sftp())
            if conn is not None:
                close_conn = getattr(conn, "close", None)
                if close_conn is not None:
                    close_conn()
                wait_closed = getattr(conn, "wait_closed", None)
                if wait_closed is not None:
                    await _maybe_await(wait_closed())

        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw)
        return parse_admin_list_text(text, source=self.name, default_role=self.default_role)


class AdminListSyncEngine:
    """Merge admin entries from multiple sources with precedence rules."""

    def __init__(
        self,
        *,
        sources: list[AdminListSource],
        precedence: list[str] | None = None,
    ):
        self._sources = list(sources)
        declared_precedence = precedence or [source.name for source in self._sources]
        self._rank: dict[str, int] = {name: index for index, name in enumerate(declared_precedence)}

    async def sync(self) -> AdminListSyncResult:
        merged: dict[str, AdminListEntry] = {}
        conflicts: list[AdminListConflict] = []

        for source in self._sources:
            entries = await source.fetch()
            for entry in entries:
                existing = merged.get(entry.steam_id)
                if existing is None:
                    merged[entry.steam_id] = entry
                    continue

                if existing.role == entry.role and existing.note == entry.note:
                    continue

                current_rank = self._source_rank(existing.source)
                candidate_rank = self._source_rank(entry.source)
                if candidate_rank < current_rank:
                    chosen = entry
                    overridden = existing
                    merged[entry.steam_id] = entry
                else:
                    chosen = existing
                    overridden = entry

                conflicts.append(
                    AdminListConflict(
                        steam_id=entry.steam_id,
                        chosen_source=chosen.source,
                        chosen_role=chosen.role,
                        overridden_source=overridden.source,
                        overridden_role=overridden.role,
                    )
                )

        return AdminListSyncResult(entries=merged, conflicts=conflicts)

    def _source_rank(self, source_name: str) -> int:
        return self._rank.get(source_name, len(self._rank) + 1000)


def parse_admin_list_text(text: str, *, source: str, default_role: str = "admin") -> list[AdminListEntry]:
    entries: list[AdminListEntry] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "," in line:
            fields = [part.strip() for part in line.split(",")]
            steam_id = fields[0] if fields else ""
            role = fields[1] if len(fields) > 1 else default_role
            note = fields[2] if len(fields) > 2 else ""
        else:
            fields = line.split()
            steam_id = fields[0] if fields else ""
            role = fields[1] if len(fields) > 1 else default_role
            note = " ".join(fields[2:]) if len(fields) > 2 else ""

        steam_id = steam_id.strip()
        if not steam_id:
            continue

        role = role.strip() or default_role
        entries.append(AdminListEntry(steam_id=steam_id, role=role, note=note, source=source))

    return entries
