"""Tests for database module."""

import pytest
from sqlalchemy.orm import DeclarativeBase

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
