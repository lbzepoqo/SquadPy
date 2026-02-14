"""Tests for AutoRejoinTeam plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import JoinSucceeded, PlayerID
from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "auto_rejoin_team",
        Path(__file__).parent.parent / "plugins" / "auto_rejoin_team" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.AutoRejoinTeam


def _player(steam_id: str, team_id: int) -> RconPlayer:
    return RconPlayer(
        id=0,
        steam_id=steam_id,
        eos_id="",
        name=f"Player_{steam_id}",
        team_id=team_id,
        squad_id=1,
        is_leader=False,
        role="Rifleman",
    )


def _join_event(steam_id: str) -> JoinSucceeded:
    return JoinSucceeded(player=PlayerID(steam_id=steam_id))


class TestAutoRejoinTeam:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "max_players_for_rejoin": 80,
                "max_attempts": 2,
            },
        )
        await instance.on_enable()
        return instance

    async def test_rejoin_switches_back_to_prior_team(self, plugin):
        """Known player rejoining wrong team is switched back."""
        plugin.rcon.list_players.return_value = [_player("steam_a", 1)]
        await plugin.refresh_players()

        await plugin.handle_join_succeeded(_join_event("steam_a"))

        plugin.rcon.list_players.return_value = [_player("steam_a", 2)]
        await plugin.enforce_rejoin()

        plugin.rcon.switch_team.assert_awaited_once_with("steam_a")

    async def test_no_prior_team_no_action(self, plugin):
        """Unknown players are not forced when they rejoin."""
        await plugin.handle_join_succeeded(_join_event("steam_new"))
        plugin.rcon.list_players.return_value = [_player("steam_new", 2)]
        await plugin.enforce_rejoin()
        plugin.rcon.switch_team.assert_not_awaited()

    async def test_already_on_desired_team_clears_pending(self, plugin):
        """Pending player on desired team is cleared without switch."""
        plugin.rcon.list_players.return_value = [_player("steam_a", 1)]
        await plugin.refresh_players()

        await plugin.handle_join_succeeded(_join_event("steam_a"))
        plugin.rcon.list_players.return_value = [_player("steam_a", 1)]
        await plugin.enforce_rejoin()

        plugin.rcon.switch_team.assert_not_awaited()
        assert "steam_a" not in plugin._pending

    async def test_max_players_guard_skips_enforcement(self, plugin):
        """Enforcement pauses when server population is above configured cap."""
        plugin.config["max_players_for_rejoin"] = 1
        plugin.rcon.list_players.return_value = [_player("steam_a", 1)]
        await plugin.refresh_players()
        await plugin.handle_join_succeeded(_join_event("steam_a"))

        plugin.rcon.list_players.return_value = [_player("steam_a", 2), _player("steam_b", 1)]
        await plugin.enforce_rejoin()

        plugin.rcon.switch_team.assert_not_awaited()

    async def test_attempt_limit_stops_retries(self, plugin):
        """Retries stop after max_attempts."""
        plugin.rcon.list_players.return_value = [_player("steam_a", 1)]
        await plugin.refresh_players()
        await plugin.handle_join_succeeded(_join_event("steam_a"))

        plugin.rcon.list_players.return_value = [_player("steam_a", 2)]
        await plugin.enforce_rejoin()
        await plugin.enforce_rejoin()
        await plugin.enforce_rejoin()  # exceeds max_attempts, clears pending

        assert plugin.rcon.switch_team.await_count == 2
        assert "steam_a" not in plugin._pending

    async def test_plugin_attributes_and_handlers(self):
        cls = _load_plugin_class()
        assert cls.name == "Auto Rejoin Team"
        assert "rcon" in cls.requires

        handlers = cls.get_event_handlers()
        events = [event_name for event_name, _ in handlers]
        assert "join_succeeded" in events
        assert "player_connected" in events

        tasks = cls.get_periodic_tasks()
        names = [name for name, _ in tasks]
        assert "refresh_players" in names
        assert "enforce_rejoin" in names
