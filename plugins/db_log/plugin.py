"""DBLog - structured persistence schema for moderation and analytics events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from squadpy.database import Base
from squadpy.plugin import Plugin, periodic
from plugins.db_log.migrations import apply_sqlite_migrations


class DbLogMatch(Base):
    __tablename__ = "db_log_matches"
    __table_args__ = (
        Index("ix_db_log_matches_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(128), default="")
    layer: Mapped[str] = mapped_column(String(128), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    winner: Mapped[str] = mapped_column(String(64), default="")
    winner_tickets: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DbLogPlayer(Base):
    __tablename__ = "db_log_players"
    __table_args__ = (
        Index("ix_db_log_players_steam_id", "steam_id", unique=True),
        Index("ix_db_log_players_eos_id", "eos_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    steam_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    eos_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_name: Mapped[str] = mapped_column(String(128), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DbLogSession(Base):
    __tablename__ = "db_log_sessions"
    __table_args__ = (
        Index("ix_db_log_sessions_match_id", "match_id"),
        Index("ix_db_log_sessions_player_id", "player_id"),
        Index("ix_db_log_sessions_joined_at", "joined_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("db_log_matches.id"), nullable=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("db_log_players.id"))
    team_id: Mapped[int] = mapped_column(Integer, default=0)
    squad_id: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DbLogEvent(Base):
    __tablename__ = "db_log_events"
    __table_args__ = (
        Index("ix_db_log_events_event_name", "event_name"),
        Index("ix_db_log_events_occurred_at", "occurred_at"),
        Index("ix_db_log_events_match_id", "match_id"),
        Index("ix_db_log_events_player_id", "player_id"),
        Index("ix_db_log_events_event_name_occurred_at", "event_name", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("db_log_matches.id"), nullable=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("db_log_players.id"), nullable=True)
    steam_id: Mapped[str] = mapped_column(String(32), default="")
    eos_id: Mapped[str] = mapped_column(String(32), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class DbLogAdminAction(Base):
    __tablename__ = "db_log_admin_actions"
    __table_args__ = (
        Index("ix_db_log_admin_actions_created_at", "created_at"),
        Index("ix_db_log_admin_actions_action", "action"),
        Index("ix_db_log_admin_actions_admin_steam_id", "admin_steam_id"),
        Index("ix_db_log_admin_actions_target_steam_id", "target_steam_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    action: Mapped[str] = mapped_column(String(64))
    admin_steam_id: Mapped[str] = mapped_column(String(32), default="")
    target_steam_id: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")


class DbLogChatMessage(Base):
    __tablename__ = "db_log_chat_messages"
    __table_args__ = (
        Index("ix_db_log_chat_messages_created_at", "created_at"),
        Index("ix_db_log_chat_messages_channel", "channel"),
        Index("ix_db_log_chat_messages_player_id", "player_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    channel: Mapped[str] = mapped_column(String(32))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("db_log_players.id"), nullable=True)
    steam_id: Mapped[str] = mapped_column(String(32), default="")
    eos_id: Mapped[str] = mapped_column(String(32), default="")
    player_name: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(Text, default="")


class DbLog(Plugin):
    name = "DB Log"
    description = "Creates DBLog-compatible core persistence schema"
    requires = ["db"]
    _DEFAULT_PRUNE_INTERVAL_SECONDS = 3600.0
    _DEFAULT_RETENTION_DAYS = {
        "matches": 30,
        "sessions": 30,
        "events": 30,
        "admin_actions": 90,
        "chat_messages": 30,
    }

    async def on_enable(self):
        if self.db is None:
            raise RuntimeError("Database manager is not available")

        if self.db.driver == "sqlite":
            sqlite_path = self.db.sqlite_path
            if sqlite_path and sqlite_path != ":memory:":
                applied = apply_sqlite_migrations(Path(sqlite_path))
                if applied:
                    self.logger.info("Applied db_log migrations: %s", applied)

        await self.db.create_tables()
        self._prune_enabled = self._parse_bool(
            self.config.get("prune_enabled", True),
            True,
        )
        self._prune_interval_seconds = self._non_negative_float(
            self.config.get("prune_interval_seconds", self._DEFAULT_PRUNE_INTERVAL_SECONDS),
            self._DEFAULT_PRUNE_INTERVAL_SECONDS,
        )
        self._retention_days = {
            "matches": self._retention_days_for("retention_matches_days"),
            "sessions": self._retention_days_for("retention_sessions_days"),
            "events": self._retention_days_for("retention_events_days"),
            "admin_actions": self._retention_days_for("retention_admin_actions_days"),
            "chat_messages": self._retention_days_for("retention_chat_messages_days"),
        }
        self._next_prune_at = self._utcnow()
        self.logger.info("DB log core schema ensured")

    @periodic(seconds=60)
    async def run_prune_jobs(self):
        if not self._prune_enabled:
            return

        now = self._utcnow()
        if now < self._next_prune_at:
            return

        deleted = await self._prune_rows(now)
        self._next_prune_at = now + timedelta(seconds=self._prune_interval_seconds)
        total_deleted = sum(deleted.values())
        if total_deleted <= 0:
            return

        details = ", ".join(
            f"{table_name}={count}"
            for table_name, count in deleted.items()
            if count > 0
        )
        self.logger.info("DB log prune removed %s rows (%s)", total_deleted, details)

    async def _prune_rows(self, now: datetime) -> dict[str, int]:
        if self.db is None:
            raise RuntimeError("Database manager is not available")

        deleted_rows = {
            "matches": 0,
            "sessions": 0,
            "events": 0,
            "admin_actions": 0,
            "chat_messages": 0,
        }

        async with self.db.session() as session:
            deleted_rows["sessions"] = await self._delete_older_than(
                session,
                model=DbLogSession,
                timestamp_column=DbLogSession.joined_at,
                retention_days=self._retention_days["sessions"],
                now=now,
            )
            deleted_rows["events"] = await self._delete_older_than(
                session,
                model=DbLogEvent,
                timestamp_column=DbLogEvent.occurred_at,
                retention_days=self._retention_days["events"],
                now=now,
            )
            deleted_rows["admin_actions"] = await self._delete_older_than(
                session,
                model=DbLogAdminAction,
                timestamp_column=DbLogAdminAction.created_at,
                retention_days=self._retention_days["admin_actions"],
                now=now,
            )
            deleted_rows["chat_messages"] = await self._delete_older_than(
                session,
                model=DbLogChatMessage,
                timestamp_column=DbLogChatMessage.created_at,
                retention_days=self._retention_days["chat_messages"],
                now=now,
            )

            retention_matches = self._retention_days["matches"]
            if retention_matches > 0:
                matches_cutoff = now - timedelta(days=retention_matches)
                stale_match_ids = list(
                    (
                        await session.scalars(
                            select(DbLogMatch.id).where(DbLogMatch.started_at < matches_cutoff)
                        )
                    ).all()
                )
                if stale_match_ids:
                    referenced_match_ids = set(
                        (
                            await session.scalars(
                                select(DbLogSession.match_id).where(
                                    DbLogSession.match_id.is_not(None),
                                    DbLogSession.match_id.in_(stale_match_ids),
                                )
                            )
                        ).all()
                    )
                    referenced_match_ids.update(
                        (
                            await session.scalars(
                                select(DbLogEvent.match_id).where(
                                    DbLogEvent.match_id.is_not(None),
                                    DbLogEvent.match_id.in_(stale_match_ids),
                                )
                            )
                        ).all()
                    )
                    prunable_match_ids = [
                        match_id
                        for match_id in stale_match_ids
                        if match_id not in referenced_match_ids
                    ]
                    if prunable_match_ids:
                        result = await session.execute(
                            delete(DbLogMatch).where(DbLogMatch.id.in_(prunable_match_ids))
                        )
                        deleted_rows["matches"] = self._normalized_rowcount(result.rowcount)

            await session.commit()

        return deleted_rows

    async def _delete_older_than(
        self,
        session,
        *,
        model,
        timestamp_column,
        retention_days: int,
        now: datetime,
    ) -> int:
        if retention_days <= 0:
            return 0

        cutoff = now - timedelta(days=retention_days)
        result = await session.execute(
            delete(model).where(timestamp_column < cutoff)
        )
        return self._normalized_rowcount(result.rowcount)

    def _retention_days_for(self, config_key: str) -> int:
        default_days = self._DEFAULT_RETENTION_DAYS[config_key.removeprefix("retention_").removesuffix("_days")]
        try:
            parsed = int(self.config.get(config_key, default_days))
        except (TypeError, ValueError):
            return default_days
        return parsed if parsed >= 0 else default_days

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _normalized_rowcount(rowcount: int | None) -> int:
        if rowcount is None:
            return 0
        return max(0, int(rowcount))

    @staticmethod
    def _non_negative_float(value, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 0 else default

    @staticmethod
    def _parse_bool(value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default
