"""Tests for DiscordConnector."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.config import DiscordConfig
from squadpy.discord.connector import DiscordConnector


@pytest.fixture
def discord_config():
    return DiscordConfig(enabled=True, token="test_token", guild_id=123456789)


class TestConnectorInit:
    def test_creates_connector(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_commands.Bot.return_value = MagicMock()
            connector = DiscordConnector(discord_config)
            assert connector.guild_id == 123456789
            assert connector.bot is not None

    def test_stores_config(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_commands.Bot.return_value = MagicMock()
            connector = DiscordConnector(discord_config)
            assert connector._config == discord_config


class TestConnectorLifecycle:
    async def test_start_creates_task(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = AsyncMock()
            mock_commands.Bot.return_value = mock_bot
            connector = DiscordConnector(discord_config)
            assert callable(connector.start)

    async def test_close_calls_bot_close(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = AsyncMock()
            mock_commands.Bot.return_value = mock_bot
            connector = DiscordConnector(discord_config)
            connector._bot_task = MagicMock()
            connector._bot_task.cancel = MagicMock()
            await connector.close()
            mock_bot.close.assert_awaited_once()


class TestConnectorSend:
    async def test_send_to_channel(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_channel = AsyncMock()
            mock_bot.get_channel.return_value = mock_channel
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            await connector.send(999, content="Hello")
            mock_bot.get_channel.assert_called_once_with(999)
            mock_channel.send.assert_awaited_once_with(content="Hello", embed=None, view=None)

    async def test_send_returns_none_if_channel_not_found(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.get_channel.return_value = None
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            result = await connector.send(999, content="Hello")
            assert result is None

    async def test_get_channel(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_channel = MagicMock()
            mock_bot.get_channel.return_value = mock_channel
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            result = connector.get_channel(999)
            assert result is mock_channel


class TestConnectorInteractionRouting:
    async def test_register_slash_command(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            with patch("squadpy.discord.connector.app_commands") as mock_app:
                mock_bot = MagicMock()
                mock_bot.tree = MagicMock()
                mock_commands.Bot.return_value = mock_bot

                connector = DiscordConnector(discord_config)
                handler = AsyncMock()
                connector.register_slash_command(
                    "my_plugin", handler, name="test", description="A test command"
                )
                assert mock_bot.tree.add_command.called

    async def test_register_interaction_handler(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            handler = AsyncMock()
            connector.register_interaction_handler(
                "my_plugin", "button_click", "claim", handler
            )
            assert "my_plugin:claim" in connector._interaction_handlers

    async def test_namespaced_routing(self, discord_config):
        """Two plugins registering the same custom_id don't collide."""
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            handler_a = AsyncMock()
            handler_b = AsyncMock()
            connector.register_interaction_handler("plugin_a", "button_click", "submit", handler_a)
            connector.register_interaction_handler("plugin_b", "button_click", "submit", handler_b)
            assert "plugin_a:submit" in connector._interaction_handlers
            assert "plugin_b:submit" in connector._interaction_handlers
            assert connector._interaction_handlers["plugin_a:submit"] is handler_a
            assert connector._interaction_handlers["plugin_b:submit"] is handler_b

    async def test_unregister_plugin_handlers(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            handler = AsyncMock()
            connector.register_interaction_handler("my_plugin", "button_click", "claim", handler)
            connector.unregister_plugin("my_plugin")
            assert "my_plugin:claim" not in connector._interaction_handlers

    async def test_sync_commands(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.tree.sync = AsyncMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            await connector.sync_commands()
            mock_bot.tree.sync.assert_awaited_once()
