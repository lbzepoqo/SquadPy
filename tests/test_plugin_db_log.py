"""Tests for DBLog plugin schema bootstrap."""

import importlib.util
import sys
from datetime import datetime, timedelta
from importlib.abc import Loader
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from squadpy.database import Base


_PLUGIN_MODULE = None


def _load_plugin_module():
    global _PLUGIN_MODULE
    if _PLUGIN_MODULE is not None:
        return _PLUGIN_MODULE

    spec = importlib.util.spec_from_file_location(
        "db_log",
        Path(__file__).parent.parent / "plugins" / "db_log" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _PLUGIN_MODULE = module
    return module


def _load_plugin_class():
    return _load_plugin_module().DbLog


def _db_mock_with_session(mock_session: AsyncMock):
    session_context = AsyncMock()
    session_context.__aenter__.return_value = mock_session
    session_context.__aexit__.return_value = False
    return SimpleNamespace(
        driver="sqlite",
        sqlite_path=":memory:",
        create_tables=AsyncMock(),
        session=lambda: session_context,
    )


class TestDbLog:
    def test_schema_registers_expected_tables_and_indexes(self):
        """DBLog metadata exposes required core tables and index names."""
        _load_plugin_module()

        tables = set(Base.metadata.tables.keys())
        indexes = {
            index.name
            for table in Base.metadata.tables.values()
            for index in table.indexes
            if index.name
        }

        expected_tables = {
            "db_log_matches",
            "db_log_players",
            "db_log_sessions",
            "db_log_events",
            "db_log_admin_actions",
            "db_log_chat_messages",
        }
        expected_indexes = {
            "ix_db_log_matches_started_at",
            "ix_db_log_players_steam_id",
            "ix_db_log_players_eos_id",
            "ix_db_log_sessions_match_id",
            "ix_db_log_sessions_player_id",
            "ix_db_log_sessions_joined_at",
            "ix_db_log_events_event_name",
            "ix_db_log_events_occurred_at",
            "ix_db_log_events_match_id",
            "ix_db_log_events_player_id",
            "ix_db_log_events_event_name_occurred_at",
            "ix_db_log_admin_actions_created_at",
            "ix_db_log_admin_actions_action",
            "ix_db_log_admin_actions_admin_steam_id",
            "ix_db_log_admin_actions_target_steam_id",
            "ix_db_log_chat_messages_created_at",
            "ix_db_log_chat_messages_channel",
            "ix_db_log_chat_messages_player_id",
        }

        assert expected_tables.issubset(tables)
        assert expected_indexes.issubset(indexes)

    async def test_on_enable_calls_create_tables(self):
        cls = _load_plugin_class()
        mock_db = AsyncMock()
        plugin = cls(db=mock_db, config={})
        await plugin.on_enable()
        mock_db.create_tables.assert_awaited_once()

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "DB Log"
        assert "db" in cls.requires
        assert ("run_prune_jobs", 60) in cls.get_periodic_tasks()

    async def test_on_enable_requires_database_manager(self):
        cls = _load_plugin_class()
        plugin = cls(db=None, config={})
        with pytest.raises(RuntimeError, match="Database manager is not available"):
            await plugin.on_enable()

    async def test_prune_jobs_respect_retention_windows(self):
        module = _load_plugin_module()
        cls = module.DbLog
        mock_session = AsyncMock()
        mock_session.execute.return_value = SimpleNamespace(rowcount=0)
        mock_db = _db_mock_with_session(mock_session)

        plugin = cls(
            db=mock_db,
            config={
                "retention_matches_days": 0,
                "retention_sessions_days": 10,
                "retention_events_days": 5,
                "retention_admin_actions_days": 20,
                "retention_chat_messages_days": 15,
            },
        )
        await plugin.on_enable()

        now = datetime(2026, 2, 14, 12, 0, 0)
        await plugin._prune_rows(now)

        assert mock_session.execute.await_count == 4
        assert mock_session.commit.await_count == 1

        expected = {
            "db_log_sessions": ("joined_at", 10),
            "db_log_events": ("occurred_at", 5),
            "db_log_admin_actions": ("created_at", 20),
            "db_log_chat_messages": ("created_at", 15),
        }
        for call in mock_session.execute.await_args_list:
            statement = call.args[0]
            table_name = statement.table.name
            assert table_name in expected

            column_name, days = expected[table_name]
            where_criteria = list(statement._where_criteria)
            assert len(where_criteria) == 1
            criterion = where_criteria[0]
            assert criterion.left.name == column_name
            assert criterion.right.value == now - timedelta(days=days)

    async def test_prune_jobs_skip_tables_with_disabled_retention(self):
        module = _load_plugin_module()
        cls = module.DbLog
        mock_session = AsyncMock()
        mock_db = _db_mock_with_session(mock_session)

        plugin = cls(
            db=mock_db,
            config={
                "retention_matches_days": 0,
                "retention_sessions_days": 0,
                "retention_events_days": 0,
                "retention_admin_actions_days": 0,
                "retention_chat_messages_days": 0,
            },
        )
        await plugin.on_enable()

        await plugin._prune_rows(datetime(2026, 2, 14, 13, 0, 0))

        mock_session.execute.assert_not_awaited()
        mock_session.commit.assert_awaited_once()

    async def test_prune_jobs_can_be_disabled(self):
        module = _load_plugin_module()
        cls = module.DbLog
        mock_db = SimpleNamespace(
            driver="sqlite",
            sqlite_path=":memory:",
            create_tables=AsyncMock(),
            session=lambda: None,
        )
        plugin = cls(
            db=mock_db,
            config={
                "prune_enabled": False,
                "retention_events_days": 1,
            },
        )
        await plugin.on_enable()

        plugin._prune_rows = AsyncMock(return_value={})
        now = datetime(2026, 2, 14, 14, 0, 0)
        plugin._utcnow = lambda: now
        plugin._next_prune_at = now
        await plugin.run_prune_jobs()

        plugin._prune_rows.assert_not_awaited()

    async def test_dashboard_snapshot_delegates_to_analytics_helper(self):
        cls = _load_plugin_class()
        mock_db = SimpleNamespace(
            driver="sqlite",
            sqlite_path=":memory:",
            create_tables=AsyncMock(),
            session=lambda: None,
        )
        plugin = cls(db=mock_db, config={})
        await plugin.on_enable()

        expected = {"population_daily": [], "event_volume_daily": [], "moderation_daily": [], "chat_volume_daily": []}
        plugin._analytics_helper.dashboard_snapshot = AsyncMock(return_value=expected)

        result = await plugin.dashboard_snapshot(window_days=14, limit=120)

        assert result == expected
        plugin._analytics_helper.dashboard_snapshot.assert_awaited_once_with(
            window_days=14,
            limit=120,
        )
