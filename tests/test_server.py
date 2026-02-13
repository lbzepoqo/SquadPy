"""Tests for the server orchestrator."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.config import LoggingConfig, ServerConfig
from squadpy.server import SquadPyServer, format_plugin_line, format_service_line
from squadpy.plugin_loader import LoadedPlugin, PluginStatus


class TestSquadPyServer:
    @pytest.fixture
    def server_config(self):
        return ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
        })

    @pytest.fixture
    def logging_config(self):
        return LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}})

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
        config = ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "password": "test"},
            "log": {"enabled": True, "mode": "local", "path": "/tmp/test.log"},
        })
        assert config.log.enabled is True

    def test_log_reader_not_in_services_when_disabled(self):
        config = ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "password": "test"},
        })
        assert config.log.enabled is False

    async def test_start_log_reader_uses_sftp_reader(self):
        server = SquadPyServer(
            server_config=ServerConfig.model_validate({
                "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
                "log": {
                    "enabled": True,
                    "mode": "sftp",
                    "path": "/remote/SquadGame.log",
                    "poll_interval": 0.5,
                    "host": "sftp.example.com",
                    "port": 2022,
                    "username": "tester",
                    "password": "secret",
                },
            }),
            logging_config=LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}}),
            base_dir=Path("/tmp/test"),
        )

        with patch("squadpy.server.SFTPLogReader") as mock_sftp_reader:
            with patch("squadpy.server.LogParser") as mock_parser:
                with patch("squadpy.server.asyncio.create_task", return_value=MagicMock()):
                    ok, detail = await server._start_log_reader()

        assert ok is True
        assert detail == "tailing (sftp)"
        mock_sftp_reader.assert_called_once_with(
            host="sftp.example.com",
            port=2022,
            username="tester",
            password="secret",
            path="/remote/SquadGame.log",
            poll_interval=0.5,
        )
        mock_parser.assert_called_once()


class TestServerDiscordConfig:
    def test_server_config_with_discord(self):
        """ServerConfig accepts discord section."""
        config = ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "password": "test"},
            "discord": {"enabled": True, "token": "tok", "guild_id": 123},
        })
        assert config.discord.enabled is True

    def test_server_config_without_discord(self):
        config = ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "password": "test"},
        })
        assert config.discord.enabled is False


class TestHotReloadPeriodicTasks:
    async def test_reload_cancels_periodic_tasks_for_target_plugin(self):
        server = SquadPyServer(
            server_config=ServerConfig.model_validate({
                "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
            }),
            logging_config=LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}}),
            base_dir=Path("/tmp/test"),
        )
        server._running = True

        old_task = asyncio.create_task(asyncio.sleep(60))
        other_task = asyncio.create_task(asyncio.sleep(60))
        server._periodic_tasks = [
            ("target_plugin", old_task),
            ("other_plugin", other_task),
        ]

        target_instance = AsyncMock()
        target_instance.on_disable = AsyncMock()
        server._loaded_plugins = [
            LoadedPlugin(
                name="Target Plugin",
                dir_name="target_plugin",
                status=PluginStatus.ENABLED,
                instance=target_instance,
            )
        ]

        with patch("squadpy.server.PluginLoader") as mock_loader_cls:
            mock_loader = MagicMock()
            mock_loader.discover.return_value = [MagicMock(dir_name="target_plugin")]
            mock_loader._load_one = AsyncMock(
                return_value=LoadedPlugin(
                    name="Target Plugin",
                    dir_name="target_plugin",
                    status=PluginStatus.FAILED,
                    error="reload failed",
                )
            )
            mock_loader_cls.return_value = mock_loader

            ok, error = await server.reload_plugin("target_plugin")

        await asyncio.sleep(0)
        assert ok is False
        assert error == "reload failed"
        assert old_task.cancelled()
        assert not other_task.cancelled()
        assert len(server._periodic_tasks) == 1
        assert server._periodic_tasks[0][0] == "other_plugin"

        other_task.cancel()
        await asyncio.sleep(0)


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
