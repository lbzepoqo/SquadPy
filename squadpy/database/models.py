"""Shared declarative base for all plugin models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
