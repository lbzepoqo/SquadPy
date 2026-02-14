"""Tests for DiscordFobHabDamage plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import DeployableDamaged, NewGame


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_fob_hab_damage",
        Path(__file__).parent.parent
        / "plugins"
        / "discord_fob_hab_damage"
        / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordFobHabDamage


def _event(
    *,
    deployable: str,
    damage: float,
    damage_source: str = "SQRadialDamage",
    damage_type: str = "BP_Fragmentation_DamageType_C",
    direct_hit: bool = False,
) -> DeployableDamaged:
    return DeployableDamaged(
        deployable=deployable,
        damage=damage,
        damage_source=damage_source,
        damage_type=damage_type,
        direct_hit=direct_hit,
    )


class TestDiscordFobHabDamage:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={
                "channel_id": 12345,
                "summary_thresholds": [100, 250],
                "hab_keywords": ["hab"],
                "fob_keywords": ["fob", "radio"],
                "include_other_deployables": False,
                "include_damage_metadata": True,
                "reset_on_new_game": True,
            },
        )
        await instance.on_enable()
        return instance

    async def test_sends_summary_when_threshold_crossed(self, plugin):
        await plugin.handle_deployable_damaged(
            _event(deployable="BP_FOBRadio_US_C", damage=60.0, direct_hit=True)
        )
        plugin.discord.send.assert_not_awaited()

        await plugin.handle_deployable_damaged(
            _event(deployable="BP_FOBRadio_US_C", damage=45.0, direct_hit=False)
        )

        plugin.discord.send.assert_awaited_once()
        assert plugin.discord.send.call_args[0][0] == 12345
        content = plugin.discord.send.call_args[1]["content"]
        assert "[FOB/HAB Damage]" in content
        assert "category=FOB" in content
        assert "deployable=BP_FOBRadio_US_C" in content
        assert "hit=45.0" in content
        assert "cumulative=105.0" in content
        assert "threshold=100.0" in content
        assert "source=SQRadialDamage" in content
        assert "type=BP_Fragmentation_DamageType_C" in content
        assert "direct_hit=false" in content

    async def test_crossing_multiple_thresholds_sends_new_summary_each_time(self, plugin):
        await plugin.handle_deployable_damaged(_event(deployable="BP_HAB_US_C", damage=90.0))
        await plugin.handle_deployable_damaged(_event(deployable="BP_HAB_US_C", damage=20.0))
        await plugin.handle_deployable_damaged(_event(deployable="BP_HAB_US_C", damage=130.0))
        await plugin.handle_deployable_damaged(_event(deployable="BP_HAB_US_C", damage=20.0))

        assert plugin.discord.send.await_count == 2
        latest_content = plugin.discord.send.call_args[1]["content"]
        assert "category=HAB" in latest_content
        assert "cumulative=260.0" in latest_content
        assert "threshold=250.0" in latest_content

    async def test_non_fob_hab_deployables_are_ignored_by_default(self, plugin):
        await plugin.handle_deployable_damaged(
            _event(deployable="BP_I_Sandbag_80", damage=500.0)
        )
        plugin.discord.send.assert_not_awaited()

    async def test_reset_on_new_game_clears_threshold_progress(self, plugin):
        await plugin.handle_deployable_damaged(
            _event(deployable="BP_HAB_US_C", damage=120.0)
        )
        plugin.discord.send.assert_awaited_once()

        await plugin.handle_new_game(NewGame())
        await plugin.handle_deployable_damaged(
            _event(deployable="BP_HAB_US_C", damage=110.0)
        )

        assert plugin.discord.send.await_count == 2

    async def test_no_channel_id_skips_send(self):
        cls = _load_plugin_class()
        instance = cls(discord=AsyncMock(), config={"channel_id": 0})
        await instance.on_enable()

        await instance.handle_deployable_damaged(
            _event(deployable="BP_FOBRadio_US_C", damage=500.0)
        )
        instance.discord.send.assert_not_awaited()

    async def test_plugin_attributes_and_handlers(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord FOB/HAB Damage"
        assert "discord" in cls.requires
        handlers = cls.get_event_handlers()
        assert ("deployable_damaged", "handle_deployable_damaged") in handlers
        assert ("new_game", "handle_new_game") in handlers
