"""Database manager — engine, sessions, lifecycle."""

import logging
from pathlib import Path
from urllib.parse import quote_plus

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
        self._driver: str | None = None
        self._sqlite_path: str | None = None

    @property
    def driver(self) -> str | None:
        return self._driver

    @property
    def sqlite_path(self) -> str | None:
        return self._sqlite_path

    def _build_url(self, config: DatabaseConfig) -> str:
        dialect = _DRIVER_MAP[config.driver]
        if config.driver == "sqlite":
            return f"{dialect}:///{config.path}"
        username = quote_plus(config.username or "")
        password = quote_plus(config.password or "")
        return f"{dialect}://{username}:{password}@{config.host}:{config.port}/{config.database}"

    async def initialize(self, config: DatabaseConfig) -> None:
        url = self._build_url(config)
        self._driver = config.driver
        self._sqlite_path = config.path if config.driver == "sqlite" else None
        connect_args = {}
        kwargs = {}
        if config.driver == "sqlite":
            connect_args["check_same_thread"] = False
            if config.path == ":memory:" or url.endswith(":///"):
                from sqlalchemy.pool import StaticPool
                kwargs["poolclass"] = StaticPool
        else:
            kwargs["pool_pre_ping"] = True

        if config.driver == "sqlite" and config.path != ":memory:":
            db_path = Path(config.path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_async_engine(url, connect_args=connect_args, **kwargs)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        logger.info("Database initialized: %s", url.split("://")[0])

    def session(self) -> AsyncSession:
        if self._session_factory is None:
            raise RuntimeError("Database not initialized")
        return self._session_factory()

    async def create_tables(self) -> None:
        if self._engine is None:
            raise RuntimeError("Database not initialized")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    async def shutdown(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._driver = None
            self._sqlite_path = None
            logger.info("Database shut down")
