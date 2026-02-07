"""SquadPy — Python-based Squad game server management framework."""

from squadpy.plugin import Plugin, on_event, periodic
from squadpy.events.types import BaseEvent
from squadpy.server import VERSION as __version__

__all__ = ["Plugin", "on_event", "periodic", "BaseEvent", "__version__"]
