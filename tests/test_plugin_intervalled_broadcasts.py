"""Tests for IntervalledBroadcasts plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import NewGame


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "intervalled_broadcasts",
        Path(__file__).parent.parent / "plugins" / "intervalled_broadcasts" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.IntervalledBroadcasts


class TestIntervalledBroadcasts:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "messages": ["msg-a", "msg-a", "msg-b"],
                "interval_seconds": 60,
                "broadcast_on_start": False,
                "reset_on_new_game": False,
                "mode": "sequential",
                "dedupe_consecutive": True,
                "min_players": 0,
                "random_seed": 1337,
            },
        )
        await instance.on_enable()
        return instance

    async def test_schedule_respects_interval(self, plugin):
        """Broadcast only fires when interval has elapsed."""
        plugin._test_now = 1000.0
        plugin._now = lambda: plugin._test_now
        plugin._next_run_at = 1060.0

        await plugin.broadcast_tick()
        plugin.rcon.broadcast.assert_not_awaited()

        plugin._test_now = 1060.0
        await plugin.broadcast_tick()
        plugin.rcon.broadcast.assert_awaited_once()

        plugin._test_now = 1061.0
        await plugin.broadcast_tick()
        assert plugin.rcon.broadcast.await_count == 1

    async def test_sequential_dedupe_skips_consecutive_duplicate_message(self, plugin):
        """Consecutive duplicates are skipped when dedupe_consecutive is enabled."""
        plugin._test_now = 2000.0
        plugin._now = lambda: plugin._test_now
        plugin._next_run_at = plugin._test_now

        await plugin.broadcast_tick()  # msg-a
        plugin._test_now += 60
        await plugin.broadcast_tick()  # msg-b (skip duplicate msg-a)
        plugin._test_now += 60
        await plugin.broadcast_tick()  # msg-a

        sent = [call.args[0] for call in plugin.rcon.broadcast.await_args_list]
        assert sent == ["msg-a", "msg-b", "msg-a"]

    async def test_dedupe_disabled_allows_consecutive_duplicates(self, plugin):
        """With dedupe disabled, repeated sequential entries are allowed."""
        plugin.config["dedupe_consecutive"] = False
        plugin._test_now = 3000.0
        plugin._now = lambda: plugin._test_now
        plugin._next_run_at = plugin._test_now

        await plugin.broadcast_tick()  # msg-a
        plugin._test_now += 60
        await plugin.broadcast_tick()  # msg-a again

        sent = [call.args[0] for call in plugin.rcon.broadcast.await_args_list]
        assert sent[:2] == ["msg-a", "msg-a"]

    async def test_min_players_gate_blocks_broadcast(self, plugin):
        """Population gate prevents sends when server is below threshold."""
        plugin.config["min_players"] = 5
        plugin.rcon.list_players.return_value = [object(), object(), object()]
        plugin._test_now = 4000.0
        plugin._now = lambda: plugin._test_now
        plugin._next_run_at = plugin._test_now

        await plugin.broadcast_tick()

        plugin.rcon.broadcast.assert_not_awaited()
        plugin.rcon.list_players.assert_awaited_once()

    async def test_reset_on_new_game_resets_rotation(self, plugin):
        """new_game reset can restart broadcast rotation and schedule."""
        plugin.config["reset_on_new_game"] = True
        plugin.config["broadcast_on_start"] = True
        plugin._message_index = 2
        plugin._last_message = "msg-b"

        plugin._test_now = 5000.0
        plugin._now = lambda: plugin._test_now
        await plugin.handle_new_game(NewGame())

        assert plugin._message_index == 0
        assert plugin._last_message is None
        assert plugin._next_run_at == plugin._test_now

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Intervalled Broadcasts"
        assert "rcon" in cls.requires

        tasks = cls.get_periodic_tasks()
        assert ("broadcast_tick", 5) in tasks

        handlers = cls.get_event_handlers()
        assert ("new_game", "handle_new_game") in handlers
