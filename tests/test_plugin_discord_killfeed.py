"""Tests for DiscordKillfeed plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import PlayerDied, PlayerID


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_killfeed",
        Path(__file__).parent.parent / "plugins" / "discord_killfeed" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordKillfeed


class TestDiscordKillfeed:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_weapon": True},
        )
        return instance

    async def test_killfeed_sent_to_discord(self, plugin):
        event = PlayerDied(
            victim_name="Victim",
            attacker=PlayerID(name="Attacker"),
            weapon="BP_Rifle",
        )

        await plugin.handle_player_died(event)

        plugin.discord.send.assert_awaited_once()
        assert plugin.discord.send.call_args[0][0] == 12345
        content = plugin.discord.send.call_args[1]["content"]
        assert "Attacker" in content
        assert "Victim" in content
        assert "BP_Rifle" in content

    async def test_no_channel_id_skips_send(self):
        cls = _load_plugin_class()
        instance = cls(discord=AsyncMock(), config={"channel_id": 0})

        event = PlayerDied(victim_name="Victim", attacker=PlayerID(name="Attacker"))
        await instance.handle_player_died(event)

        instance.discord.send.assert_not_awaited()

    async def test_weapon_disabled_omits_weapon_text(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_weapon": False},
        )

        event = PlayerDied(
            victim_name="Victim",
            attacker=PlayerID(name="Attacker"),
            weapon="BP_Rifle",
        )
        await instance.handle_player_died(event)

        content = instance.discord.send.call_args[1]["content"]
        assert "weapon=" not in content

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord Killfeed"
        assert "discord" in cls.requires
        assert cls.get_event_handlers() == [("player_died", "handle_player_died")]
