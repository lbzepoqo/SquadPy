"""Tests for database module."""

import pytest
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from squadpy.config import DatabaseConfig
from squadpy.database.manager import DatabaseManager
from squadpy.database.models import Base


class TestBase:
    def test_base_is_declarative(self):
        assert issubclass(Base, DeclarativeBase)

    def test_base_has_metadata(self):
        assert hasattr(Base, "metadata")


class TestURLBuilding:
    def test_sqlite_url(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path="data/test.db")
        mgr = DatabaseManager()
        url = mgr._build_url(config)
        assert url == "sqlite+aiosqlite:///data/test.db"

    def test_postgresql_url(self):
        config = DatabaseConfig(
            enabled=True, driver="postgresql",
            host="localhost", port=5432, username="user", password="pass", database="squad",
        )
        mgr = DatabaseManager()
        url = mgr._build_url(config)
        assert url == "postgresql+asyncpg://user:pass@localhost:5432/squad"

    def test_mysql_url(self):
        config = DatabaseConfig(
            enabled=True, driver="mysql",
            host="db.example.com", port=3306, username="admin", password="secret", database="mydb",
        )
        mgr = DatabaseManager()
        url = mgr._build_url(config)
        assert url == "mysql+aiomysql://admin:secret@db.example.com:3306/mydb"


class _TestRecord(Base):
    __tablename__ = "test_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str]


class TestDatabaseLifecycle:
    async def test_initialize_creates_engine(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        assert mgr._engine is not None
        assert mgr._session_factory is not None
        await mgr.shutdown()

    async def test_create_tables(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.create_tables()
        async with mgr.session() as session:
            session.add(_TestRecord(value="hello"))
            await session.commit()
        async with mgr.session() as session:
            from sqlalchemy import select
            result = await session.execute(select(_TestRecord))
            rows = result.scalars().all()
            assert len(rows) == 1
            assert rows[0].value == "hello"
        await mgr.shutdown()

    async def test_session_no_auto_commit(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.create_tables()
        async with mgr.session() as session:
            session.add(_TestRecord(value="uncommitted"))
        async with mgr.session() as session:
            from sqlalchemy import select
            result = await session.execute(select(_TestRecord))
            rows = result.scalars().all()
            assert len(rows) == 0
        await mgr.shutdown()

    async def test_shutdown_disposes_engine(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.shutdown()
        assert mgr._engine is None
        assert mgr._session_factory is None

    async def test_session_raises_before_initialize(self):
        mgr = DatabaseManager()
        with pytest.raises(RuntimeError, match="not initialized"):
            mgr.session()


class TestExports:
    def test_base_importable_from_package(self):
        from squadpy.database import Base as B
        assert B is Base

    def test_manager_importable_from_package(self):
        from squadpy.database import DatabaseManager as DM
        assert DM is DatabaseManager
