"""Tests for DBLog plugin schema bootstrap."""

import importlib.util
import sys
from importlib.abc import Loader
from pathlib import Path
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

    async def test_on_enable_requires_database_manager(self):
        cls = _load_plugin_class()
        plugin = cls(db=None, config={})
        with pytest.raises(RuntimeError, match="Database manager is not available"):
            await plugin.on_enable()
