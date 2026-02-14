"""Tests for DiscordTeamkill plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import Teamkill, PlayerID


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_teamkill",
        Path(__file__).parent.parent / "plugins" / "discord_teamkill" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordTeamkill


class TestDiscordTeamkill:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_weapon": True},
        )
        return instance

    async def test_teamkill_sent_to_discord(self, plugin):
        event = Teamkill(
            attacker=PlayerID(name="Attacker", steam_id="76561198000000001"),
            victim=PlayerID(name="Victim", steam_id="76561198000000002"),
            weapon="BP_Rifle",
        )

        await plugin.handle_teamkill(event)

        plugin.discord.send.assert_awaited_once()
        assert plugin.discord.send.call_args[0][0] == 12345
        content = plugin.discord.send.call_args[1]["content"]
        assert "Attacker" in content
        assert "Victim" in content
        assert "BP_Rifle" in content

    async def test_no_channel_id_skips_send(self):
        cls = _load_plugin_class()
        instance = cls(discord=AsyncMock(), config={"channel_id": 0})

        event = Teamkill(
            attacker=PlayerID(name="Attacker"),
            victim=PlayerID(name="Victim"),
            weapon="BP_Rifle",
        )

        await instance.handle_teamkill(event)

        instance.discord.send.assert_not_awaited()

    async def test_weapon_disabled_omits_weapon_text(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_weapon": False},
        )

        event = Teamkill(
            attacker=PlayerID(name="Attacker", steam_id="1"),
            victim=PlayerID(name="Victim", steam_id="2"),
            weapon="BP_Rifle",
        )

        await instance.handle_teamkill(event)

        content = instance.discord.send.call_args[1]["content"]
        assert "weapon=" not in content

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord Teamkill"
        assert "discord" in cls.requires
        assert cls.get_event_handlers() == [("teamkill", "handle_teamkill")]
