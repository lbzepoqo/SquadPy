"""Tests for ServerStatus plugin."""

import datetime
import importlib.util
import urllib.parse
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from squadpy.events.types import ServerTickRate, NewGame
from squadpy.rcon.types import MapInfo, RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "server_status",
        Path(__file__).parent.parent / "plugins" / "server_status" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.ServerStatus


def _make_player(squad_id: int = 1) -> RconPlayer:
    return RconPlayer(
        id=0, steam_id="s", eos_id="e", name="P",
        team_id=1, squad_id=squad_id, is_leader=False, role="R",
    )


async def _history_from(messages):
    for message in messages:
        yield message


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

    async def test_reuses_existing_status_embed_on_startup(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        mock_rcon.list_players.return_value = []
        mock_rcon.show_current_map.return_value = None
        mock_rcon.show_next_map.return_value = None

        mock_discord = AsyncMock()
        mock_message = AsyncMock()
        mock_message.id = 1001
        mock_message.author = MagicMock(id=42)
        mock_message.embeds = [discord.Embed(title="Server Status")]
        mock_discord.bot.user = MagicMock(id=42)
        mock_discord.get_channel.return_value = MagicMock(
            history=MagicMock(return_value=_history_from([mock_message]))
        )
        mock_discord.edit_message.return_value = mock_message

        instance = cls(
            rcon=mock_rcon,
            discord=mock_discord,
            config={"channel_id": 12345},
        )
        await instance.on_enable()

        mock_discord.send.assert_not_awaited()
        assert mock_discord.edit_message.await_count >= 1
        assert instance._message is mock_message

    async def test_update_edits_existing_message(self, plugin):
        """Periodic update edits existing message."""
        plugin.rcon.list_players.return_value = [_make_player(), _make_player()]
        plugin.rcon.show_current_map.return_value = MapInfo("Tallil", "Tallil_Seed", "US RU")
        plugin.rcon.show_next_map.return_value = None

        await plugin.update_status()
        plugin.discord.edit_message.assert_awaited()

        embed = plugin.discord.edit_message.call_args[1]["embed"]
        fields = {field.name: field.value for field in embed.fields}
        assert fields["Map"] == "Tallil"
        assert fields["Layer"] == "Tallil_Seed"
        assert fields["Factions"] == "US RU"
        assert fields["Players"] == "2"
        assert fields["Squads"] == "1"
        assert fields["Tick Rate"] == "0.0"
        assert fields["Next Map"] == "Not set (voting)"
        assert embed.image.url.startswith("https://quickchart.io/chart")
        assert "version=4" in embed.image.url
        assert "{" not in embed.image.url
        assert '"' not in embed.image.url
        decoded = urllib.parse.unquote(embed.image.url)
        assert "Players" in decoded
        assert "Last 60 min" in decoded
        assert '"min":0' in decoded
        assert '"max":100' in decoded
        assert '"stepSize":10' in decoded

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

    async def test_graph_window_prunes_old_samples(self, plugin):
        """Trend samples older than graph_window_minutes are pruned."""
        plugin.config["graph_window_minutes"] = 10
        plugin.rcon.list_players.return_value = [_make_player()]
        plugin.rcon.show_current_map.return_value = MapInfo("Tallil", "Tallil_Seed", "US RU")
        plugin.rcon.show_next_map.return_value = None
        plugin._trend_samples.clear()

        base = plugin._now()
        times = [
            base - datetime.timedelta(minutes=30),
            base - datetime.timedelta(minutes=9),
            base,
        ]
        last_time = base

        def _next_time():
            nonlocal last_time
            if times:
                last_time = times.pop(0)
            return last_time

        plugin._now = _next_time

        await plugin.update_status()
        await plugin.update_status()
        await plugin.update_status()

        assert len(plugin._trend_samples) == 2
        assert plugin._trend_samples[0][1] == 1

    async def test_graph_url_stays_within_embed_limit(self, plugin):
        """Graph URL remains under Discord embed URL limits via downsampling."""
        plugin.config["graph_window_minutes"] = 240
        plugin.config["graph_max_points"] = 24
        plugin.rcon.list_players.return_value = [_make_player()]
        plugin.rcon.show_current_map.return_value = MapInfo("Tallil", "Tallil_Seed", "US RU")
        plugin.rcon.show_next_map.return_value = None

        base = plugin._now()
        times = [
            base - datetime.timedelta(minutes=239 - i)
            for i in range(240)
        ]
        last_time = base

        def _next_time():
            nonlocal last_time
            if times:
                last_time = times.pop(0)
            return last_time

        plugin._now = _next_time

        for _ in range(240):
            await plugin.update_status()

        embed = plugin.discord.edit_message.call_args[1]["embed"]
        assert embed.image.url is not None
        assert len(embed.image.url) <= 2000
        assert len(plugin._sampled_trend_points()) <= 25

    async def test_graph_can_be_disabled(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        mock_discord = AsyncMock()
        mock_message = AsyncMock()
        mock_discord.send.return_value = mock_message
        mock_discord.edit_message.return_value = mock_message

        instance = cls(
            rcon=mock_rcon,
            discord=mock_discord,
            config={"channel_id": 12345, "graph_enabled": False},
        )
        await instance.on_enable()

        instance.rcon.list_players.return_value = [_make_player()]
        instance.rcon.show_current_map.return_value = MapInfo("Tallil", "Tallil_Seed", "US RU")
        instance.rcon.show_next_map.return_value = None
        await instance.update_status()

        embed = instance.discord.edit_message.call_args[1]["embed"]
        assert embed.image.url is None
