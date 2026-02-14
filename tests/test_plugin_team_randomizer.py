"""Tests for TeamRandomizer plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "team_randomizer",
        Path(__file__).parent.parent / "plugins" / "team_randomizer" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.TeamRandomizer


def _player(
    steam_id: str,
    *,
    team_id: int,
    is_leader: bool = False,
) -> RconPlayer:
    return RconPlayer(
        id=0,
        steam_id=steam_id,
        eos_id="",
        name=f"Player_{steam_id}",
        team_id=team_id,
        squad_id=1,
        is_leader=is_leader,
        role="Rifleman",
    )


def _teams(team1_count: int, team2_count: int) -> list[RconPlayer]:
    players: list[RconPlayer] = []
    for idx in range(team1_count):
        players.append(_player(f"t1_{idx}", team_id=1))
    for idx in range(team2_count):
        players.append(_player(f"t2_{idx}", team_id=2))
    return players


class TestTeamRandomizer:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "min_players": 1,
                "max_team_difference": 1,
                "max_moves_per_cycle": 2,
                "cycle_cooldown_seconds": 60,
                "allow_leaders": False,
                "announce_moves": True,
                "announce_message": "Moved {count} ({team1}/{team2})",
                "random_seed": 1337,
                "exempt_steam_ids": [],
            },
        )
        await instance.on_enable()
        return instance

    async def test_no_action_when_already_balanced(self, plugin):
        """No moves happen when teams are within allowed difference."""
        plugin.rcon.list_players.return_value = _teams(5, 4)
        await plugin.randomize_teams()
        plugin.rcon.switch_team.assert_not_awaited()
        plugin.rcon.broadcast.assert_not_awaited()

    async def test_moves_players_when_imbalanced(self, plugin):
        """Imbalanced teams trigger limited random moves."""
        plugin.rcon.list_players.return_value = _teams(8, 4)
        await plugin.randomize_teams()

        assert plugin.rcon.switch_team.await_count == 2
        plugin.rcon.broadcast.assert_awaited_once_with("Moved 2 (8/4)")

    async def test_max_moves_per_cycle_respected(self, plugin):
        """Configured max moves cap is enforced."""
        plugin.config["max_moves_per_cycle"] = 1
        plugin.rcon.list_players.return_value = _teams(9, 3)
        await plugin.randomize_teams()
        assert plugin.rcon.switch_team.await_count == 1

    async def test_exempt_and_leader_players_not_selected(self, plugin):
        """Exempt players and leaders are never auto-moved."""
        plugin.config["exempt_steam_ids"] = ["exempt_1"]
        plugin.rcon.list_players.return_value = [
            _player("exempt_1", team_id=1),
            _player("leader_1", team_id=1, is_leader=True),
            _player("eligible_1", team_id=1),
            _player("t2_1", team_id=2),
        ]

        await plugin.randomize_teams()
        plugin.rcon.switch_team.assert_awaited_once_with("eligible_1")

    async def test_cycle_cooldown_prevents_back_to_back_runs(self, plugin):
        """Cooldown prevents repeated randomization too frequently."""
        plugin.config["max_moves_per_cycle"] = 1
        plugin._test_now = 1000.0
        plugin._now = lambda: plugin._test_now
        plugin.rcon.list_players.return_value = _teams(7, 3)

        await plugin.randomize_teams()
        plugin._test_now = 1030.0
        await plugin.randomize_teams()

        assert plugin.rcon.switch_team.await_count == 1

    async def test_plugin_attributes_and_tasks(self):
        cls = _load_plugin_class()
        assert cls.name == "Team Randomizer"
        assert "rcon" in cls.requires
        tasks = cls.get_periodic_tasks()
        names = [name for name, _ in tasks]
        assert "randomize_teams" in names
