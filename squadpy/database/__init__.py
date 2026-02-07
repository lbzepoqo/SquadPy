"""Database module — exports Base and DatabaseManager."""

from squadpy.database.models import Base
from squadpy.database.manager import DatabaseManager

__all__ = ["Base", "DatabaseManager"]
