"""Tests for SeedingMode plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "seeding_mode",
        Path(__file__).parent.parent / "plugins" / "seeding_mode" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.SeedingMode


def _players(count: int) -> list[RconPlayer]:
    out: list[RconPlayer] = []
    for idx in range(count):
        out.append(
            RconPlayer(
                id=idx,
                steam_id=f"steam_{idx}",
                eos_id="",
                name=f"Player{idx}",
                team_id=1,
                squad_id=1,
                is_leader=False,
                role="Rifleman",
            )
        )
    return out


class TestSeedingMode:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "seed_player_threshold": 50,
                "announce_transitions": True,
                "announce_initial_mode": False,
                "seed_mode_message": "Seed ({players}/{threshold})",
                "live_mode_message": "Live ({players}/{threshold})",
                "set_fog_of_war_on_transition": False,
            },
        )
        await instance.on_enable()
        return instance

    async def test_initial_mode_not_announced_by_default(self, plugin):
        """Initial mode snapshot does not announce unless enabled."""
        plugin.rcon.list_players.return_value = _players(20)
        await plugin.evaluate_mode()

        assert plugin.mode == "seed"
        plugin.rcon.broadcast.assert_not_awaited()

    async def test_seed_to_live_transition_announced(self, plugin):
        """Crossing threshold to live mode emits transition message."""
        plugin.rcon.list_players.return_value = _players(20)
        await plugin.evaluate_mode()  # initial seed, no announcement
        plugin.rcon.list_players.return_value = _players(60)
        await plugin.evaluate_mode()

        assert plugin.mode == "live"
        plugin.rcon.broadcast.assert_awaited_once_with("Live (60/50)")

    async def test_live_to_seed_transition_announced(self, plugin):
        """Dropping below threshold emits seed transition message."""
        plugin.rcon.list_players.return_value = _players(60)
        await plugin.evaluate_mode()  # initial live, no announcement
        plugin.rcon.list_players.return_value = _players(40)
        await plugin.evaluate_mode()

        assert plugin.mode == "seed"
        plugin.rcon.broadcast.assert_awaited_once_with("Seed (40/50)")

    async def test_no_repeat_action_when_mode_unchanged(self, plugin):
        """Unchanged mode does not repeatedly announce."""
        plugin.rcon.list_players.return_value = _players(20)
        await plugin.evaluate_mode()
        await plugin.evaluate_mode()
        await plugin.evaluate_mode()
        plugin.rcon.broadcast.assert_not_awaited()

    async def test_announce_initial_mode_option(self, plugin):
        """Initial mode announcement can be enabled."""
        plugin.config["announce_initial_mode"] = True
        plugin.rcon.list_players.return_value = _players(20)
        await plugin.evaluate_mode()
        plugin.rcon.broadcast.assert_awaited_once_with("Seed (20/50)")

    async def test_fog_of_war_toggles_on_transitions(self, plugin):
        """Optional fog mode commands fire on transitions."""
        plugin.config["set_fog_of_war_on_transition"] = True
        plugin.config["seed_fog_mode"] = "1"
        plugin.config["live_fog_mode"] = "0"

        plugin.rcon.list_players.return_value = _players(60)
        await plugin.evaluate_mode()  # initial live, no action
        plugin.rcon.list_players.return_value = _players(40)
        await plugin.evaluate_mode()  # live -> seed

        plugin.rcon.set_fog_of_war.assert_awaited_once_with("1")

    async def test_invalid_threshold_uses_fallback(self, plugin):
        """Invalid threshold config falls back to default 50."""
        plugin.config["seed_player_threshold"] = "bad"
        plugin.config["announce_initial_mode"] = True
        plugin.rcon.list_players.return_value = _players(60)
        await plugin.evaluate_mode()
        assert plugin.mode == "live"
        plugin.rcon.broadcast.assert_awaited_once_with("Live (60/50)")

    async def test_new_game_resets_mode(self, plugin):
        """New game resets mode by default."""
        plugin._mode = "live"
        await plugin.handle_new_game(MagicMock())
        assert plugin.mode is None

    async def test_plugin_attributes_and_handlers(self):
        cls = _load_plugin_class()
        assert cls.name == "Seeding Mode"
        assert "rcon" in cls.requires
        handlers = cls.get_event_handlers()
        events = [ev for ev, _ in handlers]
        assert "new_game" in events
        tasks = cls.get_periodic_tasks()
        names = [name for name, _ in tasks]
        assert "evaluate_mode" in names
