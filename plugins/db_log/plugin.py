"""DBLog - structured persistence schema for moderation and analytics events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from squadpy.database import Base
from squadpy.plugin import Plugin


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

    async def on_enable(self):
        if self.db is None:
            raise RuntimeError("Database manager is not available")
        await self.db.create_tables()
        self.logger.info("DB log core schema ensured")
