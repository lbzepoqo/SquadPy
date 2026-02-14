"""Dashboard-oriented analytics query helpers for db_log."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text


class DbLogAnalyticsQueryHelper:
    """Provides dashboard-ready aggregate queries over db_log analytics views."""

    def __init__(
        self,
        session_factory,
        *,
        default_window_days: int = 7,
        default_limit: int = 90,
    ) -> None:
        self._session_factory = session_factory
        self._default_window_days = self._positive_int(default_window_days, 7)
        self._default_limit = self._positive_int(default_limit, 90)

    async def dashboard_snapshot(
        self,
        *,
        window_days: int | None = None,
        limit: int | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        since = self._window_start(window_days)
        row_limit = self._effective_limit(limit)
        return {
            "population_daily": await self.population_daily(since=since, limit=row_limit),
            "event_volume_daily": await self.event_volume_daily(since=since, limit=row_limit),
            "moderation_daily": await self.moderation_daily(since=since, limit=row_limit),
            "chat_volume_daily": await self.chat_volume_daily(since=since, limit=row_limit),
        }

    async def population_daily(self, *, since: datetime, limit: int) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT bucket_day, sessions_started, unique_players, matches_seen
            FROM db_log_mv_population_daily
            WHERE bucket_day >= DATE(:since)
            ORDER BY bucket_day ASC
            LIMIT :limit
            """
        )
        return await self._fetch_rows(query, {"since": since.isoformat(), "limit": limit})

    async def event_volume_daily(self, *, since: datetime, limit: int) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT bucket_day, event_name, event_count
            FROM db_log_mv_event_volume_daily
            WHERE bucket_day >= DATE(:since)
            ORDER BY bucket_day ASC, event_count DESC, event_name ASC
            LIMIT :limit
            """
        )
        return await self._fetch_rows(query, {"since": since.isoformat(), "limit": limit})

    async def moderation_daily(self, *, since: datetime, limit: int) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT bucket_day, action, action_count
            FROM db_log_mv_moderation_daily
            WHERE bucket_day >= DATE(:since)
            ORDER BY bucket_day ASC, action_count DESC, action ASC
            LIMIT :limit
            """
        )
        return await self._fetch_rows(query, {"since": since.isoformat(), "limit": limit})

    async def chat_volume_daily(self, *, since: datetime, limit: int) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT bucket_day, channel, message_count
            FROM db_log_mv_chat_volume_daily
            WHERE bucket_day >= DATE(:since)
            ORDER BY bucket_day ASC, message_count DESC, channel ASC
            LIMIT :limit
            """
        )
        return await self._fetch_rows(query, {"since": since.isoformat(), "limit": limit})

    async def _fetch_rows(self, query, params: dict[str, Any]) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(query, params)
            return [dict(row) for row in result.mappings().all()]

    def _window_start(self, window_days: int | None) -> datetime:
        days = self._positive_int(
            self._default_window_days if window_days is None else window_days,
            self._default_window_days,
        )
        return self._utc_now() - timedelta(days=days)

    def _effective_limit(self, limit: int | None) -> int:
        return self._positive_int(
            self._default_limit if limit is None else limit,
            self._default_limit,
        )

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _positive_int(value, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
