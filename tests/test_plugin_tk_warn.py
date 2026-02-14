"""Tests for TKWarn plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.events.types import PlayerID, PlayerWounded, Teamkill
from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "tk_warn",
        Path(__file__).parent.parent / "plugins" / "tk_warn" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.TKWarn


def _make_rcon_player(name: str, steam_id: str, team_id: int) -> RconPlayer:
    return RconPlayer(
        id=0,
        steam_id=steam_id,
        eos_id="",
        name=name,
        team_id=team_id,
        squad_id=1,
        is_leader=False,
        role="Rifleman",
    )


def _make_wound_event(victim_name: str, attacker_name: str) -> PlayerWounded:
    return PlayerWounded(
        victim_name=victim_name,
        attacker=PlayerID(name=attacker_name),
    )


def _make_teamkill_event(
    attacker_name: str = "Attacker",
    attacker_steam_id: str = "steam_atk",
    victim_name: str = "Victim",
    victim_steam_id: str = "steam_vic",
) -> Teamkill:
    return Teamkill(
        attacker=PlayerID(name=attacker_name, steam_id=attacker_steam_id),
        victim=PlayerID(name=victim_name, steam_id=victim_steam_id),
        weapon="Rifle",
    )


class TestTKWarn:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        instance = cls(
            rcon=mock_rcon,
            config={
                "event_source": "teamkill",
                "kick_threshold": 3,
                "warning_message": "TK #{count}. {threshold} = kick.",
                "kick_message": "Kicked for TK ({count})",
            },
        )
        await instance.on_enable()
        # Pre-populate player cache for player_wounded mode tests.
        instance._player_cache = {
            "Attacker": _make_rcon_player("Attacker", "steam_atk", team_id=1),
            "Victim": _make_rcon_player("Victim", "steam_vic", team_id=1),
            "Enemy": _make_rcon_player("Enemy", "steam_enemy", team_id=2),
        }
        return instance

    async def test_tk_detected_teamkill_event(self, plugin):
        """Teamkill event increments count and warns offender."""
        await plugin.handle_teamkill(_make_teamkill_event())
        plugin.rcon.warn.assert_awaited_once_with("steam_atk", "TK #1. 3 = kick.")

    async def test_no_tk_self_target_ignored(self, plugin):
        """Self-targeted event is ignored."""
        event = _make_teamkill_event(victim_steam_id="steam_atk")
        await plugin.handle_teamkill(event)
        plugin.rcon.warn.assert_not_awaited()
        plugin.rcon.kick.assert_not_awaited()

    async def test_count_increments(self, plugin):
        """TK count increments with each offense."""
        event = _make_teamkill_event()
        await plugin.handle_teamkill(event)
        await plugin.handle_teamkill(event)
        assert plugin._tk_counts["steam_atk"] == 2
        assert plugin.rcon.warn.await_count == 2

    async def test_kick_at_threshold(self, plugin):
        """Player kicked when reaching kick_threshold."""
        event = _make_teamkill_event()
        await plugin.handle_teamkill(event)  # 1 - warn
        await plugin.handle_teamkill(event)  # 2 - warn
        await plugin.handle_teamkill(event)  # 3 - kick
        assert plugin.rcon.warn.await_count == 2
        plugin.rcon.kick.assert_awaited_once_with("steam_atk", "Kicked for TK (3)")

    async def test_kick_only_once_after_threshold(self, plugin):
        """Further TK events after kick do not trigger repeated actions."""
        event = _make_teamkill_event()
        await plugin.handle_teamkill(event)
        await plugin.handle_teamkill(event)
        await plugin.handle_teamkill(event)  # kicked
        await plugin.handle_teamkill(event)  # ignored
        assert plugin.rcon.warn.await_count == 2
        assert plugin.rcon.kick.await_count == 1

    async def test_warning_cooldown_suppresses_repeat_warns(self, plugin):
        """Warning cooldown suppresses warning spam but still tracks counts."""
        plugin.config["warning_cooldown_seconds"] = 60
        event = _make_teamkill_event()
        await plugin.handle_teamkill(event)  # warn
        await plugin.handle_teamkill(event)  # suppressed warn
        await plugin.handle_teamkill(event)  # kick at threshold
        assert plugin.rcon.warn.await_count == 1
        assert plugin.rcon.kick.await_count == 1

    async def test_invalid_threshold_falls_back_to_default(self, plugin):
        """Invalid threshold values fall back to safe default."""
        plugin.config["kick_threshold"] = "bad"
        event = _make_teamkill_event()
        await plugin.handle_teamkill(event)
        await plugin.handle_teamkill(event)
        await plugin.handle_teamkill(event)
        await plugin.handle_teamkill(event)
        # default threshold is 5, so only warnings after 4 events
        assert plugin.rcon.warn.await_count == 4
        plugin.rcon.kick.assert_not_awaited()

    async def test_message_template_edge_case_no_crash(self, plugin):
        """Unknown format keys in messages are handled safely."""
        plugin.config["warning_message"] = "Warning for {unknown_key}"
        await plugin.handle_teamkill(_make_teamkill_event())
        plugin.rcon.warn.assert_awaited_once_with("steam_atk", "Warning for {unknown_key}")

    async def test_player_wounded_mode_works(self, plugin):
        """Legacy player_wounded mode still detects TK from player cache."""
        plugin.config["event_source"] = "player_wounded"
        await plugin.handle_wound(_make_wound_event("Victim", "Attacker"))
        plugin.rcon.warn.assert_awaited_once_with("steam_atk", "TK #1. 3 = kick.")

    async def test_player_wounded_mode_ignores_teamkill_event(self, plugin):
        """Mode selection prevents double-counting across sources."""
        plugin.config["event_source"] = "player_wounded"
        await plugin.handle_teamkill(_make_teamkill_event())
        plugin.rcon.warn.assert_not_awaited()

    async def test_missing_player_no_crash(self, plugin):
        """Unknown player in cache does not raise."""
        plugin.config["event_source"] = "player_wounded"
        await plugin.handle_wound(_make_wound_event("UnknownVictim", "UnknownAttacker"))
        plugin.rcon.warn.assert_not_awaited()

    async def test_new_game_resets_counts(self, plugin):
        """New game event clears local state by default."""
        plugin._tk_counts = {"steam_atk": 2}
        plugin._kicked = {"steam_atk"}
        plugin._last_warning_at = {"steam_atk": 12.0}
        await plugin.reset_counts(MagicMock())
        assert plugin._tk_counts == {}
        assert plugin._kicked == set()
        assert plugin._last_warning_at == {}

    async def test_reset_can_be_disabled(self, plugin):
        """Config can preserve counts across new_game events."""
        plugin.config["reset_on_new_game"] = False
        plugin._tk_counts = {"steam_atk": 2}
        await plugin.reset_counts(MagicMock())
        assert plugin._tk_counts == {"steam_atk": 2}

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

    async def test_plugin_handlers_registered(self):
        cls = _load_plugin_class()
        handlers = cls.get_event_handlers()
        events = [ev for ev, _ in handlers]
        assert "teamkill" in events
        assert "player_wounded" in events
        assert "new_game" in events
