"""Tests for plugin base class and decorators."""

import asyncio
from unittest.mock import MagicMock

import pytest

from squadpy.plugin import Plugin, on_event, periodic


class SamplePlugin(Plugin):
    name = "Sample"
    description = "A test plugin"
    requires = ["rcon"]

    async def on_enable(self):
        self.enabled_called = True

    async def on_disable(self):
        self.disabled_called = True

    @on_event("player_connected")
    async def handle_connect(self, event):
        self.last_event = event

    @on_event("chat_message")
    async def handle_chat(self, event):
        self.last_chat = event

    @periodic(seconds=5)
    async def check_something(self):
        self.check_called = True


class MinimalPlugin(Plugin):
    name = "Minimal"
    description = "No requirements"


class TestPluginClass:
    @pytest.fixture
    def plugin(self):
        return SamplePlugin(
            rcon=MagicMock(),
            discord=None,
            db=None,
            config={"timeout": 30},
            server=MagicMock(),
        )

    def test_plugin_name(self, plugin):
        assert plugin.name == "Sample"

    def test_plugin_has_rcon(self, plugin):
        assert plugin.rcon is not None

    def test_plugin_has_logger(self, plugin):
        assert plugin.logger.name == "squadpy.plugins.sample"

    def test_plugin_config(self, plugin):
        assert plugin.config["timeout"] == 30

    def test_no_discord_is_none(self, plugin):
        assert plugin.discord is None

    async def test_on_enable(self, plugin):
        await plugin.on_enable()
        assert plugin.enabled_called

    async def test_on_disable(self, plugin):
        await plugin.on_disable()
        assert plugin.disabled_called


class TestOnEventDecorator:
    def test_marks_handler_with_event_name(self):
        p = SamplePlugin(
            rcon=MagicMock(), discord=None, db=None,
            config={}, server=MagicMock(),
        )
        assert hasattr(p.handle_connect, "_squadpy_event")
        assert p.handle_connect._squadpy_event == "player_connected"

    def test_collects_all_event_handlers(self):
        handlers = SamplePlugin.get_event_handlers()
        event_names = {name for name, _ in handlers}
        assert "player_connected" in event_names
        assert "chat_message" in event_names

    def test_handlers_are_callable(self):
        handlers = SamplePlugin.get_event_handlers()
        for _, method_name in handlers:
            assert isinstance(method_name, str)


class TestPeriodicDecorator:
    def test_marks_method_with_interval(self):
        p = SamplePlugin(
            rcon=MagicMock(), discord=None, db=None,
            config={}, server=MagicMock(),
        )
        assert hasattr(p.check_something, "_squadpy_periodic")
        assert p.check_something._squadpy_periodic == 5

    def test_collects_periodic_tasks(self):
        tasks = SamplePlugin.get_periodic_tasks()
        assert len(tasks) == 1
        method_name, interval = tasks[0]
        assert method_name == "check_something"
        assert interval == 5


class TestPluginRequires:
    def test_requires_list(self):
        assert SamplePlugin.requires == ["rcon"]

    def test_no_requires(self):
        assert MinimalPlugin.requires == []
