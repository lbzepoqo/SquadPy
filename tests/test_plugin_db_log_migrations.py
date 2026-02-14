"""Tests for DBLog sqlite migrations."""

import sqlite3

from plugins.db_log.migrations import (
    LATEST_DB_LOG_SCHEMA_VERSION,
    apply_sqlite_migrations,
    sqlite_schema_version,
)


class TestDbLogMigrations:
    def test_clean_bootstrap_applies_all_versions_and_schema(self, tmp_path):
        """Empty sqlite database bootstraps to latest DBLog schema version."""
        db_path = tmp_path / "db_log_clean.sqlite"

        assert sqlite_schema_version(db_path) == 0
        applied = apply_sqlite_migrations(db_path)

        assert applied == [1, 2]
        assert sqlite_schema_version(db_path) == LATEST_DB_LOG_SCHEMA_VERSION

        conn = sqlite3.connect(db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'",
                ).fetchall()
            }
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'",
                ).fetchall()
                if row[0] and not str(row[0]).startswith("sqlite_autoindex")
            }
        finally:
            conn.close()

        expected_tables = {
            "db_log_schema_migrations",
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

    def test_forward_migration_from_v1_to_latest(self, tmp_path):
        """Applying migrations incrementally upgrades from older version."""
        db_path = tmp_path / "db_log_forward.sqlite"

        applied_v1 = apply_sqlite_migrations(db_path, target_version=1)
        assert applied_v1 == [1]
        assert sqlite_schema_version(db_path) == 1

        applied_v2 = apply_sqlite_migrations(db_path)
        assert applied_v2 == [2]
        assert sqlite_schema_version(db_path) == LATEST_DB_LOG_SCHEMA_VERSION

        applied_again = apply_sqlite_migrations(db_path)
        assert applied_again == []
