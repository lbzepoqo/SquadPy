"""Database manager — engine, sessions, lifecycle."""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from squadpy.config import DatabaseConfig
from squadpy.database.models import Base

logger = logging.getLogger("squadpy.database")

_DRIVER_MAP = {
    "sqlite": "sqlite+aiosqlite",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
}


class DatabaseManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def _build_url(self, config: DatabaseConfig) -> str:
        dialect = _DRIVER_MAP[config.driver]
        if config.driver == "sqlite":
            return f"{dialect}:///{config.path}"
        return f"{dialect}://{config.username}:{config.password}@{config.host}:{config.port}/{config.database}"
