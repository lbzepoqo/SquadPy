"""Plugin base class and decorators."""

import logging
from typing import Any


def on_event(event_name: str):
    """Decorator to subscribe a plugin method to an event."""
    def decorator(func):
        func._squadpy_event = event_name
        return func
    return decorator


def periodic(seconds: float):
    """Decorator to run a plugin method on an interval."""
    def decorator(func):
        func._squadpy_periodic = seconds
        return func
    return decorator


VALID_DISCORD_EVENT_TYPES = {"button_click", "select_menu", "modal_submit", "thread_message"}


def slash_command(name: str, description: str = ""):
    """Decorator to register a plugin method as a Discord slash command."""
    def decorator(func):
        func._squadpy_slash_command = {"name": name, "description": description}
        return func
    return decorator


def on_discord(event_type: str, custom_id: str | None = None):
    """Decorator to register a plugin method as a Discord interaction handler."""
    if event_type not in VALID_DISCORD_EVENT_TYPES:
        raise ValueError(
            f"Unknown discord event type: {event_type}. "
            f"Valid types: {VALID_DISCORD_EVENT_TYPES}"
        )
    def decorator(func):
        func._squadpy_on_discord = {"event_type": event_type, "custom_id": custom_id}
        return func
    return decorator


class Plugin:
    """Base class for all SquadPy plugins."""

    name: str = ""
    description: str = ""
    requires: list[str] = []

    def __init__(
        self,
        rcon: Any = None,
        discord: Any = None,
        db: Any = None,
        config: dict = None,
        server: Any = None,
    ):
        self.rcon = rcon
        self.discord = discord
        self.db = db
        self.config = config or {}
        self.server = server
        plugin_id = self.name.lower().replace(" ", "_") or self.__class__.__name__.lower()
        self.logger = logging.getLogger(f"squadpy.plugins.{plugin_id}")

    async def on_enable(self) -> None:
        """Called when the plugin is enabled. Override in subclass."""

    async def on_disable(self) -> None:
        """Called when the plugin is disabled. Override in subclass."""

    @classmethod
    def get_event_handlers(cls) -> list[tuple[str, str]]:
        """Return list of (event_name, method_name) for all @on_event methods."""
        handlers = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if callable(attr) and hasattr(attr, "_squadpy_event"):
                handlers.append((attr._squadpy_event, attr_name))
        return handlers

    @classmethod
    def get_periodic_tasks(cls) -> list[tuple[str, float]]:
        """Return list of (method_name, interval_seconds) for all @periodic methods."""
        tasks = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if callable(attr) and hasattr(attr, "_squadpy_periodic"):
                tasks.append((attr_name, attr._squadpy_periodic))
        return tasks

    @classmethod
    def get_slash_commands(cls) -> list[tuple[dict, str]]:
        """Return list of (meta_dict, method_name) for all @slash_command methods."""
        commands = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if callable(attr) and hasattr(attr, "_squadpy_slash_command"):
                commands.append((attr._squadpy_slash_command, attr_name))
        return commands

    @classmethod
    def get_discord_handlers(cls) -> list[tuple[dict, str]]:
        """Return list of (meta_dict, method_name) for all @on_discord methods."""
        handlers = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if callable(attr) and hasattr(attr, "_squadpy_on_discord"):
                handlers.append((attr._squadpy_on_discord, attr_name))
        return handlers
