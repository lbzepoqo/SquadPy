"""Tests for KnifeBroadcast plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import NewGame, PlayerDied, PlayerID
from squadpy.layers import LayerCatalog


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "knife_broadcast",
        Path(__file__).parent.parent / "plugins" / "knife_broadcast" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.KnifeBroadcast


def _death(*, attacker: str, victim: str, weapon: str) -> PlayerDied:
    return PlayerDied(
        victim_name=victim,
        damage=100.0,
        attacker=PlayerID(name=attacker),
        weapon=weapon,
    )


class TestKnifeBroadcast:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "fetch_melee_weapons_from_layer_source": False,
                "cooldown_seconds": 5,
                "knife_weapon_tokens": ["knife", "bayonet"],
                "melee_weapon_names": [],
                "broadcast_message": "{attacker} knifed {victim} with {weapon}!",
                "include_weapon_name": True,
                "reset_on_new_game": True,
            },
        )
        await instance.on_enable()
        return instance

    async def test_non_melee_weapon_ignored(self, plugin):
        await plugin.handle_player_died(_death(attacker="A", victim="V", weapon="BP_Rifle_C"))
        plugin.rcon.broadcast.assert_not_awaited()

    async def test_broadcasts_for_knife_weapon_token(self, plugin):
        plugin._now = lambda: 100.0
        await plugin.handle_player_died(
            _death(attacker="Blade", victim="Target", weapon="BP_Knife_Combat_C")
        )
        plugin.rcon.broadcast.assert_awaited_once()
        message = plugin.rcon.broadcast.await_args.args[0]
        assert "Blade" in message
        assert "Target" in message
        assert "BP_Knife_Combat_C" in message

    async def test_cooldown_prevents_repeat_broadcasts(self, plugin):
        plugin._test_now = 200.0
        plugin._now = lambda: plugin._test_now

        await plugin.handle_player_died(_death(attacker="A", victim="B", weapon="BP_Knife_Combat_C"))
        await plugin.handle_player_died(_death(attacker="C", victim="D", weapon="BP_Knife_Combat_C"))
        assert plugin.rcon.broadcast.await_count == 1

        plugin._test_now += 6
        await plugin.handle_player_died(_death(attacker="E", victim="F", weapon="BP_Knife_Combat_C"))
        assert plugin.rcon.broadcast.await_count == 2

    async def test_configured_melee_names_support_detection(self, plugin):
        plugin.config["knife_weapon_tokens"] = []
        plugin.config["melee_weapon_names"] = ["BP_Melee_Kukri_C"]
        plugin._now = lambda: 500.0

        await plugin.handle_player_died(_death(attacker="A", victim="B", weapon="BP_Melee_Kukri_C"))
        plugin.rcon.broadcast.assert_awaited_once()

    async def test_layer_catalog_melee_names_support_detection(self):
        cls = _load_plugin_class()
        layer_service = cls.on_enable.__globals__["LayerCatalogService"]
        original_fetch = layer_service.fetch

        async def fake_fetch(self):
            return LayerCatalog(melee_weapons=frozenset({"BP_Melee_Dagger_C"}))

        layer_service.fetch = fake_fetch
        try:
            instance = cls(
                rcon=AsyncMock(),
                config={
                    "fetch_melee_weapons_from_layer_source": True,
                    "knife_weapon_tokens": [],
                    "melee_weapon_names": [],
                    "cooldown_seconds": 0,
                },
            )
            await instance.on_enable()
            instance._now = lambda: 800.0

            await instance.handle_player_died(
                _death(attacker="A", victim="B", weapon="BP_Melee_Dagger_C")
            )
            instance.rcon.broadcast.assert_awaited_once()
        finally:
            layer_service.fetch = original_fetch

    async def test_new_game_resets_cooldown_state(self, plugin):
        plugin._last_broadcast_at = 321.0
        await plugin.handle_new_game(NewGame())
        assert plugin._last_broadcast_at == 0.0

    async def test_can_hide_weapon_name(self, plugin):
        plugin.config["include_weapon_name"] = False
        plugin.config["broadcast_message"] = "{attacker} knifed {victim}!"
        plugin._now = lambda: 900.0

        await plugin.handle_player_died(
            _death(attacker="NoWeapon", victim="Shown", weapon="BP_Knife_Combat_C")
        )

        plugin.rcon.broadcast.assert_awaited_once()
        assert plugin.rcon.broadcast.await_args.args[0] == "NoWeapon knifed Shown!"

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Knife Broadcast"
        assert "rcon" in cls.requires

        handlers = cls.get_event_handlers()
        assert ("player_died", "handle_player_died") in handlers
        assert ("new_game", "handle_new_game") in handlers
