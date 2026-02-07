"""Base event type and core event definitions."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BaseEvent:
    """Base class for all SquadPy events."""
    event_name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
