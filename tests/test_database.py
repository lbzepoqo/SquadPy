"""Tests for database module."""

from sqlalchemy.orm import DeclarativeBase

from squadpy.database.models import Base


class TestBase:
    def test_base_is_declarative(self):
        assert issubclass(Base, DeclarativeBase)

    def test_base_has_metadata(self):
        assert hasattr(Base, "metadata")
