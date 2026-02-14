"""Tests for DiscordRoundEvents plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import NewGame, RoundEnded


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_round_events",
        Path(__file__).parent.parent / "plugins" / "discord_round_events" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordRoundEvents


class TestDiscordRoundEvents:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={
                "channel_id": 12345,
                "include_previous_winner": True,
                "include_loser": True,
            },
        )
        return instance

    async def test_round_start_sent_to_discord(self, plugin):
        event = NewGame(
            dlc="SquadGame",
            map_classname="Narva",
            layer_classname="Narva_AAS_v1",
            winner={"winner": "Team 1", "layer": "Narva_AAS_v1"},
        )

        await plugin.handle_new_game(event)

        plugin.discord.send.assert_awaited_once()
        assert plugin.discord.send.call_args[0][0] == 12345
        content = plugin.discord.send.call_args[1]["content"]
        assert "[RoundStart]" in content
        assert "map=Narva" in content
        assert "layer=Narva_AAS_v1" in content
        assert "previous_winner=Team 1" in content

    async def test_round_end_sent_to_discord(self, plugin):
        event = RoundEnded(
            winner={
                "team": "1",
                "subfaction": "Motorized",
                "faction": "USA",
                "tickets": 55,
            },
            loser={
                "team": "2",
                "subfaction": "Motorized",
                "faction": "RGF",
                "tickets": 0,
            },
        )

        await plugin.handle_round_ended(event)

        plugin.discord.send.assert_awaited_once()
        content = plugin.discord.send.call_args[1]["content"]
        assert "[RoundEnd]" in content
        assert "winner=team=1" in content
        assert "loser=team=2" in content

    async def test_no_channel_id_skips_send(self):
        cls = _load_plugin_class()
        instance = cls(discord=AsyncMock(), config={"channel_id": 0})

        await instance.handle_new_game(NewGame(map_classname="Narva", layer_classname="Narva_AAS_v1"))
        await instance.handle_round_ended(RoundEnded())

        instance.discord.send.assert_not_awaited()

    async def test_loser_disabled_omits_loser_text(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_loser": False},
        )

        event = RoundEnded(
            winner={"winner": "Team 1"},
            loser={"winner": "Team 2"},
        )
        await instance.handle_round_ended(event)

        content = instance.discord.send.call_args[1]["content"]
        assert "winner=Team 1" in content
        assert "loser=" not in content

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord Round Events"
        assert "discord" in cls.requires
        assert cls.get_event_handlers() == [
            ("new_game", "handle_new_game"),
            ("round_ended", "handle_round_ended"),
        ]
