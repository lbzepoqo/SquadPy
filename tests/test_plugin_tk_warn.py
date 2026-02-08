"""Tests for TKWarn plugin."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.events.types import PlayerWounded, PlayerID
from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "tk_warn",
        Path(__file__).parent.parent / "plugins" / "tk_warn" / "plugin.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TKWarn


def _make_rcon_player(name: str, steam_id: str, team_id: int) -> RconPlayer:
    return RconPlayer(
        id=0, steam_id=steam_id, eos_id="", name=name,
        team_id=team_id, squad_id=1, is_leader=False, role="Rifleman",
    )


def _make_wound_event(victim_name: str, attacker_name: str) -> PlayerWounded:
    return PlayerWounded(
        victim_name=victim_name,
        attacker=PlayerID(name=attacker_name),
    )


class TestTKWarn:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        instance = cls(
            rcon=mock_rcon,
            config={
                "kick_threshold": 3,
                "warning_message": "TK #{count}. {threshold} = kick.",
                "kick_message": "Kicked for TK ({count})",
            },
        )
        await instance.on_enable()
        # Pre-populate player cache
        instance._player_cache = {
            "Attacker": _make_rcon_player("Attacker", "steam_atk", team_id=1),
            "Victim": _make_rcon_player("Victim", "steam_vic", team_id=1),
            "Enemy": _make_rcon_player("Enemy", "steam_enemy", team_id=2),
        }
        return instance

    async def test_tk_detected_same_team(self, plugin):
        """Wounding same-team player triggers TK warning."""
        event = _make_wound_event("Victim", "Attacker")
        await plugin.handle_wound(event)
        plugin.rcon.warn.assert_awaited_once()
        assert "TK #1" in plugin.rcon.warn.call_args[0][1]

    async def test_no_tk_different_teams(self, plugin):
        """Wounding enemy player is NOT a TK."""
        event = _make_wound_event("Enemy", "Attacker")
        await plugin.handle_wound(event)
        plugin.rcon.warn.assert_not_awaited()
        plugin.rcon.kick.assert_not_awaited()

    async def test_count_increments(self, plugin):
        """TK count increments with each offense."""
        event = _make_wound_event("Victim", "Attacker")
        await plugin.handle_wound(event)
        await plugin.handle_wound(event)
        assert plugin._tk_counts["steam_atk"] == 2
        assert plugin.rcon.warn.await_count == 2

    async def test_kick_at_threshold(self, plugin):
        """Player kicked when reaching kick_threshold."""
        event = _make_wound_event("Victim", "Attacker")
        await plugin.handle_wound(event)  # 1 - warn
        await plugin.handle_wound(event)  # 2 - warn
        await plugin.handle_wound(event)  # 3 - kick
        assert plugin.rcon.warn.await_count == 2
        plugin.rcon.kick.assert_awaited_once()
        assert "Kicked for TK (3)" in plugin.rcon.kick.call_args[0][1]

    async def test_self_damage_ignored(self, plugin):
        """Self-damage (attacker == victim) is NOT a TK."""
        event = _make_wound_event("Attacker", "Attacker")
        await plugin.handle_wound(event)
        plugin.rcon.warn.assert_not_awaited()

    async def test_missing_player_no_crash(self, plugin):
        """Unknown player in cache doesn't crash."""
        event = _make_wound_event("UnknownVictim", "UnknownAttacker")
        await plugin.handle_wound(event)
        plugin.rcon.warn.assert_not_awaited()

    async def test_new_game_resets_counts(self, plugin):
        """New game resets TK counts."""
        plugin._tk_counts = {"steam_atk": 4}
        event = MagicMock()
        await plugin.reset_counts(event)
        assert plugin._tk_counts == {}

    async def test_refresh_players_updates_cache(self, plugin):
        """Periodic refresh updates player cache from RCON."""
        new_player = _make_rcon_player("NewGuy", "steam_new", team_id=1)
        plugin.rcon.list_players.return_value = [new_player]
        await plugin.refresh_players()
        assert "NewGuy" in plugin._player_cache

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "TK Warn"
        assert "rcon" in cls.requires
