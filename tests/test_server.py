"""Tests for the server orchestrator."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from squadpy.server import SquadPyServer, format_service_line, format_plugin_line
from squadpy.config import ServerConfig, LoggingConfig
from squadpy.plugin_loader import LoadedPlugin, PluginStatus


class TestSquadPyServer:
    @pytest.fixture
    def server_config(self):
        return ServerConfig(
            rcon={"host": "127.0.0.1", "port": 21114, "password": "test"}
        )

    @pytest.fixture
    def logging_config(self):
        return LoggingConfig(level="INFO", file={"enabled": False})

    @pytest.fixture
    def server(self, server_config, logging_config):
        return SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp/test"),
        )

    def test_initial_state(self, server):
        assert not server.running

    def test_version(self, server):
        assert server.version == "0.1.0"


class TestStartupSummary:
    def test_format_service_status_ok(self):
        line = format_service_line("RCON", True, "connected (127.0.0.1:21114)")
        assert "RCON" in line
        assert "connected" in line

    def test_format_service_status_fail(self):
        line = format_service_line("Discord", False, "not configured")
        assert "Discord" in line
        assert "not configured" in line

    def test_format_plugin_status_enabled(self):
        plugin = LoadedPlugin(
            name="TKWarn", dir_name="tk_warn",
            status=PluginStatus.ENABLED,
        )
        line = format_plugin_line(plugin)
        assert "TKWarn" in line
        assert "enabled" in line.lower() or "ok" in line.lower()

    def test_format_plugin_status_failed(self):
        plugin = LoadedPlugin(
            name="BadPlugin", dir_name="bad_plugin",
            status=PluginStatus.FAILED,
            error="missing channel_id",
        )
        line = format_plugin_line(plugin)
        assert "BadPlugin" in line
        assert "missing channel_id" in line

    def test_format_plugin_status_disabled(self):
        plugin = LoadedPlugin(
            name="SeedReward", dir_name="seed_reward",
            status=PluginStatus.DISABLED,
        )
        line = format_plugin_line(plugin)
        assert "SeedReward" in line
        assert "disabled" in line.lower()
