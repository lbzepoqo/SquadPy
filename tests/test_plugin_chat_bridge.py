"""Tests for DiscordChatBridge plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.events.types import ChatMessage


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_chat_bridge",
        Path(__file__).parent.parent / "plugins" / "discord_chat_bridge" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordChatBridge


class TestDiscordChatBridge:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        mock_discord = AsyncMock()
        mock_discord.bot = MagicMock()

        instance = cls(
            rcon=mock_rcon,
            discord=mock_discord,
            config={
                "channel_id": 12345,
                "chat_channels": ["ChatAll", "ChatTeam"],
                "show_channel_prefix": True,
                "discord_to_game_format": "[Discord] {author}: {message}",
            },
        )
        await instance.on_enable()
        return instance

    async def test_game_chat_in_configured_channel_sent(self, plugin):
        """Game chat in configured channel sent to Discord."""
        event = ChatMessage(
            player_name="PlayerOne",
            steam_id="s",
            eos_id="e",
            channel="ChatAll",
            message="hello from game",
        )
        await plugin.relay_to_discord(event)
        plugin.discord.send.assert_awaited_once()
        args = plugin.discord.send.call_args
        assert "[All]" in args[1]["content"]
        assert "PlayerOne" in args[1]["content"]

    async def test_game_chat_not_in_configured_channel_ignored(self, plugin):
        """Game chat in non-configured channel is ignored."""
        event = ChatMessage(
            player_name="PlayerOne",
            channel="ChatSquad",
            message="squad only",
        )
        await plugin.relay_to_discord(event)
        plugin.discord.send.assert_not_awaited()

    async def test_game_chat_team_channel(self, plugin):
        """ChatTeam is in configured channels."""
        event = ChatMessage(
            player_name="P",
            channel="ChatTeam",
            message="team msg",
        )
        await plugin.relay_to_discord(event)
        plugin.discord.send.assert_awaited_once()
        assert "[Team]" in plugin.discord.send.call_args[1]["content"]

    async def test_discord_to_game_broadcasts(self, plugin):
        """Discord message in bridge channel broadcasts to game."""
        msg = MagicMock()
        msg.channel.id = 12345
        msg.author.bot = False
        msg.author.display_name = "DiscordUser"
        msg.content = "hi from discord"

        await plugin._on_discord_message(msg)
        plugin.rcon.broadcast.assert_awaited_once_with(
            "[Discord] DiscordUser: hi from discord"
        )

    async def test_discord_bot_message_ignored(self, plugin):
        """Bot messages are ignored to prevent echo loops."""
        msg = MagicMock()
        msg.channel.id = 12345
        msg.author.bot = True

        await plugin._on_discord_message(msg)
        plugin.rcon.broadcast.assert_not_awaited()

    async def test_discord_other_channel_ignored(self, plugin):
        """Messages in non-bridge channels are ignored."""
        msg = MagicMock()
        msg.channel.id = 99999
        msg.author.bot = False

        await plugin._on_discord_message(msg)
        plugin.rcon.broadcast.assert_not_awaited()

    async def test_on_enable_adds_listener(self, plugin):
        """on_enable registers on_message listener."""
        plugin.discord.bot.add_listener.assert_called_once()

    async def test_on_disable_removes_listener(self, plugin):
        """on_disable removes on_message listener."""
        await plugin.on_disable()
        plugin.discord.bot.remove_listener.assert_called_once()

    async def test_no_prefix_mode(self):
        """show_channel_prefix=False omits channel prefix."""
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            discord=AsyncMock(),
            config={
                "channel_id": 12345,
                "chat_channels": ["ChatAll"],
                "show_channel_prefix": False,
            },
        )
        instance.discord.bot = MagicMock()
        await instance.on_enable()

        event = ChatMessage(player_name="P", channel="ChatAll", message="hi")
        await instance.relay_to_discord(event)
        content = instance.discord.send.call_args[1]["content"]
        assert "[All]" not in content
        assert "**P**: hi" in content

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord Chat Bridge"
        assert "rcon" in cls.requires
        assert "discord" in cls.requires
