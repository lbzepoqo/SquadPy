"""Tests for MaxPlayerInSquad plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import NewGame
from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "max_player_in_squad",
        Path(__file__).parent.parent / "plugins" / "max_player_in_squad" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.MaxPlayerInSquad


def _player(
    steam_id: str,
    *,
    team_id: int = 1,
    squad_id: int = 1,
    is_leader: bool = False,
) -> RconPlayer:
    return RconPlayer(
        id=0,
        steam_id=steam_id,
        eos_id="",
        name=f"Player_{steam_id}",
        team_id=team_id,
        squad_id=squad_id,
        is_leader=is_leader,
        role="Rifleman",
    )


class TestMaxPlayerInSquad:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "max_players": 3,
                "min_players": 0,
                "warnings_before_kick": 2,
                "exempt_leaders": True,
                "exempt_steam_ids": [],
                "exempt_squad_ids": [],
                "warning_message": "Squad {squad_id} over {max_players} ({warnings_remaining})",
                "kick_reason": "Over limit {max_players} in squad {squad_id}",
            },
        )
        await instance.on_enable()
        return instance

    async def test_warning_then_kick_for_repeated_offender(self, plugin):
        """Overflow player is warned, then kicked on the next offense."""
        players = [_player("s1"), _player("s2"), _player("s3"), _player("s4")]
        plugin.rcon.list_players.return_value = players

        await plugin.enforce_max_players()
        plugin.rcon.warn.assert_awaited_once_with("s4", "Squad 1 over 3 (1)")
        plugin.rcon.kick.assert_not_awaited()

        await plugin.enforce_max_players()
        plugin.rcon.kick.assert_awaited_once_with("s4", "Over limit 3 in squad 1")

    async def test_immediate_kick_enforcement_when_threshold_is_one(self, plugin):
        """warnings_before_kick=1 triggers direct overflow enforcement."""
        plugin.config["warnings_before_kick"] = 1
        players = [
            _player("s1"),
            _player("s2"),
            _player("s3"),
            _player("s4"),
            _player("s5"),
        ]
        plugin.rcon.list_players.return_value = players

        await plugin.enforce_max_players()

        assert plugin.rcon.kick.await_count == 2
        kicked_ids = {call.args[0] for call in plugin.rcon.kick.await_args_list}
        assert kicked_ids == {"s4", "s5"}
        plugin.rcon.warn.assert_not_awaited()

    async def test_exempt_player_not_enforced(self, plugin):
        """Configured exempt player IDs are never warned/kicked."""
        plugin.config["warnings_before_kick"] = 1
        plugin.config["exempt_steam_ids"] = ["s5"]
        players = [
            _player("s1"),
            _player("s2"),
            _player("s3"),
            _player("s4"),
            _player("s5"),
        ]
        plugin.rcon.list_players.return_value = players

        await plugin.enforce_max_players()

        target_ids = {call.args[0] for call in plugin.rcon.kick.await_args_list}
        assert "s5" not in target_ids

    async def test_exempt_leader_not_enforced(self, plugin):
        """Leaders are exempt when exempt_leaders is enabled."""
        plugin.config["warnings_before_kick"] = 1
        players = [
            _player("s1"),
            _player("s2"),
            _player("s3"),
            _player("leader", is_leader=True),
        ]
        plugin.rcon.list_players.return_value = players

        await plugin.enforce_max_players()

        kicked_ids = {call.args[0] for call in plugin.rcon.kick.await_args_list}
        assert "leader" not in kicked_ids

    async def test_warning_state_clears_when_squad_recovers(self, plugin):
        """Warnings reset when a player is no longer in overflow state."""
        plugin.config["warnings_before_kick"] = 3
        plugin.rcon.list_players.side_effect = [
            [_player("s1"), _player("s2"), _player("s3"), _player("s4")],  # warn
            [_player("s1"), _player("s2"), _player("s3")],  # recovered
            [_player("s1"), _player("s2"), _player("s3"), _player("s4")],  # warn again
        ]

        await plugin.enforce_max_players()
        await plugin.enforce_max_players()
        await plugin.enforce_max_players()

        assert plugin.rcon.warn.await_count == 2
        plugin.rcon.kick.assert_not_awaited()

    async def test_new_game_resets_warning_state(self, plugin):
        """New rounds reset warning counters to avoid stale escalation."""
        plugin.rcon.list_players.return_value = [
            _player("s1"),
            _player("s2"),
            _player("s3"),
            _player("s4"),
        ]
        await plugin.enforce_max_players()
        assert plugin._warning_counts

        await plugin.reset_warnings(NewGame())
        assert plugin._warning_counts == {}

    async def test_plugin_attributes_and_tasks(self):
        cls = _load_plugin_class()
        assert cls.name == "Max Player In Squad"
        assert "rcon" in cls.requires

        periodic_tasks = cls.get_periodic_tasks()
        names = [name for name, _ in periodic_tasks]
        assert "enforce_max_players" in names

        handlers = cls.get_event_handlers()
        assert ("new_game", "reset_warnings") in handlers
