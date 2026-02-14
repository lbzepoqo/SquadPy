"""Tests for DiscordAdminBroadcast plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_admin_broadcast",
        Path(__file__).parent.parent / "plugins" / "discord_admin_broadcast" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordAdminBroadcast


class TestDiscordAdminBroadcast:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            discord=AsyncMock(),
            config={"admin_role_id": 12345, "audit_channel_id": 99999},
        )
        return instance

    async def test_broadcast_requires_role(self, plugin):
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.roles = [MagicMock(id=54321)]

        await plugin.broadcast_cmd(interaction, "Server restart in 10 minutes")

        plugin.rcon.broadcast.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args[1]["ephemeral"] is True

    async def test_broadcast_sends_to_rcon_and_audit(self, plugin):
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.display_name = "AdminOne"
        interaction.user.roles = [MagicMock(id=12345)]

        await plugin.broadcast_cmd(interaction, "Server restart in 10 minutes")

        plugin.rcon.broadcast.assert_awaited_once_with("Server restart in 10 minutes")
        plugin.discord.send.assert_awaited_once_with(
            99999,
            content="[Broadcast] actor=AdminOne message=Server restart in 10 minutes",
        )
        interaction.response.send_message.assert_awaited_once_with(
            "Broadcast sent.", ephemeral=True
        )

    async def test_broadcast_without_role_gate(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            discord=AsyncMock(),
            config={"admin_role_id": 0, "audit_channel_id": 0},
        )

        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.roles = [MagicMock(id=999)]

        await instance.broadcast_cmd(interaction, "hello")

        instance.rcon.broadcast.assert_awaited_once_with("hello")
        instance.discord.send.assert_not_awaited()

    async def test_empty_message_rejected(self, plugin):
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.roles = [MagicMock(id=12345)]

        await plugin.broadcast_cmd(interaction, "   ")

        plugin.rcon.broadcast.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "Message must not be empty.",
            ephemeral=True,
        )

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord Admin Broadcast"
        assert "rcon" in cls.requires
        assert "discord" in cls.requires

        commands = cls.get_slash_commands()
        assert len(commands) == 1
        meta, method_name = commands[0]
        assert meta["name"] == "broadcast"
        assert method_name == "broadcast_cmd"
