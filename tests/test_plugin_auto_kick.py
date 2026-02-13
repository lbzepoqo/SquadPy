"""Tests for AutoKickUnassigned plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "auto_kick_unassigned",
        Path(__file__).parent.parent / "plugins" / "auto_kick_unassigned" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.AutoKickUnassigned


def _make_player(steam_id: str, squad_id: int = 1, team_id: int = 1) -> RconPlayer:
    return RconPlayer(
        id=0, steam_id=steam_id, eos_id="", name=f"Player_{steam_id[-4:]}",
        team_id=team_id, squad_id=squad_id, is_leader=False, role="Rifleman",
    )


class TestAutoKickUnassigned:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        mock_rcon = AsyncMock()
        instance = cls(
            rcon=mock_rcon,
            config={
                "min_players": 3,
                "warnings_before_kick": 3,
                "warning_message": "Join a squad!",
                "kick_message": "Kicked: no squad",
            },
        )
        await instance.on_enable()
        return instance

    async def test_warns_unassigned_players(self, plugin):
        """Unassigned players get warned."""
        plugin.rcon.list_players.return_value = [
            _make_player("1001", squad_id=1),
            _make_player("1002", squad_id=1),
            _make_player("1003", squad_id=0),  # unassigned
        ]
        await plugin.check_unassigned()
        plugin.rcon.warn.assert_awaited_once_with("1003", "Join a squad!")

    async def test_kicks_after_threshold(self, plugin):
        """Player kicked after reaching warning threshold."""
        plugin.rcon.list_players.return_value = [
            _make_player("1001", squad_id=1),
            _make_player("1002", squad_id=1),
            _make_player("1003", squad_id=0),
        ]
        # 3 checks = warnings_before_kick
        await plugin.check_unassigned()  # count=1
        await plugin.check_unassigned()  # count=2
        await plugin.check_unassigned()  # count=3 -> kick

        assert plugin.rcon.warn.await_count == 2
        plugin.rcon.kick.assert_awaited_once_with("1003", "Kicked: no squad")

    async def test_player_joins_squad_clears_warning(self, plugin):
        """Player who joins a squad stops being tracked."""
        plugin.rcon.list_players.return_value = [
            _make_player("1001", squad_id=1),
            _make_player("1002", squad_id=1),
            _make_player("1003", squad_id=0),
        ]
        await plugin.check_unassigned()
        assert "1003" in plugin._warnings

        # Player joins squad
        plugin.rcon.list_players.return_value = [
            _make_player("1001", squad_id=1),
            _make_player("1002", squad_id=1),
            _make_player("1003", squad_id=2),  # now in squad
        ]
        await plugin.check_unassigned()
        assert "1003" not in plugin._warnings

    async def test_below_min_players_no_action(self, plugin):
        """Below min_players threshold, no warnings or kicks."""
        plugin.rcon.list_players.return_value = [
            _make_player("1001", squad_id=0),
            _make_player("1002", squad_id=0),
        ]
        await plugin.check_unassigned()
        plugin.rcon.warn.assert_not_awaited()
        plugin.rcon.kick.assert_not_awaited()

    async def test_new_game_resets_warnings(self, plugin):
        """New game event clears all warnings."""
        plugin._warnings = {"1001": 2, "1002": 1}
        event = MagicMock()
        await plugin.reset_warnings(event)
        assert plugin._warnings == {}

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Auto Kick Unassigned"
        assert "rcon" in cls.requires

    async def test_plugin_has_periodic_task(self):
        cls = _load_plugin_class()
        tasks = cls.get_periodic_tasks()
        names = [name for name, _ in tasks]
        assert "check_unassigned" in names

    async def test_plugin_has_event_handler(self):
        cls = _load_plugin_class()
        handlers = cls.get_event_handlers()
        events = [ev for ev, _ in handlers]
        assert "new_game" in events
