"""Tests for AdminRequest plugin."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.events.types import ChatMessage
from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "admin_request",
        Path(__file__).parent.parent / "plugins" / "admin_request" / "plugin.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AdminRequest


class TestAdminRequest:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        mock_discord = AsyncMock()
        mock_message = AsyncMock()
        mock_message.id = 44444
        mock_message.embeds = []
        mock_discord.send.return_value = mock_message
        mock_discord.namespace_custom_id = MagicMock(return_value="admin_request:claim_ticket")
        mock_thread = AsyncMock()
        mock_thread.id = 99999
        mock_discord.create_thread.return_value = mock_thread

        instance = cls(
            rcon=mock_rcon,
            discord=mock_discord,
            config={
                "channel_id": 12345,
                "ping_role_id": 0,
                "command_prefix": "!admin",
            },
        )
        await instance.on_enable()
        return instance

    async def test_admin_prefix_creates_ticket(self, plugin):
        """Chat with !admin prefix creates embed + thread."""
        event = ChatMessage(
            player_name="Player1",
            steam_id="76561198000000001",
            eos_id="abc123",
            channel="ChatAll",
            message="!admin someone is cheating",
        )
        await plugin.handle_chat(event)

        plugin.discord.send.assert_awaited_once()
        plugin.discord.create_thread.assert_awaited_once()
        plugin.rcon.warn.assert_awaited_once_with(
            "76561198000000001", "Your admin request has been submitted"
        )
        assert 99999 in plugin._tickets

    async def test_non_admin_prefix_ignored(self, plugin):
        """Chat without !admin prefix is ignored."""
        event = ChatMessage(
            player_name="Player1",
            steam_id="76561198000000001",
            eos_id="abc123",
            channel="ChatAll",
            message="hello everyone",
        )
        await plugin.handle_chat(event)
        plugin.discord.send.assert_not_awaited()

    async def test_no_reason_default(self, plugin):
        """!admin with no reason uses default text."""
        event = ChatMessage(
            player_name="Player1",
            steam_id="76561198000000001",
            eos_id="abc123",
            channel="ChatAll",
            message="!admin",
        )
        await plugin.handle_chat(event)
        plugin.discord.send.assert_awaited_once()

    async def test_claim_button_edits_embed(self, plugin):
        """Clicking Claim edits the embed."""
        import discord as _discord
        mock_embed = MagicMock(spec=_discord.Embed)
        mock_embed.color = None

        interaction = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.id = 44444
        interaction.message.embeds = [mock_embed]
        interaction.user = MagicMock()
        interaction.user.display_name = "AdminUser"
        interaction.response = AsyncMock()

        plugin._tickets[99999] = {
            "steam_id": "76561198000000001",
            "player_name": "Player1",
            "message_id": 44444,
            "claimed_by": None,
        }

        await plugin.handle_claim(interaction)
        interaction.response.edit_message.assert_awaited_once()
        assert plugin._tickets[99999]["claimed_by"] == "AdminUser"

    async def test_claim_updates_matching_ticket_only(self, plugin):
        """Claim maps by originating message, not first unclaimed ticket."""
        import discord as _discord
        mock_embed = MagicMock(spec=_discord.Embed)
        mock_embed.color = None

        plugin._tickets[11111] = {
            "steam_id": "steam-a",
            "player_name": "PlayerA",
            "message_id": 1001,
            "claimed_by": None,
        }
        plugin._tickets[22222] = {
            "steam_id": "steam-b",
            "player_name": "PlayerB",
            "message_id": 1002,
            "claimed_by": None,
        }

        interaction = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.id = 1002
        interaction.message.embeds = [mock_embed]
        interaction.user = MagicMock()
        interaction.user.display_name = "AdminUser"
        interaction.response = AsyncMock()

        await plugin.handle_claim(interaction)

        assert plugin._tickets[11111]["claimed_by"] is None
        assert plugin._tickets[22222]["claimed_by"] == "AdminUser"

    async def test_thread_message_relays_to_player(self, plugin):
        """Thread message relays to player via RCON warn."""
        # Setup ticket
        plugin._tickets[99999] = {
            "steam_id": "76561198000000001",
            "player_name": "Player1",
            "claimed_by": "Admin",
        }
        plugin._player_cache["76561198000000001"] = RconPlayer(
            id=0, steam_id="76561198000000001", eos_id="", name="Player1",
            team_id=1, squad_id=1, is_leader=False, role="R",
        )

        msg = MagicMock()
        msg.channel = MagicMock()
        msg.channel.id = 99999
        msg.author = MagicMock()
        msg.author.display_name = "AdminGuy"
        msg.content = "Stop doing that"

        await plugin.handle_thread_msg(msg)
        plugin.rcon.warn.assert_awaited_once_with(
            "76561198000000001", "[Admin] AdminGuy: Stop doing that"
        )

    async def test_thread_message_player_offline_no_crash(self, plugin):
        """Thread message for offline player doesn't crash."""
        plugin._tickets[99999] = {
            "steam_id": "76561198000000001",
            "player_name": "Player1",
            "claimed_by": "Admin",
        }
        # Player NOT in cache (offline)

        msg = MagicMock()
        msg.channel = MagicMock()
        msg.channel.id = 99999
        msg.author = MagicMock()
        msg.author.display_name = "AdminGuy"
        msg.content = "Hey you"

        await plugin.handle_thread_msg(msg)
        plugin.rcon.warn.assert_not_awaited()

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Admin Request"
        assert "rcon" in cls.requires
        assert "discord" in cls.requires

    async def test_no_channel_id_skips(self):
        """No channel_id configured skips ticket creation."""
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(), discord=AsyncMock(),
            config={"channel_id": 0, "command_prefix": "!admin"},
        )
        await instance.on_enable()
        event = ChatMessage(
            player_name="P", steam_id="s", eos_id="e",
            channel="ChatAll", message="!admin help",
        )
        await instance.handle_chat(event)
        instance.discord.send.assert_not_awaited()
