"""Tests for Discord decorators (@slash_command, @on_discord)."""

import pytest

from squadpy.plugin import Plugin, on_event, slash_command, on_discord


class DiscordPlugin(Plugin):
    name = "Discord Test"
    requires = ["discord"]

    @slash_command(name="status", description="Show server status")
    async def show_status(self, interaction):
        pass

    @slash_command(name="reload", description="Reload a plugin")
    async def reload_cmd(self, interaction):
        pass

    @on_discord("button_click", custom_id="claim")
    async def handle_claim(self, interaction):
        pass

    @on_discord("select_menu", custom_id="team_select")
    async def handle_select(self, interaction):
        pass

    @on_discord("modal_submit", custom_id="report_form")
    async def handle_modal(self, interaction):
        pass

    @on_discord("thread_message")
    async def handle_thread(self, message):
        pass


class TestSlashCommandDecorator:
    def test_marks_method_with_metadata(self):
        method = DiscordPlugin.show_status
        assert hasattr(method, "_squadpy_slash_command")
        meta = getattr(method, "_squadpy_slash_command", None)
        assert isinstance(meta, dict)
        assert meta["name"] == "status"
        assert meta["description"] == "Show server status"

    def test_collects_all_slash_commands(self):
        commands = DiscordPlugin.get_slash_commands()
        names = {meta["name"] for meta, _ in commands}
        assert names == {"status", "reload"}

    def test_slash_command_returns(self):
        """Decorator returns list of (meta_dict, method_name) tuples."""
        commands = DiscordPlugin.get_slash_commands()
        for meta, method_name in commands:
            assert isinstance(meta, dict)
            assert isinstance(method_name, str)


class TestOnDiscordDecorator:
    def test_marks_button_click_handler(self):
        method = DiscordPlugin.handle_claim
        assert hasattr(method, "_squadpy_on_discord")
        meta = getattr(method, "_squadpy_on_discord", None)
        assert isinstance(meta, dict)
        assert meta["event_type"] == "button_click"
        assert meta["custom_id"] == "claim"

    def test_marks_select_menu_handler(self):
        meta = getattr(DiscordPlugin.handle_select, "_squadpy_on_discord", None)
        assert isinstance(meta, dict)
        assert meta["event_type"] == "select_menu"
        assert meta["custom_id"] == "team_select"

    def test_marks_modal_submit_handler(self):
        meta = getattr(DiscordPlugin.handle_modal, "_squadpy_on_discord", None)
        assert isinstance(meta, dict)
        assert meta["event_type"] == "modal_submit"
        assert meta["custom_id"] == "report_form"

    def test_marks_thread_message_handler(self):
        meta = getattr(DiscordPlugin.handle_thread, "_squadpy_on_discord", None)
        assert isinstance(meta, dict)
        assert meta["event_type"] == "thread_message"
        assert meta["custom_id"] is None

    def test_collects_all_discord_handlers(self):
        handlers = DiscordPlugin.get_discord_handlers()
        event_types = {meta["event_type"] for meta, _ in handlers}
        assert event_types == {"button_click", "select_menu", "modal_submit", "thread_message"}

    def test_invalid_event_type_raises(self):
        with pytest.raises(ValueError, match="Unknown discord event type"):
            @on_discord("invalid_type", custom_id="x")
            async def bad_handler(self, interaction):
                pass
