"""Tests for AutoSeedLowPlayers plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "auto_seed_low_players",
        Path(__file__).parent.parent / "plugins" / "auto_seed_low_players" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.AutoSeedLowPlayers


def _make_player(
    steam_id: str,
    *,
    team_id: int = 1,
    squad_id: int = 1,
) -> RconPlayer:
    return RconPlayer(
        id=0,
        steam_id=steam_id,
        eos_id="",
        name=f"Player_{steam_id}",
        team_id=team_id,
        squad_id=squad_id,
        is_leader=False,
        role="Rifleman",
    )


class TestAutoSeedLowPlayers:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "seed_player_threshold": 5,
                "announce_transitions": True,
                "announce_reminders": True,
                "reminder_interval_seconds": 60,
                "low_population_message": "Low ({players}/{threshold})",
                "recovered_message": "Recovered ({players}/{threshold})",
                "warn_unassigned_on_enter": True,
                "unassigned_warning_message": "Join a squad",
                "set_fog_on_transition": True,
                "seed_fog_mode": "1",
                "live_fog_mode": "0",
            },
        )
        await instance.on_enable()
        return instance

    async def test_enter_low_population_runs_actions(self, plugin):
        """Transition into low-pop mode announces and runs configured actions."""
        plugin.rcon.list_players.return_value = [
            _make_player("p1", squad_id=0),
            _make_player("p2", squad_id=1),
            _make_player("p3", squad_id=1),
        ]

        await plugin.check_low_population()

        plugin.rcon.broadcast.assert_awaited_once_with("Low (3/5)")
        plugin.rcon.warn.assert_awaited_once_with("p1", "Join a squad")
        plugin.rcon.set_fog_of_war.assert_awaited_once_with("1")

    async def test_low_population_reminder_respects_interval(self, plugin):
        """Repeated reminders only fire after interval."""
        plugin.rcon.list_players.return_value = [
            _make_player("p1", squad_id=1),
            _make_player("p2", squad_id=1),
            _make_player("p3", squad_id=1),
        ]

        plugin._test_now = 1000.0
        plugin._now = lambda: plugin._test_now

        await plugin.check_low_population()  # transition announce
        plugin._test_now = 1030.0
        await plugin.check_low_population()  # no reminder
        plugin._test_now = 1061.0
        await plugin.check_low_population()  # reminder

        assert plugin.rcon.broadcast.await_count == 2

    async def test_exit_low_population_runs_actions(self, plugin):
        """Transition out of low-pop mode announces recovery actions."""
        plugin.rcon.list_players.side_effect = [
            [_make_player("p1"), _make_player("p2"), _make_player("p3")],  # low
            [
                _make_player("p1"),
                _make_player("p2"),
                _make_player("p3"),
                _make_player("p4"),
                _make_player("p5"),
                _make_player("p6"),
            ],  # recovered
        ]

        await plugin.check_low_population()
        await plugin.check_low_population()

        assert plugin.rcon.broadcast.await_count == 2
        assert plugin.rcon.set_fog_of_war.await_count == 2
        assert plugin.rcon.set_fog_of_war.call_args_list[0][0] == ("1",)
        assert plugin.rcon.set_fog_of_war.call_args_list[1][0] == ("0",)

    async def test_never_low_population_does_nothing(self, plugin):
        """No low-pop transition means no actions are fired."""
        plugin.rcon.list_players.return_value = [
            _make_player("p1"),
            _make_player("p2"),
            _make_player("p3"),
            _make_player("p4"),
            _make_player("p5"),
        ]
        await plugin.check_low_population()
        plugin.rcon.broadcast.assert_not_awaited()
        plugin.rcon.warn.assert_not_awaited()
        plugin.rcon.set_fog_of_war.assert_not_awaited()

    async def test_plugin_attributes_and_tasks(self):
        cls = _load_plugin_class()
        assert cls.name == "Auto Seed Low Players"
        assert "rcon" in cls.requires
        tasks = cls.get_periodic_tasks()
        names = [name for name, _ in tasks]
        assert "check_low_population" in names
