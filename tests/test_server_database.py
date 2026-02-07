"""Tests for database integration in server orchestrator."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.config import ServerConfig, LoggingConfig, RconConfig, DatabaseConfig
from squadpy.server import SquadPyServer


@pytest.fixture
def base_configs():
    server_config = ServerConfig(rcon=RconConfig(host="127.0.0.1", port=21114, password="test"))
    logging_config = LoggingConfig()
    return server_config, logging_config


@pytest.fixture
def db_config_enabled():
    return DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")


@pytest.fixture
def db_config_disabled():
    return DatabaseConfig(enabled=False)


class TestServerDatabaseInit:
    def test_server_accepts_db_config(self, base_configs, db_config_enabled):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        assert server._db_config is db_config_enabled

    def test_server_db_config_defaults_none(self, base_configs):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
        )
        assert server._db_config is None


class TestServerDatabaseLifecycle:
    async def test_db_initialized_when_enabled(self, base_configs, db_config_enabled):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        with patch.object(server, "_connect_rcon", new_callable=AsyncMock) as mock_rcon:
            mock_rcon.return_value = (False, "mocked")
            with patch.object(server, "_load_plugins", new_callable=AsyncMock):
                with patch.object(server, "_print_summary"):
                    with patch.object(server, "_setup_signals"):
                        task = asyncio.create_task(server.start())
                        await asyncio.sleep(0.1)
                        assert server._db is not None
                        await server.stop()
                        await task

    async def test_db_none_when_disabled(self, base_configs, db_config_disabled):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_disabled,
        )
        with patch.object(server, "_connect_rcon", new_callable=AsyncMock) as mock_rcon:
            mock_rcon.return_value = (False, "mocked")
            with patch.object(server, "_load_plugins", new_callable=AsyncMock):
                with patch.object(server, "_print_summary"):
                    with patch.object(server, "_setup_signals"):
                        task = asyncio.create_task(server.start())
                        await asyncio.sleep(0.1)
                        assert server._db is None
                        await server.stop()
                        await task

    async def test_db_shutdown_called_on_stop(self, base_configs, db_config_enabled):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        mock_db = AsyncMock()
        server._db = mock_db
        server._running = True
        await server.stop()
        mock_db.shutdown.assert_awaited_once()

    async def test_db_passed_to_plugins_in_services(self, base_configs, db_config_enabled):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        mock_db = MagicMock()
        server._db = mock_db
        services = server._build_services(rcon=None, log_parser=None)
        assert services["db"] is mock_db


class TestServerDatabaseSummary:
    def test_summary_shows_db_status(self, base_configs, db_config_enabled, capsys):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        server._print_summary(False, "mocked", False, "", False, "", True, "SQLite (data/squadpy.db)")
        captured = capsys.readouterr()
        assert "SQLite" in captured.out

    def test_summary_shows_not_configured(self, base_configs, capsys):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
        )
        server._print_summary(False, "mocked", False, "", False, "", False, "not configured")
        captured = capsys.readouterr()
        assert "not configured" in captured.out
