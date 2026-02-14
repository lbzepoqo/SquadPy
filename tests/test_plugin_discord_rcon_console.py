"""Tests for DiscordRconConsole plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_rcon_console",
        Path(__file__).parent.parent / "plugins" / "discord_rcon_console" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordRconConsole


def _interaction(*, role_ids: list[int], display_name: str = "AdminOne", user_id: int = 1001):
    interaction = AsyncMock()
    interaction.response = AsyncMock()
    interaction.user = MagicMock()
    interaction.user.roles = [MagicMock(id=role_id) for role_id in role_ids]
    interaction.user.display_name = display_name
    interaction.user.id = user_id
    interaction.guild_id = 777
    interaction.channel_id = 888
    return interaction


class TestDiscordRconConsole:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            discord=AsyncMock(),
            config={
                "admin_role_id": 12345,
                "audit_channel_id": 99999,
                "allow_all_commands": False,
                "allowed_command_prefixes": ["ShowCurrentMap", "ListPlayers"],
                "include_response": True,
                "max_response_chars": 120,
            },
        )
        return instance

    async def test_rcon_requires_role(self, plugin):
        interaction = _interaction(role_ids=[54321], display_name="UserNoPerm", user_id=2002)

        await plugin.rcon_cmd(interaction, "ShowCurrentMap")

        plugin.rcon.execute_privileged.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "You do not have permission to run console commands.",
            ephemeral=True,
        )
        plugin.discord.send.assert_awaited_once()
        assert plugin.discord.send.call_args[0][0] == 99999
        assert "outcome=rejected_role" in plugin.discord.send.call_args[1]["content"]

    async def test_rcon_rejects_disallowed_command_policy(self, plugin):
        interaction = _interaction(role_ids=[12345])

        await plugin.rcon_cmd(interaction, "AdminEndMatch")

        plugin.rcon.execute_privileged.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "Command is not allowed by policy.",
            ephemeral=True,
        )
        plugin.discord.send.assert_awaited_once()
        assert "outcome=rejected_policy" in plugin.discord.send.call_args[1]["content"]

    async def test_rcon_executes_allowed_command(self, plugin):
        interaction = _interaction(role_ids=[12345])
        plugin.rcon.execute_privileged.return_value = "Current level is Sumari"

        await plugin.rcon_cmd(interaction, "ShowCurrentMap")

        plugin.rcon.execute_privileged.assert_awaited_once()
        args = plugin.rcon.execute_privileged.call_args[0]
        kwargs = plugin.rcon.execute_privileged.call_args[1]
        assert args[0] == "ShowCurrentMap"
        assert kwargs["actor"] == "AdminOne:1001"
        assert kwargs["origin"] == "discord:guild=777:channel=888"
        assert kwargs["policy"]("ShowCurrentMap")
        assert not kwargs["policy"]("AdminEndMatch")

        interaction.response.send_message.assert_awaited_once()
        response_text = interaction.response.send_message.call_args[0][0]
        assert "Command executed." in response_text
        assert "Current level is Sumari" in response_text
        assert interaction.response.send_message.call_args[1]["ephemeral"] is True

        plugin.discord.send.assert_awaited_once()
        assert "outcome=success" in plugin.discord.send.call_args[1]["content"]

    async def test_rcon_execution_error_reports_and_audits(self, plugin):
        interaction = _interaction(role_ids=[12345])
        plugin.rcon.execute_privileged.side_effect = RuntimeError("connection lost")

        await plugin.rcon_cmd(interaction, "ShowCurrentMap")

        interaction.response.send_message.assert_awaited_once_with(
            "Command failed: connection lost",
            ephemeral=True,
        )
        plugin.discord.send.assert_awaited_once()
        content = plugin.discord.send.call_args[1]["content"]
        assert "outcome=error" in content
        assert "connection lost" in content

    async def test_empty_command_rejected(self, plugin):
        interaction = _interaction(role_ids=[12345])

        await plugin.rcon_cmd(interaction, "   ")

        plugin.rcon.execute_privileged.assert_not_awaited()
        plugin.discord.send.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "Command must not be empty.",
            ephemeral=True,
        )

    async def test_audit_channel_optional(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            discord=AsyncMock(),
            config={
                "admin_role_id": 0,
                "audit_channel_id": 0,
                "allow_all_commands": True,
            },
        )
        instance.rcon.execute_privileged.return_value = "OK"
        interaction = _interaction(role_ids=[])

        await instance.rcon_cmd(interaction, "AdminEndMatch")

        instance.rcon.execute_privileged.assert_awaited_once()
        instance.discord.send.assert_not_awaited()

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord RCON Console"
        assert "rcon" in cls.requires
        assert "discord" in cls.requires

        commands = cls.get_slash_commands()
        assert len(commands) == 1
        meta, method_name = commands[0]
        assert meta["name"] == "rcon"
        assert method_name == "rcon_cmd"
