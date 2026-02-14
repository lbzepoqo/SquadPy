"""Tests for HeliCrashBroadcast plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import NewGame, PlayerDied, PlayerID
from squadpy.layers import LayerCatalog


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "heli_crash_broadcast",
        Path(__file__).parent.parent / "plugins" / "heli_crash_broadcast" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.HeliCrashBroadcast


def _death(*, victim: str, weapon: str) -> PlayerDied:
    return PlayerDied(
        victim_name=victim,
        damage=100.0,
        attacker=PlayerID(name="Attacker"),
        weapon=weapon,
    )


class TestHeliCrashBroadcast:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "fetch_helicopters_from_layer_source": False,
                "incident_window_seconds": 15,
                "min_victims": 3,
                "cooldown_seconds": 60,
                "heli_weapon_tokens": ["loach", "heli", "mi8"],
                "helicopter_names": [],
                "broadcast_message": "Heli crash? {victim_count} via {weapon} in {window_seconds}s",
                "include_victim_names": False,
                "max_recent_deaths": 50,
                "reset_on_new_game": True,
            },
        )
        await instance.on_enable()
        return instance

    async def test_non_heli_weapon_ignored(self, plugin):
        await plugin.handle_player_died(_death(victim="V1", weapon="BP_Rifle_C"))
        plugin.rcon.broadcast.assert_not_awaited()

    async def test_configured_helicopter_names_support_detection(self, plugin):
        plugin.config["heli_weapon_tokens"] = []
        plugin.config["helicopter_names"] = ["BP_Loach_CAS_Small_C"]
        plugin._test_now = 900.0
        plugin._now = lambda: plugin._test_now

        for victim in ["A", "B", "C"]:
            await plugin.handle_player_died(_death(victim=victim, weapon="BP_M134_Loach_Dual_C"))
            plugin._test_now += 1

        plugin.rcon.broadcast.assert_awaited_once()

    async def test_broadcast_when_threshold_reached_in_window(self, plugin):
        plugin._test_now = 1000.0
        plugin._now = lambda: plugin._test_now

        await plugin.handle_player_died(_death(victim="V1", weapon="BP_M134_Loach_Dual_C"))
        plugin._test_now += 2
        await plugin.handle_player_died(_death(victim="V2", weapon="BP_M134_Loach_Dual_C"))
        plugin._test_now += 2
        await plugin.handle_player_died(_death(victim="V3", weapon="BP_M134_Loach_Dual_C"))

        plugin.rcon.broadcast.assert_awaited_once()
        message = plugin.rcon.broadcast.await_args.args[0]
        assert "3" in message
        assert "BP_M134_Loach_Dual_C" in message

    async def test_outside_window_does_not_trigger(self, plugin):
        plugin._test_now = 2000.0
        plugin._now = lambda: plugin._test_now

        await plugin.handle_player_died(_death(victim="V1", weapon="BP_M134_Loach_Dual_C"))
        plugin._test_now += 16
        await plugin.handle_player_died(_death(victim="V2", weapon="BP_M134_Loach_Dual_C"))
        plugin._test_now += 16
        await plugin.handle_player_died(_death(victim="V3", weapon="BP_M134_Loach_Dual_C"))

        plugin.rcon.broadcast.assert_not_awaited()

    async def test_cooldown_dedupes_repeated_incidents(self, plugin):
        plugin._test_now = 3000.0
        plugin._now = lambda: plugin._test_now

        for victim in ["A", "B", "C"]:
            await plugin.handle_player_died(_death(victim=victim, weapon="BP_M134_Loach_Dual_C"))
            plugin._test_now += 1
        assert plugin.rcon.broadcast.await_count == 1

        for victim in ["D", "E", "F"]:
            await plugin.handle_player_died(_death(victim=victim, weapon="BP_M134_Loach_Dual_C"))
            plugin._test_now += 1
        assert plugin.rcon.broadcast.await_count == 1

        plugin._test_now += 61
        for victim in ["G", "H", "I"]:
            await plugin.handle_player_died(_death(victim=victim, weapon="BP_M134_Loach_Dual_C"))
            plugin._test_now += 1
        assert plugin.rcon.broadcast.await_count == 2

    async def test_new_game_resets_state(self, plugin):
        plugin._recent_deaths.append((1.0, "BP_M134_Loach_Dual_C", "Victim"))
        plugin._last_broadcast_at = 123.0

        await plugin.handle_new_game(NewGame())

        assert not plugin._recent_deaths
        assert plugin._last_broadcast_at == 0.0

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Heli Crash Broadcast"
        assert "rcon" in cls.requires

        handlers = cls.get_event_handlers()
        assert ("player_died", "handle_player_died") in handlers
        assert ("new_game", "handle_new_game") in handlers

    async def test_layer_catalog_names_support_detection(self):
        cls = _load_plugin_class()
        layer_service = cls.on_enable.__globals__["LayerCatalogService"]
        original_fetch = layer_service.fetch

        async def fake_fetch(self):
            return LayerCatalog(
                vehicles_by_class={
                    "HELICOPTER": frozenset({"BP_Loach_CAS_Small_C", "MI8 Transport"})
                }
            )

        layer_service.fetch = fake_fetch
        try:
            instance = cls(
                rcon=AsyncMock(),
                config={
                    "fetch_helicopters_from_layer_source": True,
                    "incident_window_seconds": 15,
                    "min_victims": 3,
                    "cooldown_seconds": 60,
                    "heli_weapon_tokens": [],
                    "helicopter_names": [],
                },
            )
            await instance.on_enable()
            instance._test_now = 5000.0
            instance._now = lambda: instance._test_now

            for victim in ["V1", "V2", "V3"]:
                await instance.handle_player_died(_death(victim=victim, weapon="BP_M134_Loach_Dual_C"))
                instance._test_now += 1

            instance.rcon.broadcast.assert_awaited_once()
        finally:
            layer_service.fetch = original_fetch
