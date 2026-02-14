"""Tests for DiscordSquadCreated plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import PlayerID, SquadCreated


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_squad_created",
        Path(__file__).parent.parent / "plugins" / "discord_squad_created" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordSquadCreated


class TestDiscordSquadCreated:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_creator_ids": True},
        )
        return instance

    async def test_squad_created_sent_to_discord(self, plugin):
        event = SquadCreated(
            team_id=1,
            team_name="USA",
            squad_id=7,
            squad_name="INF MIC",
            creator=PlayerID(
                name="SL",
                steam_id="76561198000000001",
                eos_id="00000000000000000000000000000001",
            ),
        )

        await plugin.handle_squad_created(event)

        plugin.discord.send.assert_awaited_once()
        assert plugin.discord.send.call_args[0][0] == 12345
        content = plugin.discord.send.call_args[1]["content"]
        assert "[SquadCreated]" in content
        assert "team=1 (USA)" in content
        assert "squad=7 name=INF MIC" in content
        assert "creator=SL" in content
        assert "steam=76561198000000001" in content
        assert "eos=00000000000000000000000000000001" in content

    async def test_no_channel_id_skips_send(self):
        cls = _load_plugin_class()
        instance = cls(discord=AsyncMock(), config={"channel_id": 0})

        await instance.handle_squad_created(
            SquadCreated(
                team_id=1,
                team_name="USA",
                squad_id=7,
                squad_name="INF MIC",
                creator=PlayerID(name="SL"),
            )
        )

        instance.discord.send.assert_not_awaited()

    async def test_creator_ids_disabled_omits_creator_ids(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_creator_ids": False},
        )

        event = SquadCreated(
            team_id=2,
            team_name="RGF",
            squad_id=3,
            squad_name="Armor",
            creator=PlayerID(
                name="ArmorLead",
                steam_id="76561198000000002",
                eos_id="00000000000000000000000000000002",
            ),
        )
        await instance.handle_squad_created(event)

        content = instance.discord.send.call_args[1]["content"]
        assert "creator=ArmorLead" in content
        assert "steam=" not in content
        assert "eos=" not in content

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord Squad Created"
        assert "discord" in cls.requires
        assert cls.get_event_handlers() == [("squad_created", "handle_squad_created")]
