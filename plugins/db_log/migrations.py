"""Versioned sqlite migrations for DBLog schema."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SqliteMigration:
    version: int
    name: str
    statements: tuple[str, ...]


LATEST_DB_LOG_SCHEMA_VERSION = 2


SQLITE_MIGRATIONS: tuple[SqliteMigration, ...] = (
    SqliteMigration(
        version=1,
        name="create_core_tables",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS db_log_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS db_log_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL DEFAULT '',
                layer TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                winner TEXT NOT NULL DEFAULT '',
                winner_tickets INTEGER
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS db_log_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steam_id TEXT,
                eos_id TEXT,
                last_name TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS db_log_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                player_id INTEGER NOT NULL,
                team_id INTEGER NOT NULL DEFAULT 0,
                squad_id INTEGER NOT NULL DEFAULT 0,
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                left_at TEXT,
                FOREIGN KEY(match_id) REFERENCES db_log_matches(id),
                FOREIGN KEY(player_id) REFERENCES db_log_players(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS db_log_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                match_id INTEGER,
                player_id INTEGER,
                steam_id TEXT NOT NULL DEFAULT '',
                eos_id TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(match_id) REFERENCES db_log_matches(id),
                FOREIGN KEY(player_id) REFERENCES db_log_players(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS db_log_admin_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                admin_steam_id TEXT NOT NULL DEFAULT '',
                target_steam_id TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS db_log_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                channel TEXT NOT NULL,
                player_id INTEGER,
                steam_id TEXT NOT NULL DEFAULT '',
                eos_id TEXT NOT NULL DEFAULT '',
                player_name TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(player_id) REFERENCES db_log_players(id)
            );
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_db_log_players_steam_id ON db_log_players (steam_id);",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_db_log_players_eos_id ON db_log_players (eos_id);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_matches_started_at ON db_log_matches (started_at);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_sessions_match_id ON db_log_sessions (match_id);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_sessions_player_id ON db_log_sessions (player_id);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_events_event_name ON db_log_events (event_name);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_events_occurred_at ON db_log_events (occurred_at);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_events_match_id ON db_log_events (match_id);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_events_player_id ON db_log_events (player_id);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_admin_actions_created_at ON db_log_admin_actions (created_at);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_admin_actions_action ON db_log_admin_actions (action);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_chat_messages_created_at ON db_log_chat_messages (created_at);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_chat_messages_channel ON db_log_chat_messages (channel);",
        ),
    ),
    SqliteMigration(
        version=2,
        name="add_performance_indexes",
        statements=(
            "CREATE INDEX IF NOT EXISTS ix_db_log_sessions_joined_at ON db_log_sessions (joined_at);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_events_event_name_occurred_at ON db_log_events (event_name, occurred_at);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_admin_actions_admin_steam_id ON db_log_admin_actions (admin_steam_id);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_admin_actions_target_steam_id ON db_log_admin_actions (target_steam_id);",
            "CREATE INDEX IF NOT EXISTS ix_db_log_chat_messages_player_id ON db_log_chat_messages (player_id);",
        ),
    ),
)


def apply_sqlite_migrations(
    db_path: str | Path,
    *,
    target_version: int | None = None,
) -> list[int]:
    """Apply pending sqlite migrations and return newly applied versions."""
    path = str(db_path)
    effective_target = target_version or LATEST_DB_LOG_SCHEMA_VERSION
    if effective_target < 1:
        return []

    applied_versions: list[int] = []
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS db_log_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        existing_rows = conn.execute(
            "SELECT version FROM db_log_schema_migrations",
        ).fetchall()
        existing_versions = {int(row[0]) for row in existing_rows}

        for migration in SQLITE_MIGRATIONS:
            if migration.version > effective_target:
                continue
            if migration.version in existing_versions:
                continue

            with conn:
                for statement in migration.statements:
                    conn.execute(statement)
                conn.execute(
                    """
                    INSERT INTO db_log_schema_migrations (version, name)
                    VALUES (?, ?)
                    """,
                    (migration.version, migration.name),
                )
            applied_versions.append(migration.version)
            existing_versions.add(migration.version)
    finally:
        conn.close()

    return applied_versions


def sqlite_schema_version(db_path: str | Path) -> int:
    """Return current sqlite migration version (0 if none)."""
    path = str(db_path)
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(version), 0)
            FROM db_log_schema_migrations
            """,
        ).fetchone()
        if row is None or row[0] is None:
            return 0
        return int(row[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()
