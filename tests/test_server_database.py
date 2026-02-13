"""Tests for database integration in server orchestrator."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.config import ServerConfig, LoggingConfig, RconConfig, DatabaseConfig
from squadpy.server import SquadPyServer
from squadpy.plugin_loader import PluginLoader, PluginStatus, LoadedPlugin


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

    async def test_tables_created_before_plugins_loaded(self, base_configs, db_config_enabled):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        mock_db = AsyncMock()
        mock_db.create_tables = AsyncMock()
        mock_db.shutdown = AsyncMock()

        async def fake_connect_database():
            server._db = mock_db
            return True, "mocked-db"

        async def fake_load_plugins(_services):
            mock_db.create_tables.assert_awaited_once()
            server._loaded_plugins = []

        with patch.object(server, "_connect_rcon", new=AsyncMock(return_value=(False, "mocked"))):
            with patch.object(server, "_start_log_reader", new=AsyncMock(return_value=(False, "mocked"))):
                with patch.object(server, "_connect_discord", new=AsyncMock(return_value=(False, "mocked"))):
                    with patch.object(server, "_connect_database", new=AsyncMock(side_effect=fake_connect_database)):
                        with patch.object(server, "_load_plugins", new=AsyncMock(side_effect=fake_load_plugins)):
                            with patch.object(server, "_print_summary"):
                                with patch.object(server, "_setup_signals"):
                                    task = asyncio.create_task(server.start())
                                    await asyncio.sleep(0.1)
                                    await server.stop()
                                    await task

        mock_db.create_tables.assert_awaited_once()

    async def test_reload_creates_tables_before_plugin_enable(self, base_configs, db_config_enabled):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        mock_db = AsyncMock()
        mock_db.create_tables = AsyncMock()
        server._db = mock_db

        plugin_instance = AsyncMock()
        plugin_instance.on_disable = AsyncMock()
        server._loaded_plugins = [
            LoadedPlugin(
                name="DB Plugin",
                dir_name="db_plugin",
                status=PluginStatus.ENABLED,
                instance=plugin_instance,
            )
        ]

        with patch("squadpy.server.PluginLoader") as mock_loader_cls:
            loader = MagicMock()
            loader.discover.return_value = [MagicMock(dir_name="db_plugin")]

            async def fake_load_one(_info, _services):
                mock_db.create_tables.assert_awaited_once()
                return LoadedPlugin(
                    name="DB Plugin",
                    dir_name="db_plugin",
                    status=PluginStatus.FAILED,
                    error="reload failed",
                )

            loader._load_one = AsyncMock(side_effect=fake_load_one)
            mock_loader_cls.return_value = loader

            success, error = await server.reload_plugin("db_plugin")

        assert success is False
        assert error == "reload failed"
        mock_db.create_tables.assert_awaited_once()


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


class TestDatabaseRequirement:
    async def test_plugin_requiring_db_fails_when_disabled(self, tmp_path):
        """A plugin with requires=['db'] fails to load when db is None."""
        plugin_dir = tmp_path / "plugins" / "db_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text('''
from squadpy.plugin import Plugin

class DbPlugin(Plugin):
    name = "DB Plugin"
    requires = ["db"]
''')
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        loader = PluginLoader(plugins_dir=tmp_path / "plugins", config_dir=config_dir)
        services = {"rcon": None, "discord": None, "db": None, "server": None}
        results = await loader.load_all(services)

        assert len(results) == 1
        assert results[0].status == PluginStatus.FAILED
        assert "db" in results[0].error.lower()

    async def test_plugin_requiring_db_succeeds_when_enabled(self, tmp_path):
        """A plugin with requires=['db'] loads when db is provided."""
        plugin_dir = tmp_path / "plugins" / "db_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text('''
from squadpy.plugin import Plugin

class DbPlugin(Plugin):
    name = "DB Plugin"
    requires = ["db"]
''')
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        from unittest.mock import MagicMock
        mock_db = MagicMock()
        loader = PluginLoader(plugins_dir=tmp_path / "plugins", config_dir=config_dir)
        services = {"rcon": None, "discord": None, "db": mock_db, "server": None}
        results = await loader.load_all(services)

        assert len(results) == 1
        assert results[0].status == PluginStatus.ENABLED
        assert results[0].instance is not None
        assert results[0].instance.db is mock_db
