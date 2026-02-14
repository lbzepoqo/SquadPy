"""Tests for SwitchCommand plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import ChatMessage


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "switch_command",
        Path(__file__).parent.parent / "plugins" / "switch_command" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.SwitchCommand


def _chat(
    message: str,
    *,
    steam_id: str = "steam_user",
    eos_id: str = "",
    channel: str = "ChatAll",
) -> ChatMessage:
    return ChatMessage(
        player_name="Player",
        steam_id=steam_id,
        eos_id=eos_id,
        channel=channel,
        message=message,
    )


class TestSwitchCommand:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "command": "!switch",
                "cooldown_seconds": 60,
                "allowed_channels": ["ChatAll", "ChatTeam"],
                "notify_on_success": True,
                "success_message": "Switch queued ({cooldown}s)",
                "cooldown_message": "Wait {remaining}s before {command}",
            },
        )
        await instance.on_enable()
        return instance

    async def test_dispatches_switch_team_for_command(self, plugin):
        """Matching command switches requesting player."""
        await plugin.handle_chat(_chat("!switch", steam_id="steam_a"))

        plugin.rcon.switch_team.assert_awaited_once_with("steam_a")
        plugin.rcon.warn.assert_awaited_once_with("steam_a", "Switch queued (60s)")

    async def test_cooldown_blocks_repeat_requests(self, plugin):
        """Repeated requests within cooldown are rejected."""
        plugin.config["notify_on_success"] = False
        plugin._test_now = 1000.0
        plugin._now = lambda: plugin._test_now

        await plugin.handle_chat(_chat("!switch", steam_id="steam_a"))
        plugin._test_now = 1030.0
        await plugin.handle_chat(_chat("!switch", steam_id="steam_a"))

        plugin.rcon.switch_team.assert_awaited_once_with("steam_a")
        plugin.rcon.warn.assert_awaited_once_with("steam_a", "Wait 30s before !switch")

    async def test_non_allowed_channel_is_ignored(self, plugin):
        """Configured channel filters are respected."""
        plugin.config["allowed_channels"] = ["ChatTeam"]
        await plugin.handle_chat(_chat("!switch", channel="ChatAll"))
        plugin.rcon.switch_team.assert_not_awaited()
        plugin.rcon.warn.assert_not_awaited()

    async def test_ignores_non_matching_messages(self, plugin):
        """Only matching command token triggers switch flow."""
        await plugin.handle_chat(_chat("hello"))
        await plugin.handle_chat(_chat("!switch now"))
        plugin.rcon.switch_team.assert_not_awaited()
        plugin.rcon.warn.assert_not_awaited()

    async def test_falls_back_to_eos_id_when_steam_id_missing(self, plugin):
        """EOS ID is used when Steam ID is absent."""
        await plugin.handle_chat(_chat("!switch", steam_id="", eos_id="eos_1"))
        plugin.rcon.switch_team.assert_awaited_once_with("eos_1")

    async def test_plugin_attributes_and_handlers(self):
        cls = _load_plugin_class()
        assert cls.name == "Switch Command"
        assert "rcon" in cls.requires

        handlers = cls.get_event_handlers()
        assert ("chat_message", "handle_chat") in handlers
