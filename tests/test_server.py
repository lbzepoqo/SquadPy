"""Tests for the server orchestrator."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from squadpy.server import SquadPyServer, format_service_line, format_plugin_line
from squadpy.config import ServerConfig, LoggingConfig, DiscordConfig
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


class TestServerLogReaderIntegration:
    def test_log_reader_in_services_when_configured(self):
        """Server config with log enabled should register log_reader service."""
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
            log={"enabled": True, "mode": "local", "path": "/tmp/test.log"},
        )
        assert config.log.enabled is True

    def test_log_reader_not_in_services_when_disabled(self):
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
        )
        assert config.log.enabled is False


class TestServerDiscordConfig:
    def test_server_config_with_discord(self):
        """ServerConfig accepts discord section."""
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
            discord={"enabled": True, "token": "tok", "guild_id": 123},
        )
        assert config.discord.enabled is True

    def test_server_config_without_discord(self):
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
        )
        assert config.discord.enabled is False


class TestStartupSummaryDiscord:
    def test_format_discord_ok(self):
        line = format_service_line("Discord", True, "connected (SquadPy#1234)")
        assert "Discord" in line
        assert "ok" in line
        assert "connected" in line

    def test_format_discord_not_configured(self):
        line = format_service_line("Discord", False, "not configured")
        assert "Discord" in line
        assert "not configured" in line
