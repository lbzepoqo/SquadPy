"""Tests for SquadNameValidator plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import NewGame, PlayerID, SquadCreated
from squadpy.rcon.types import RconSquad


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "squad_name_validator",
        Path(__file__).parent.parent / "plugins" / "squad_name_validator" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.SquadNameValidator


def _squad(
    squad_id: int,
    name: str,
    leader_id: str,
    *,
    team_id: int = 1,
) -> RconSquad:
    return RconSquad(
        id=squad_id,
        name=name,
        size=5,
        locked=False,
        creator_name=f"Leader_{leader_id}",
        creator_steam_id=leader_id,
        creator_eos_id="",
        team_id=team_id,
        team_name="TeamOne",
    )


class TestSquadNameValidator:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "validate_on_create": True,
                "min_length": 3,
                "max_length": 20,
                "ignore_case": True,
                "blocked_exact_names": [],
                "blocked_terms": ["admin"],
                "invalid_patterns": [r"^squad\s*\d+$"],
                "required_pattern": "",
                "enforcement_action": "warn_then_kick",
                "warnings_before_kick": 2,
                "exempt_steam_ids": [],
                "exempt_squad_ids": [],
                "warning_message": "Invalid squad {squad_id}: {squad_name} ({warnings_remaining})",
                "kick_reason": "Kick invalid squad {squad_id}: {squad_name}",
            },
        )
        await instance.on_enable()
        return instance

    async def test_warn_then_kick_on_repeated_invalid_name(self, plugin):
        plugin.rcon.list_squads.return_value = [_squad(1, "SQUAD 1", "steam1")]

        await plugin.validate_squads()
        plugin.rcon.warn.assert_awaited_once_with("steam1", "Invalid squad 1: SQUAD 1 (1)")
        plugin.rcon.kick.assert_not_awaited()

        await plugin.validate_squads()
        plugin.rcon.kick.assert_awaited_once_with("steam1", "Kick invalid squad 1: SQUAD 1")

    async def test_warn_only_mode_never_kicks(self, plugin):
        plugin.config["enforcement_action"] = "warn"
        plugin.rcon.list_squads.return_value = [_squad(2, "SQUAD 2", "steam2")]

        await plugin.validate_squads()
        await plugin.validate_squads()

        assert plugin.rcon.warn.await_count == 2
        plugin.rcon.kick.assert_not_awaited()

    async def test_immediate_kick_mode(self, plugin):
        plugin.config["enforcement_action"] = "kick"
        plugin.rcon.list_squads.return_value = [_squad(3, "SQUAD 3", "steam3")]

        await plugin.validate_squads()

        plugin.rcon.warn.assert_not_awaited()
        plugin.rcon.kick.assert_awaited_once_with("steam3", "Kick invalid squad 3: SQUAD 3")

    async def test_exempt_player_and_squad_skipped(self, plugin):
        plugin.config["enforcement_action"] = "kick"
        plugin.config["exempt_steam_ids"] = ["steam4"]
        plugin.config["exempt_squad_ids"] = [5]
        plugin.rcon.list_squads.return_value = [
            _squad(4, "SQUAD 4", "steam4"),
            _squad(5, "SQUAD 5", "steam5"),
        ]

        await plugin.validate_squads()

        plugin.rcon.warn.assert_not_awaited()
        plugin.rcon.kick.assert_not_awaited()

    async def test_valid_name_clears_violation_state(self, plugin):
        plugin.rcon.list_squads.side_effect = [
            [_squad(6, "SQUAD 6", "steam6")],
            [_squad(6, "INF LAT", "steam6")],
            [_squad(6, "SQUAD 6", "steam6")],
        ]

        await plugin.validate_squads()
        await plugin.validate_squads()
        await plugin.validate_squads()

        assert plugin.rcon.warn.await_count == 2
        plugin.rcon.kick.assert_not_awaited()

    async def test_squad_created_event_validates_immediately(self, plugin):
        event = SquadCreated(
            team_id=1,
            team_name="USA",
            squad_id=7,
            squad_name="SQUAD 7",
            creator=PlayerID(name="SL7", steam_id="steam7"),
        )

        await plugin.handle_squad_created(event)

        plugin.rcon.warn.assert_awaited_once_with("steam7", "Invalid squad 7: SQUAD 7 (1)")

    async def test_new_game_resets_violation_counts(self, plugin):
        plugin.rcon.list_squads.return_value = [_squad(8, "SQUAD 8", "steam8")]
        await plugin.validate_squads()
        assert plugin._violation_counts

        await plugin.reset_state(NewGame())
        assert plugin._violation_counts == {}

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Squad Name Validator"
        assert "rcon" in cls.requires

        periodic_tasks = cls.get_periodic_tasks()
        assert ("validate_squads", 30) in periodic_tasks

        handlers = cls.get_event_handlers()
        assert ("squad_created", "handle_squad_created") in handlers
        assert ("new_game", "reset_state") in handlers
