"""Async event bus for dispatching events to subscribers."""

import logging
from collections import defaultdict
from typing import Callable, Coroutine, Any

from squadpy.events.types import BaseEvent

logger = logging.getLogger("squadpy.events")

EventHandler = Callable[[BaseEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Async event bus that dispatches events to registered handlers."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: BaseEvent) -> None:
        handlers = self._handlers.get(event.event_name, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Error in handler %s for event %s",
                    handler.__qualname__,
                    event.event_name,
                )

    def clear(self) -> None:
        self._handlers.clear()
