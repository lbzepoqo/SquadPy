"""Tests for FogOfWar plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.events.types import NewGame


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "fog_of_war",
        Path(__file__).parent.parent / "plugins" / "fog_of_war" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.FogOfWar


def _players(count: int) -> list[object]:
    return [MagicMock() for _ in range(count)]


class TestFogOfWar:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "seed_player_threshold": 50,
                "hysteresis_players": 2,
                "change_cooldown_seconds": 30,
                "seed_fog_mode": "1",
                "live_fog_mode": "0",
                "reset_on_new_game": True,
                "revert_on_disable": True,
                "revert_to_mode": "live",
            },
        )
        await instance.on_enable()
        return instance

    async def test_applies_seed_fog_below_threshold(self, plugin):
        plugin.rcon.list_players.return_value = _players(20)
        await plugin.evaluate_fog_mode()

        plugin.rcon.set_fog_of_war.assert_awaited_once_with("1")
        assert plugin._current_mode == "seed"
        records = plugin.recent_audit_records()
        assert records[-1]["outcome"] == "success"
        assert "mode=seed" in records[-1]["detail"]

    async def test_transitions_to_live_with_hysteresis(self, plugin):
        plugin.config["change_cooldown_seconds"] = 0
        plugin.rcon.list_players.side_effect = [
            _players(20),  # seed
            _players(51),  # stays seed due hysteresis (needs >= 52)
            _players(52),  # goes live
        ]

        await plugin.evaluate_fog_mode()
        await plugin.evaluate_fog_mode()
        await plugin.evaluate_fog_mode()

        assert plugin.rcon.set_fog_of_war.await_count == 2
        assert plugin.rcon.set_fog_of_war.await_args_list[0].args == ("1",)
        assert plugin.rcon.set_fog_of_war.await_args_list[1].args == ("0",)
        assert plugin._current_mode == "live"

    async def test_invalid_fog_config_is_safe_and_audited(self, plugin):
        plugin.config["seed_fog_mode"] = "bad_mode"
        plugin.rcon.list_players.return_value = _players(10)

        await plugin.evaluate_fog_mode()

        plugin.rcon.set_fog_of_war.assert_not_awaited()
        records = plugin.recent_audit_records()
        assert records[-1]["outcome"] == "invalid_config"

    async def test_change_cooldown_blocks_rapid_flips(self, plugin):
        plugin.config["hysteresis_players"] = 0
        plugin.config["change_cooldown_seconds"] = 60
        plugin._test_now = 1000.0
        plugin._now = lambda: plugin._test_now
        plugin.rcon.list_players.side_effect = [
            _players(20),  # seed apply
            _players(70),  # blocked by cooldown
            _players(70),  # allowed after cooldown
        ]

        await plugin.evaluate_fog_mode()
        plugin._test_now = 1020.0
        await plugin.evaluate_fog_mode()
        plugin._test_now = 1061.0
        await plugin.evaluate_fog_mode()

        assert plugin.rcon.set_fog_of_war.await_count == 2
        records = plugin.recent_audit_records()
        assert any(record["outcome"] == "cooldown_blocked" for record in records)

    async def test_revert_on_disable_is_reversible(self, plugin):
        plugin.rcon.list_players.return_value = _players(20)
        await plugin.evaluate_fog_mode()
        await plugin.on_disable()

        assert plugin.rcon.set_fog_of_war.await_count == 2
        assert plugin.rcon.set_fog_of_war.await_args_list[1].args == ("0",)
        assert plugin.recent_audit_records()[-1]["outcome"] == "success"

    async def test_new_game_resets_mode(self, plugin):
        plugin.rcon.list_players.return_value = _players(20)
        await plugin.evaluate_fog_mode()
        assert plugin._current_mode == "seed"

        await plugin.handle_new_game(NewGame())
        assert plugin._current_mode is None
        assert plugin.recent_audit_records()[-1]["outcome"] == "reset"

    async def test_dynamic_threshold_events_update_runtime_threshold(self, plugin):
        await plugin.handle_seeding_threshold_up(MagicMock(new_threshold=60))
        assert plugin._seed_player_threshold() == 60

        await plugin.handle_seeding_threshold_down(MagicMock(new_threshold=30))
        assert plugin._seed_player_threshold() == 30

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Fog Of War"
        assert "rcon" in cls.requires

        periodic_tasks = cls.get_periodic_tasks()
        assert ("evaluate_fog_mode", 15) in periodic_tasks

        handlers = cls.get_event_handlers()
        assert ("new_game", "handle_new_game") in handlers
        assert ("seeding_threshold_up", "handle_seeding_threshold_up") in handlers
        assert ("seeding_threshold_down", "handle_seeding_threshold_down") in handlers
