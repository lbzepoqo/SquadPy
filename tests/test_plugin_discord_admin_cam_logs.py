"""Tests for DiscordAdminCamLogs plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import AdminCamPossess, AdminCamUnpossess, PlayerID


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "discord_admin_cam_logs",
        Path(__file__).parent.parent / "plugins" / "discord_admin_cam_logs" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.DiscordAdminCamLogs


class TestDiscordAdminCamLogs:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_context": True},
        )
        return instance

    async def test_admin_cam_possess_sent_to_discord(self, plugin):
        event = AdminCamPossess(
            admin=PlayerID(name="AdminOne", steam_id="76561198000000001"),
            target="TargetPlayer",
            context={"layer": "Narva_AAS_v1", "team": 1},
        )

        await plugin.handle_admin_cam_possess(event)

        plugin.discord.send.assert_awaited_once()
        assert plugin.discord.send.call_args[0][0] == 12345
        content = plugin.discord.send.call_args[1]["content"]
        assert "AdminOne" in content
        assert "possess" in content
        assert "TargetPlayer" in content
        assert "layer=Narva_AAS_v1" in content

    async def test_admin_cam_unpossess_sent_to_discord(self, plugin):
        event = AdminCamUnpossess(
            admin=PlayerID(name="AdminTwo", steam_id="76561198000000002"),
            target="TargetPlayer",
            context={"duration_seconds": 42},
        )

        await plugin.handle_admin_cam_unpossess(event)

        plugin.discord.send.assert_awaited_once()
        content = plugin.discord.send.call_args[1]["content"]
        assert "AdminTwo" in content
        assert "unpossess" in content
        assert "duration_seconds=42" in content

    async def test_no_channel_id_skips_send(self):
        cls = _load_plugin_class()
        instance = cls(discord=AsyncMock(), config={"channel_id": 0})

        event = AdminCamPossess(admin=PlayerID(name="AdminOne"), target="TargetPlayer")
        await instance.handle_admin_cam_possess(event)

        instance.discord.send.assert_not_awaited()

    async def test_context_disabled_omits_context_text(self):
        cls = _load_plugin_class()
        instance = cls(
            discord=AsyncMock(),
            config={"channel_id": 12345, "include_context": False},
        )

        event = AdminCamPossess(
            admin=PlayerID(name="AdminOne", steam_id="76561198000000001"),
            target="TargetPlayer",
            context={"foo": "bar"},
        )

        await instance.handle_admin_cam_possess(event)

        content = instance.discord.send.call_args[1]["content"]
        assert "context:" not in content

    async def test_plugin_attributes(self):
        cls = _load_plugin_class()
        assert cls.name == "Discord Admin Cam Logs"
        assert "discord" in cls.requires
        assert cls.get_event_handlers() == [
            ("admin_cam_possess", "handle_admin_cam_possess"),
            ("admin_cam_unpossess", "handle_admin_cam_unpossess"),
        ]
