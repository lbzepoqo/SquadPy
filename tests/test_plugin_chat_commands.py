"""Tests for ChatCommands plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import ChatMessage


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "chat_commands",
        Path(__file__).parent.parent / "plugins" / "chat_commands" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.ChatCommands


def _chat(message: str, steam_id: str = "steam_user") -> ChatMessage:
    return ChatMessage(
        player_name="Player",
        steam_id=steam_id,
        eos_id="",
        channel="ChatAll",
        message=message,
    )


class TestChatCommands:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "command_prefix": "!",
                "default_role": "user",
                "roles_order": ["user", "mod", "admin"],
                "user_roles": {
                    "steam_mod": "mod",
                    "steam_admin": "admin",
                },
                "commands": {
                    "broadcast": {"min_role": "mod", "cooldown_seconds": 60},
                    "warn": {"min_role": "mod", "cooldown_seconds": 0},
                    "kick": {"min_role": "admin", "cooldown_seconds": 0},
                },
                "denied_message": "Denied !{command}",
                "cooldown_message": "Cooldown !{command} ({remaining}s)",
                "usage_message": "Usage: {usage}",
            },
        )
        await instance.on_enable()
        return instance

    async def test_broadcast_requires_role(self, plugin):
        """Users without required role are denied."""
        await plugin.handle_chat(_chat("!broadcast hello", steam_id="steam_user"))
        plugin.rcon.broadcast.assert_not_awaited()
        plugin.rcon.warn.assert_awaited_once_with("steam_user", "Denied !broadcast")

    async def test_broadcast_allowed_for_moderator(self, plugin):
        """Role-gated command executes for permitted role."""
        await plugin.handle_chat(_chat("!broadcast hello world", steam_id="steam_mod"))
        plugin.rcon.broadcast.assert_awaited_once_with("hello world")
        plugin.rcon.warn.assert_not_awaited()

    async def test_command_cooldown_blocks_repeat(self, plugin):
        """Cooldown blocks repeated command usage by same actor."""
        await plugin.handle_chat(_chat("!broadcast first", steam_id="steam_mod"))
        await plugin.handle_chat(_chat("!broadcast second", steam_id="steam_mod"))

        # first call executes, second call blocked by cooldown
        plugin.rcon.broadcast.assert_awaited_once_with("first")
        plugin.rcon.warn.assert_awaited_once()
        args = plugin.rcon.warn.call_args[0]
        assert args[0] == "steam_mod"
        assert "Cooldown !broadcast" in args[1]

    async def test_warn_command_usage_and_dispatch(self, plugin):
        """Warn command validates args and dispatches RCON warn."""
        await plugin.handle_chat(_chat("!warn steam_target stop teamkilling", steam_id="steam_mod"))
        plugin.rcon.warn.assert_awaited_once_with("steam_target", "stop teamkilling")

    async def test_warn_command_usage_message(self, plugin):
        """Warn command emits usage message on invalid args."""
        await plugin.handle_chat(_chat("!warn steam_target", steam_id="steam_mod"))
        plugin.rcon.warn.assert_awaited_once()
        args = plugin.rcon.warn.call_args[0]
        assert args[0] == "steam_mod"
        assert "Usage: !warn <player_id> <reason>" in args[1]

    async def test_kick_command_requires_admin(self, plugin):
        """Kick command enforces stronger role requirement."""
        await plugin.handle_chat(_chat("!kick steam_target bad behavior", steam_id="steam_mod"))
        plugin.rcon.kick.assert_not_awaited()
        plugin.rcon.warn.assert_awaited_once_with("steam_mod", "Denied !kick")

    async def test_kick_command_for_admin(self, plugin):
        """Kick command executes for admin role."""
        await plugin.handle_chat(_chat("!kick steam_target repeated tk", steam_id="steam_admin"))
        plugin.rcon.kick.assert_awaited_once_with("steam_target", "repeated tk")

    async def test_unknown_command_ignored(self, plugin):
        """Unknown commands are ignored."""
        await plugin.handle_chat(_chat("!does_not_exist 1 2 3", steam_id="steam_admin"))
        plugin.rcon.warn.assert_not_awaited()
        plugin.rcon.broadcast.assert_not_awaited()
        plugin.rcon.kick.assert_not_awaited()

    async def test_plugin_attributes_and_handlers(self):
        cls = _load_plugin_class()
        assert cls.name == "Chat Commands"
        assert "rcon" in cls.requires
        handlers = cls.get_event_handlers()
        assert ("chat_message", "handle_chat") in handlers
