"""Tests for the built-in PluginManager plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _load_plugin_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "plugin_manager",
        Path(__file__).parent.parent / "plugins" / "plugin_manager" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class TestPluginManagerImport:
    def test_can_import_plugin(self):
        """PluginManager plugin can be imported."""
        module = _load_plugin_module()
        assert hasattr(module, "PluginManager")

    def test_plugin_has_required_attributes(self):
        module = _load_plugin_module()
        cls = module.PluginManager

        assert cls.name == "Plugin Manager"
        assert "rcon" in cls.requires
        assert "discord" in cls.requires

    def test_plugin_has_slash_commands(self):
        module = _load_plugin_module()
        cls = module.PluginManager

        commands = cls.get_slash_commands()
        names = {meta["name"] for meta, _ in commands}
        assert "status" in names
        assert "plugins" in names
        assert "reload" in names


class TestPluginManagerHandlers:
    @pytest.fixture
    async def plugin(self):
        module = _load_plugin_module()

        mock_rcon = MagicMock()
        mock_discord = MagicMock()
        mock_server = MagicMock()
        mock_server.version = "0.1.0"
        mock_server.running = True
        mock_server._loaded_plugins = []

        plugin_instance = module.PluginManager(
            rcon=mock_rcon,
            discord=mock_discord,
            config={"admin_role_id": 123456},
            server=mock_server,
        )
        await plugin_instance.on_enable()
        return plugin_instance

    async def test_status_command_responds(self, plugin):
        """The /status command sends a response."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        await plugin.status_cmd(interaction)
        interaction.response.send_message.assert_awaited_once()

    async def test_plugins_command_responds(self, plugin):
        """The /plugins command sends a response."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        await plugin.plugins_cmd(interaction)
        interaction.response.send_message.assert_awaited_once()

    async def test_reload_command_calls_server(self, plugin):
        """The /reload command calls server.reload_plugin()."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.roles = [MagicMock(id=123456)]
        plugin.server.reload_plugin = AsyncMock(return_value=(True, ""))
        await plugin.reload_cmd(interaction, plugin_name="test_plugin")
        plugin.server.reload_plugin.assert_awaited_once_with("test_plugin")

    async def test_reload_without_admin_role_rejected(self, plugin):
        """The /reload command rejects users without admin role."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.roles = [MagicMock(id=999999)]  # Wrong role
        await plugin.reload_cmd(interaction, plugin_name="test_plugin")
        # Should respond with permission error, not call reload
        plugin.server.reload_plugin.assert_not_called()
