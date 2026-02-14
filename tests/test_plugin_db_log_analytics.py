"""Smoke tests for DBLog analytics query helpers."""

import importlib.util
from datetime import datetime
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock


_ANALYTICS_MODULE = None


def _load_analytics_module():
    global _ANALYTICS_MODULE
    if _ANALYTICS_MODULE is not None:
        return _ANALYTICS_MODULE

    spec = importlib.util.spec_from_file_location(
        "db_log_analytics",
        Path(__file__).parent.parent / "plugins" / "db_log" / "analytics.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    _ANALYTICS_MODULE = module
    return module


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    class _Mappings:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    def mappings(self):
        return self._Mappings(self._rows)


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestDbLogAnalyticsQueryHelper:
    async def test_dashboard_snapshot_smoke_executes_all_view_queries(self):
        module = _load_analytics_module()
        helper = module.DbLogAnalyticsQueryHelper
        session = AsyncMock()
        session.execute.side_effect = [
            _FakeResult([{"bucket_day": "2026-02-13", "sessions_started": 14, "unique_players": 12, "matches_seen": 1}]),
            _FakeResult([{"bucket_day": "2026-02-13", "event_name": "player_died", "event_count": 44}]),
            _FakeResult([{"bucket_day": "2026-02-13", "action": "warn", "action_count": 3}]),
            _FakeResult([{"bucket_day": "2026-02-13", "channel": "ChatAll", "message_count": 18}]),
        ]
        query_helper = helper(
            session_factory=lambda: _SessionContext(session),
            default_window_days=7,
            default_limit=90,
        )

        snapshot = await query_helper.dashboard_snapshot(window_days=3, limit=25)

        assert snapshot["population_daily"][0]["sessions_started"] == 14
        assert snapshot["event_volume_daily"][0]["event_name"] == "player_died"
        assert snapshot["moderation_daily"][0]["action"] == "warn"
        assert snapshot["chat_volume_daily"][0]["channel"] == "ChatAll"
        assert session.execute.await_count == 4

        executed_sql = [str(call.args[0]) for call in session.execute.await_args_list]
        assert any("db_log_mv_population_daily" in sql for sql in executed_sql)
        assert any("db_log_mv_event_volume_daily" in sql for sql in executed_sql)
        assert any("db_log_mv_moderation_daily" in sql for sql in executed_sql)
        assert any("db_log_mv_chat_volume_daily" in sql for sql in executed_sql)

    async def test_dashboard_snapshot_uses_default_window_and_limit_when_invalid(self):
        module = _load_analytics_module()
        helper = module.DbLogAnalyticsQueryHelper
        session = AsyncMock()
        session.execute.side_effect = [
            _FakeResult([]),
            _FakeResult([]),
            _FakeResult([]),
            _FakeResult([]),
        ]
        query_helper = helper(
            session_factory=lambda: _SessionContext(session),
            default_window_days=9,
            default_limit=17,
        )
        query_helper._utc_now = lambda: datetime(2026, 2, 14, 9, 30, 0)

        await query_helper.dashboard_snapshot(window_days=0, limit=-1)

        for call in session.execute.await_args_list:
            params = call.args[1]
            assert params["limit"] == 17
            assert params["since"].startswith("2026-02-05")
