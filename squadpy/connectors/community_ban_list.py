"""Community Ban List moderation connector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from squadpy.connectors.base import Connector

DEFAULT_COMMUNITY_BAN_LIST_API_URL = "https://communitybanlist.com/api"


@dataclass(slots=True, frozen=True)
class CommunityBan:
    reason: str
    source: str
    active: bool
    expires_at: str | None = None
    issued_at: str | None = None


@dataclass(slots=True, frozen=True)
class CommunityBanListPlayer:
    steam_id: str
    reputation: str
    risk_level: str
    active_bans: tuple[CommunityBan, ...]
    attributes: dict[str, Any]


class CommunityBanListConnector(Connector):
    """External moderation/community API connector for Community Ban List."""

    def __init__(
        self,
        *,
        api_token: str,
        base_url: str = DEFAULT_COMMUNITY_BAN_LIST_API_URL,
        timeout_seconds: float = 8.0,
    ):
        super().__init__(name="community_ban_list")
        self._api_token = str(api_token).strip()
        self._base_url = str(base_url).strip().rstrip("/") or DEFAULT_COMMUNITY_BAN_LIST_API_URL
        self._timeout_seconds = timeout_seconds if timeout_seconds > 0 else 8.0
        self._session: aiohttp.ClientSession | None = None

    async def _start(self) -> None:
        headers = {"Accept": "application/json"}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)

    async def _stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def lookup_player(self, steam_id: str) -> CommunityBanListPlayer | None:
        """Fetch Community Ban List information by SteamID64."""
        target = str(steam_id).strip()
        if not target:
            raise ValueError("steam_id must not be empty")

        session = self._require_session()
        url = f"{self._base_url}/players/{target}"
        async with session.get(url) as response:
            if response.status == 404:
                return None
            response.raise_for_status()
            payload = await response.json()

        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Invalid Community Ban List response payload")

        raw_attributes = data.get("attributes", {})
        attributes = raw_attributes if isinstance(raw_attributes, dict) else {}
        bans = self._extract_active_bans(attributes.get("bans"))

        return CommunityBanListPlayer(
            steam_id=str(data.get("id", target)),
            reputation=str(attributes.get("reputation", "unknown")),
            risk_level=str(attributes.get("risk", "unknown")),
            active_bans=tuple(bans),
            attributes=attributes,
        )

    def _extract_active_bans(self, payload: Any) -> list[CommunityBan]:
        if not isinstance(payload, list):
            return []

        active: list[CommunityBan] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            is_active = bool(entry.get("active", False))
            if not is_active:
                continue
            active.append(
                CommunityBan(
                    reason=str(entry.get("reason", "")),
                    source=str(entry.get("source", "")),
                    active=True,
                    issued_at=_optional_text(entry.get("issued_at")),
                    expires_at=_optional_text(entry.get("expires_at")),
                )
            )
        return active

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("CommunityBanListConnector is not started")
        return self._session


def _optional_text(value: Any) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    return text

