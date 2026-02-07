"""Tests for Discord integration with plugin loader."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.plugin import Plugin, on_event, slash_command, on_discord
from squadpy.plugin_loader import PluginLoader, PluginStatus, LoadedPlugin


class DiscordTestPlugin(Plugin):
    name = "Discord Test"
    requires = ["rcon", "discord"]

    @slash_command(name="hello", description="Say hello")
    async def hello_cmd(self, interaction):
        pass

    @on_discord("button_click", custom_id="click_me")
    async def handle_click(self, interaction):
        pass

    @on_event("test_event")
    async def handle_test(self, event):
        pass


class TestLoadedPluginDiscordFields:
    def test_loaded_plugin_has_slash_commands(self):
        lp = LoadedPlugin(
            name="Test", dir_name="test",
            status=PluginStatus.ENABLED,
            slash_commands=[({"name": "hello"}, "hello_cmd")],
        )
        assert len(lp.slash_commands) > 0

    def test_loaded_plugin_has_discord_handlers(self):
        lp = LoadedPlugin(
            name="Test", dir_name="test",
            status=PluginStatus.ENABLED,
            discord_handlers=[({"event_type": "button_click"}, "handle_click")],
        )
        assert len(lp.discord_handlers) > 0


class TestPluginLoaderDiscordScanning:
    def test_get_slash_commands_from_class(self):
        commands = DiscordTestPlugin.get_slash_commands()
        assert len(commands) == 1
        meta, method_name = commands[0]
        assert meta["name"] == "hello"
        assert method_name == "hello_cmd"

    def test_get_discord_handlers_from_class(self):
        handlers = DiscordTestPlugin.get_discord_handlers()
        assert len(handlers) == 1
        meta, method_name = handlers[0]
        assert meta["event_type"] == "button_click"
        assert meta["custom_id"] == "click_me"


class TestPluginRequiresDiscord:
    async def test_plugin_requiring_discord_fails_without_it(self):
        """Plugin with requires=['discord'] fails when discord service is None."""
        services = {
            "rcon": MagicMock(),
            "discord": None,
            "db": None,
            "server": MagicMock(),
        }
        loader = PluginLoader(
            plugins_dir=Path(__file__).parent / "fixtures" / "plugins",
            config_dir=Path(__file__).parent / "fixtures" / "config" / "plugins",
        )
        # The good_plugin requires ["rcon"] so it should still load
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert good.status == PluginStatus.ENABLED
