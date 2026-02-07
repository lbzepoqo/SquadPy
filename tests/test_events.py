"""Tests for the async event bus."""

import asyncio
from dataclasses import dataclass

import pytest

from squadpy.events.emitter import EventBus
from squadpy.events.types import BaseEvent


@dataclass
class FakeEvent(BaseEvent):
    event_name: str = "fake_event"
    value: str = ""


class TestEventBus:
    @pytest.fixture
    def bus(self):
        return EventBus()

    async def test_subscribe_and_emit(self, bus):
        received = []

        async def handler(event: FakeEvent):
            received.append(event)

        bus.subscribe("fake_event", handler)
        event = FakeEvent(value="hello")
        await bus.emit(event)
        assert len(received) == 1
        assert received[0].value == "hello"

    async def test_multiple_subscribers(self, bus):
        received_a = []
        received_b = []

        async def handler_a(event):
            received_a.append(event)

        async def handler_b(event):
            received_b.append(event)

        bus.subscribe("fake_event", handler_a)
        bus.subscribe("fake_event", handler_b)
        await bus.emit(FakeEvent(value="test"))
        assert len(received_a) == 1
        assert len(received_b) == 1

    async def test_unsubscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("fake_event", handler)
        bus.unsubscribe("fake_event", handler)
        await bus.emit(FakeEvent(value="ignored"))
        assert len(received) == 0

    async def test_emit_unknown_event_does_nothing(self, bus):
        await bus.emit(FakeEvent(value="nobody listening"))

    async def test_handler_error_does_not_break_others(self, bus):
        received = []

        async def bad_handler(event):
            raise ValueError("boom")

        async def good_handler(event):
            received.append(event)

        bus.subscribe("fake_event", bad_handler)
        bus.subscribe("fake_event", good_handler)
        await bus.emit(FakeEvent(value="still works"))
        assert len(received) == 1

    async def test_handler_error_is_logged(self, bus, caplog):
        async def bad_handler(event):
            raise ValueError("test error")

        bus.subscribe("fake_event", bad_handler)
        with caplog.at_level("ERROR", logger="squadpy.events"):
            await bus.emit(FakeEvent(value="trigger"))
        assert "test error" in caplog.text
