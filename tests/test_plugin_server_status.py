"""Tests for ServerStatus plugin."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.events.types import ServerTickRate, NewGame
from squadpy.rcon.types import MapInfo, RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "server_status",
        Path(__file__).parent.parent / "plugins" / "server_status" / "plugin.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ServerStatus


def _make_player(squad_id: int = 1) -> RconPlayer:
    return RconPlayer(
        id=0, steam_id="s", eos_id="e", name="P",
        team_id=1, squad_id=squad_id, is_leader=False, role="R",
    )


class TestServerStatus:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        mock_discord = AsyncMock()
        mock_message = AsyncMock()
        mock_discord.send.return_value = mock_message
        mock_discord.edit_message.return_value = mock_message

        instance = cls(
            rcon=mock_rcon,
            discord=mock_discord,
            config={"channel_id": 12345},
        )
        await instance.on_enable()
        return instance

    async def test_initial_embed_posted(self, plugin):
        """on_enable sends initial embed."""
        plugin.discord.send.assert_awaited_once()
        assert plugin._message is not None

    async def test_update_edits_existing_message(self, plugin):
        """Periodic update edits existing message."""
        plugin.rcon.list_players.return_value = [_make_player(), _make_player()]
        plugin.rcon.show_current_map.return_value = MapInfo("Tallil", "Tallil_Seed", "US RU")
        plugin.rcon.show_next_map.return_value = None

        await plugin.update_status()
        plugin.discord.edit_message.assert_awaited()

    async def test_message_deleted_posts_new(self, plugin):
        """If edit fails, a new message is posted."""
        plugin.discord.edit_message.side_effect = Exception("not found")
        new_msg = AsyncMock()
        plugin.discord.send.return_value = new_msg

        plugin.rcon.list_players.return_value = []
        plugin.rcon.show_current_map.return_value = None
        plugin.rcon.show_next_map.return_value = None

        await plugin.update_status()
        # send called again (beyond initial)
        assert plugin.discord.send.await_count == 2
        assert plugin._message is new_msg

    async def test_tick_rate_cached(self, plugin):
        """ServerTickRate event updates cached tick rate."""
        event = ServerTickRate(tick_rate=35.5)
        await plugin.cache_tick_rate(event)
        assert plugin._tick_rate == 35.5

    async def test_new_game_caches_map(self, plugin):
        """NewGame event caches map info."""
        event = NewGame(map_classname="Tallil_Outskirts", layer_classname="Tallil_Seed_v1")
        await plugin.cache_map(event)
        assert plugin._current_map == "Tallil_Outskirts"
        assert plugin._current_layer == "Tallil_Seed_v1"

    async def test_disable_sets_offline(self, plugin):
        """on_disable edits message to Offline."""
        await plugin.on_disable()
        plugin.discord.edit_message.assert_awaited()

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Server Status"
        assert "rcon" in cls.requires
        assert "discord" in cls.requires

    async def test_no_channel_id_skips_update(self):
        """No channel_id configured skips update."""
        cls = _load_plugin_class()
        instance = cls(rcon=AsyncMock(), discord=AsyncMock(), config={"channel_id": 0})
        await instance.on_enable()
        instance.discord.send.assert_not_awaited()
        await instance.update_status()
        instance.discord.edit_message.assert_not_awaited()
