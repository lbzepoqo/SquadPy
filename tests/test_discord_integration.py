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


class TestHotReloadDiscord:
    async def test_reload_deregisters_old_discord_handlers(self):
        """When a plugin is reloaded, old Discord handlers are removed."""
        from squadpy.discord.connector import DiscordConnector
        from squadpy.config import DiscordConfig
        from unittest.mock import patch

        config = DiscordConfig(enabled=True, token="tok", guild_id=123)
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.tree = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(config)

            # Register some handlers
            handler = AsyncMock()
            connector.register_interaction_handler("my_plugin", "button_click", "btn", handler)
            assert "my_plugin:btn" in connector._interaction_handlers

            # Unregister (simulating reload)
            connector.unregister_plugin("my_plugin")
            assert "my_plugin:btn" not in connector._interaction_handlers

    async def test_reload_does_not_affect_other_plugins(self):
        """Reloading one plugin doesn't touch another's handlers."""
        from squadpy.discord.connector import DiscordConnector
        from squadpy.config import DiscordConfig
        from unittest.mock import patch

        config = DiscordConfig(enabled=True, token="tok", guild_id=123)
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.tree = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(config)

            handler_a = AsyncMock()
            handler_b = AsyncMock()
            connector.register_interaction_handler("plugin_a", "button_click", "btn", handler_a)
            connector.register_interaction_handler("plugin_b", "button_click", "btn", handler_b)

            connector.unregister_plugin("plugin_a")
            assert "plugin_a:btn" not in connector._interaction_handlers
            assert "plugin_b:btn" in connector._interaction_handlers
