# Phase 4 — Database & Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add async database support via SQLAlchemy so plugins can persist data. SQLite works out of the box; PostgreSQL/MySQL are user-installed extras.

**Architecture:** `DatabaseManager` wraps an async SQLAlchemy engine and session factory. Plugins define models extending a shared `Base` and get `self.db.session()` for queries. Server orchestrator handles DB lifecycle (init → create_tables → shutdown).

**Tech Stack:** SQLAlchemy 2.0+ (async), aiosqlite, Pydantic (config validation)

**Design doc:** `docs/plans/architecture/2026-02-08-phase4-database-design.md`

---

### Task 1: Add SQLAlchemy Dependencies

**Files:**
- Modify: `pyproject.toml:6-9`

**Step 1: Update dependencies**

In `pyproject.toml`, change the `dependencies` list to:
```toml
dependencies = [
    "pydantic>=2.0",
    "discord.py>=2.3",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
]
```

**Step 2: Install dependencies**

Run: `pip install -e ".[dev]"`
Expected: Successful install, sqlalchemy and aiosqlite now available.

**Step 3: Verify import**

Run: `python -c "import sqlalchemy; import aiosqlite; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add sqlalchemy and aiosqlite dependencies for Phase 4"
```

---

### Task 2: Create DeclarativeBase

**Files:**
- Create: `squadpy/database/models.py`
- Test: `tests/test_database.py`

**Step 1: Write the failing test**

Create `tests/test_database.py`:
```python
"""Tests for database module."""

from sqlalchemy.orm import DeclarativeBase

from squadpy.database.models import Base


class TestBase:
    def test_base_is_declarative(self):
        assert issubclass(Base, DeclarativeBase)

    def test_base_has_metadata(self):
        assert hasattr(Base, "metadata")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::TestBase -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'squadpy.database.models'`

**Step 3: Write the implementation**

Create `squadpy/database/models.py`:
```python
"""Shared declarative base for all plugin models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_database.py::TestBase -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add squadpy/database/models.py tests/test_database.py
git commit -m "feat: add shared DeclarativeBase for plugin models"
```

---

### Task 3: Create DatabaseManager — URL Building

**Files:**
- Create: `squadpy/database/manager.py`
- Modify: `tests/test_database.py`

The `DatabaseManager` needs a method to build connection URLs from `DatabaseConfig`. This task tests URL building in isolation before adding engine/session logic.

**Step 1: Write failing tests**

Append to `tests/test_database.py`:
```python
import pytest

from squadpy.config import DatabaseConfig
from squadpy.database.manager import DatabaseManager


class TestURLBuilding:
    def test_sqlite_url(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path="data/test.db")
        mgr = DatabaseManager()
        url = mgr._build_url(config)
        assert url == "sqlite+aiosqlite:///data/test.db"

    def test_postgresql_url(self):
        config = DatabaseConfig(
            enabled=True, driver="postgresql",
            host="localhost", port=5432, username="user", password="pass", database="squad",
        )
        mgr = DatabaseManager()
        url = mgr._build_url(config)
        assert url == "postgresql+asyncpg://user:pass@localhost:5432/squad"

    def test_mysql_url(self):
        config = DatabaseConfig(
            enabled=True, driver="mysql",
            host="db.example.com", port=3306, username="admin", password="secret", database="mydb",
        )
        mgr = DatabaseManager()
        url = mgr._build_url(config)
        assert url == "mysql+aiomysql://admin:secret@db.example.com:3306/mydb"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_database.py::TestURLBuilding -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'squadpy.database.manager'`

**Step 3: Write the implementation**

Create `squadpy/database/manager.py`:
```python
"""Database manager — engine, sessions, lifecycle."""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from squadpy.config import DatabaseConfig
from squadpy.database.models import Base

logger = logging.getLogger("squadpy.database")

_DRIVER_MAP = {
    "sqlite": "sqlite+aiosqlite",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
}


class DatabaseManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def _build_url(self, config: DatabaseConfig) -> str:
        dialect = _DRIVER_MAP[config.driver]
        if config.driver == "sqlite":
            return f"{dialect}:///{config.path}"
        return f"{dialect}://{config.username}:{config.password}@{config.host}:{config.port}/{config.database}"
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py::TestURLBuilding -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add squadpy/database/manager.py tests/test_database.py
git commit -m "feat: add DatabaseManager with connection URL building"
```

---

### Task 4: DatabaseManager — Initialize, Session, Shutdown

**Files:**
- Modify: `squadpy/database/manager.py`
- Modify: `tests/test_database.py`

Tests use in-memory SQLite (`sqlite+aiosqlite://`) — no file cleanup.

**Step 1: Write failing tests**

Append to `tests/test_database.py`:
```python
from sqlalchemy.orm import Mapped, mapped_column


# Test model — defined at module level so Base.metadata picks it up
class _TestRecord(Base):
    __tablename__ = "test_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str]


class TestDatabaseLifecycle:
    async def test_initialize_creates_engine(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        assert mgr._engine is not None
        assert mgr._session_factory is not None
        await mgr.shutdown()

    async def test_create_tables(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.create_tables()
        # Verify table exists by inserting and querying
        async with mgr.session() as session:
            session.add(_TestRecord(value="hello"))
            await session.commit()
        async with mgr.session() as session:
            from sqlalchemy import select
            result = await session.execute(select(_TestRecord))
            rows = result.scalars().all()
            assert len(rows) == 1
            assert rows[0].value == "hello"
        await mgr.shutdown()

    async def test_session_no_auto_commit(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.create_tables()
        # Add without committing
        async with mgr.session() as session:
            session.add(_TestRecord(value="uncommitted"))
            # no commit
        # Should not persist
        async with mgr.session() as session:
            from sqlalchemy import select
            result = await session.execute(select(_TestRecord))
            rows = result.scalars().all()
            assert len(rows) == 0
        await mgr.shutdown()

    async def test_shutdown_disposes_engine(self):
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.shutdown()
        assert mgr._engine is None
        assert mgr._session_factory is None

    async def test_session_raises_before_initialize(self):
        mgr = DatabaseManager()
        with pytest.raises(RuntimeError, match="not initialized"):
            mgr.session()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_database.py::TestDatabaseLifecycle -v`
Expected: FAIL — `DatabaseManager` has no `initialize`, `session`, or `shutdown` methods

**Step 3: Add initialize, session, create_tables, shutdown**

In `squadpy/database/manager.py`, add these methods to `DatabaseManager`:
```python
    async def initialize(self, config: DatabaseConfig) -> None:
        url = self._build_url(config)
        connect_args = {}
        kwargs = {}
        if config.driver == "sqlite":
            connect_args["check_same_thread"] = False
            # For in-memory SQLite, share the same connection across the session
            if config.path == ":memory:" or url.endswith(":///"):
                from sqlalchemy.pool import StaticPool
                kwargs["poolclass"] = StaticPool
        else:
            kwargs["pool_pre_ping"] = True

        if config.driver == "sqlite" and config.path != ":memory:":
            db_path = Path(config.path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_async_engine(url, connect_args=connect_args, **kwargs)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        logger.info("Database initialized: %s", url.split("://")[0])

    def session(self) -> AsyncSession:
        if self._session_factory is None:
            raise RuntimeError("Database not initialized")
        return self._session_factory()

    async def create_tables(self) -> None:
        if self._engine is None:
            raise RuntimeError("Database not initialized")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    async def shutdown(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database shut down")
```

Note the `StaticPool` for in-memory SQLite — without it, each session would get a separate in-memory database. This is only needed for `:memory:` databases (tests). For file-based SQLite this isn't needed.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: All tests pass (TestBase: 2, TestURLBuilding: 3, TestDatabaseLifecycle: 5)

**Step 5: Commit**

```bash
git add squadpy/database/manager.py tests/test_database.py
git commit -m "feat: add DatabaseManager lifecycle (initialize, session, create_tables, shutdown)"
```

---

### Task 5: Update `__init__.py` Exports

**Files:**
- Modify: `squadpy/database/__init__.py`

**Step 1: Write failing test**

Append to `tests/test_database.py`:
```python
class TestExports:
    def test_base_importable_from_package(self):
        from squadpy.database import Base as B
        assert B is Base

    def test_manager_importable_from_package(self):
        from squadpy.database import DatabaseManager as DM
        assert DM is DatabaseManager
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::TestExports -v`
Expected: FAIL — `ImportError: cannot import name 'Base' from 'squadpy.database'`

**Step 3: Write the implementation**

Update `squadpy/database/__init__.py`:
```python
"""Database module — exports Base and DatabaseManager."""

from squadpy.database.models import Base
from squadpy.database.manager import DatabaseManager

__all__ = ["Base", "DatabaseManager"]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py::TestExports -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add squadpy/database/__init__.py tests/test_database.py
git commit -m "feat: export Base and DatabaseManager from database package"
```

---

### Task 6: Server Integration — Entry Point & Orchestrator

**Files:**
- Modify: `squadpy/__main__.py:7,14-18` — load `DatabaseConfig`
- Modify: `squadpy/server.py:8,36-43,63-155,202-211,223-251,253-308` — DB lifecycle
- Test: `tests/test_server_database.py`

This is the largest task. The server needs to:
1. Accept `DatabaseConfig` (from `__main__.py`)
2. Initialize `DatabaseManager` if enabled
3. Pass `db` to plugins via services dict
4. Call `create_tables()` after plugin loading
5. Show DB status in startup summary
6. Call `db.shutdown()` during stop
7. Re-run `create_tables()` on hot-reload

**Step 1: Write failing tests**

Create `tests/test_server_database.py`:
```python
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
        # Mock RCON so start() doesn't fail on network
        with patch.object(server, "_connect_rcon", new_callable=AsyncMock) as mock_rcon:
            mock_rcon.return_value = (False, "mocked")
            # Mock plugin loading
            with patch.object(server, "_load_plugins", new_callable=AsyncMock):
                with patch.object(server, "_print_summary"):
                    with patch.object(server, "_setup_signals"):
                        # Start in background, then stop immediately
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
        # Manually set up a mock DB
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
    def test_summary_shows_sqlite(self, base_configs, db_config_enabled, capsys):
        server_config, logging_config = base_configs
        server = SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp"),
            db_config=db_config_enabled,
        )
        server._db = MagicMock()
        server._db_config = db_config_enabled
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server_database.py -v`
Expected: FAIL — `SquadPyServer.__init__` doesn't accept `db_config`

**Step 3: Modify `squadpy/server.py`**

Changes needed:

3a. Add import at top:
```python
from squadpy.config import ServerConfig, LoggingConfig, DatabaseConfig
from squadpy.database import DatabaseManager
```

3b. Update `__init__` to accept `db_config`:
```python
    def __init__(
        self,
        server_config: ServerConfig,
        logging_config: LoggingConfig,
        base_dir: Path,
        db_config: DatabaseConfig | None = None,
    ):
        self._server_config = server_config
        self._logging_config = logging_config
        self._base_dir = base_dir
        self._db_config = db_config
        self._running = False
        self._event_bus = EventBus()
        self._rcon: RconClient | None = None
        self._loaded_plugins: list[LoadedPlugin] = []
        self._periodic_tasks: list[asyncio.Task] = []
        self._log_parser: LogParser | None = None
        self._log_parser_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._discord: DiscordConnector | None = None
        self._db: DatabaseManager | None = None
```

3c. Extract helper methods to make `start()` testable. Add these methods:
```python
    async def _connect_rcon(self) -> tuple[bool, str]:
        try:
            self._rcon = RconClient(
                host=self._server_config.rcon.host,
                port=self._server_config.rcon.port,
                password=self._server_config.rcon.password,
            )
            await self._rcon.connect()
            self._rcon.on_chat = self._handle_chat
            detail = f"connected ({self._server_config.rcon.host}:{self._server_config.rcon.port})"
            return True, detail
        except Exception as e:
            logger.error("RCON connection failed: %s", e)
            return False, str(e)

    async def _connect_database(self) -> tuple[bool, str]:
        if not self._db_config or not self._db_config.enabled:
            return False, "not configured"
        try:
            self._db = DatabaseManager()
            await self._db.initialize(self._db_config)
            driver_name = self._db_config.driver.upper()
            if self._db_config.driver == "sqlite":
                detail = f"SQLite ({self._db_config.path})"
            elif self._db_config.driver == "postgresql":
                detail = f"PostgreSQL ({self._db_config.host}:{self._db_config.port}/{self._db_config.database})"
            else:
                detail = f"MySQL ({self._db_config.host}:{self._db_config.port}/{self._db_config.database})"
            return True, detail
        except Exception as e:
            logger.error("Database initialization failed: %s", e)
            self._db = None
            return False, str(e)

    def _build_services(self, rcon, log_parser) -> dict:
        return {
            "rcon": rcon,
            "log_reader": log_parser,
            "discord": self._discord,
            "db": self._db,
            "server": self,
        }

    async def _load_plugins(self, services: dict) -> None:
        plugin_loader = PluginLoader(
            plugins_dir=self._base_dir / "plugins",
            config_dir=self._base_dir / "config" / "plugins",
        )
        self._loaded_plugins = await plugin_loader.load_all(services)

    def _setup_signals(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
```

3d. Rewrite `start()` to use the helpers and add DB lifecycle:
```python
    async def start(self) -> None:
        self._running = True

        log_dir = self._base_dir / self._logging_config.file.path
        setup_logging(self._logging_config, log_dir if self._logging_config.file.enabled else None)

        # Connect RCON
        rcon_ok, rcon_detail = await self._connect_rcon()

        # Start log reader
        log_ok, log_detail = await self._start_log_reader()

        # Connect Discord
        discord_ok, discord_detail = await self._connect_discord()

        # Initialize database
        db_ok, db_detail = await self._connect_database()

        # Load plugins
        services = self._build_services(
            rcon=self._rcon if rcon_ok else None,
            log_parser=self._log_parser if log_ok else None,
        )
        await self._load_plugins(services)

        # Create DB tables after plugins loaded (so their models are registered)
        if self._db:
            try:
                await self._db.create_tables()
            except Exception as e:
                logger.error("Failed to create database tables: %s", e)

        for lp in self._loaded_plugins:
            if lp.status == PluginStatus.ENABLED and lp.instance:
                self._register_plugin_events(lp)
                self._start_periodic_tasks(lp)

        if self._discord:
            for lp in self._loaded_plugins:
                if lp.status == PluginStatus.ENABLED and lp.instance:
                    self._register_plugin_discord(lp)
            try:
                await self._discord.sync_commands()
            except Exception as e:
                logger.error("Failed to sync Discord commands: %s", e)

        self._print_summary(rcon_ok, rcon_detail, log_ok, log_detail, discord_ok, discord_detail, db_ok, db_detail)

        self._setup_signals()
        await self._shutdown_event.wait()
```

Also extract `_start_log_reader` and `_connect_discord` from the inline code:
```python
    async def _start_log_reader(self) -> tuple[bool, str]:
        if not self._server_config.log.enabled:
            return False, "not configured"
        try:
            if self._server_config.log.mode == "local":
                reader = LocalLogReader(
                    self._server_config.log.path,
                    poll_interval=self._server_config.log.poll_interval,
                )
            else:
                raise NotImplementedError("SFTP log reader not yet implemented")
            self._log_parser = LogParser(reader=reader, event_bus=self._event_bus)
            self._log_parser_task = asyncio.create_task(self._log_parser.run())
            return True, f"tailing ({self._server_config.log.mode})"
        except Exception as e:
            logger.error("Log reader failed: %s", e)
            return False, str(e)

    async def _connect_discord(self) -> tuple[bool, str]:
        if not self._server_config.discord.enabled:
            return False, "not configured"
        try:
            self._discord = DiscordConnector(self._server_config.discord)
            await self._discord.start(self._server_config.discord.token)
            await asyncio.wait_for(self._discord.wait_until_ready(), timeout=30.0)
            bot_name = str(self._discord.bot.user) if self._discord.bot.user else "unknown"
            return True, f"connected ({bot_name})"
        except Exception as e:
            logger.error("Discord connection failed: %s", e)
            self._discord = None
            return False, str(e)
```

3e. Update `_print_summary` to accept DB params:
```python
    def _print_summary(self, rcon_ok, rcon_detail, log_ok=False, log_detail="", discord_ok=False, discord_detail="", db_ok=False, db_detail="") -> None:
        lines = [
            "",
            f"  SquadPy v{self.version}",
            "",
            "  Core Services:",
            format_service_line("RCON", rcon_ok, rcon_detail),
            format_service_line("Log Reader", log_ok, log_detail),
            format_service_line("Discord", discord_ok, discord_detail),
            format_service_line("Database", db_ok, db_detail),
            "",
        ]
        if self._loaded_plugins:
            lines.append("  Plugins:")
            for lp in self._loaded_plugins:
                lines.append(format_plugin_line(lp))
            lines.append("")
        print("\n".join(lines))
```

3f. Update `stop()` — add DB shutdown between Discord close and RCON close:
```python
    async def stop(self) -> None:
        if not self._running:
            return
        logger.info("Shutting down...")
        self._running = False

        if self._log_parser_task:
            self._log_parser_task.cancel()

        for task in self._periodic_tasks:
            task.cancel()

        for lp in self._loaded_plugins:
            if lp.status == PluginStatus.ENABLED and lp.instance:
                try:
                    await asyncio.wait_for(lp.instance.on_disable(), timeout=5.0)
                except Exception:
                    logger.exception("Error disabling plugin %s", lp.name)

        if self._discord:
            await self._discord.close()

        if self._db:
            await self._db.shutdown()

        if self._rcon:
            await self._rcon.close()

        self._event_bus.clear()
        self._shutdown_event.set()
        logger.info("Shutdown complete")
```

3g. Update `reload_plugin()` — pass `self._db` in services and re-run `create_tables()`:
```python
    async def reload_plugin(self, plugin_name: str) -> tuple[bool, str]:
        target = None
        for lp in self._loaded_plugins:
            if lp.dir_name == plugin_name or lp.name == plugin_name:
                target = lp
                break

        if target is None:
            return False, f"Plugin '{plugin_name}' not found"

        if target.instance:
            try:
                await target.instance.on_disable()
            except Exception:
                logger.exception("Error disabling %s during reload", target.name)

            for event_name, method_name in target.event_handlers:
                handler = getattr(target.instance, method_name)
                self._event_bus.unsubscribe(event_name, handler)

            if self._discord:
                self._discord.unregister_plugin(target.dir_name)

        services = self._build_services(rcon=self._rcon, log_parser=self._log_parser)
        loader = PluginLoader(
            plugins_dir=self._base_dir / "plugins",
            config_dir=self._base_dir / "config" / "plugins",
        )
        discovered = loader.discover()
        info = next((d for d in discovered if d.dir_name == target.dir_name), None)
        if info is None:
            return False, "Plugin directory no longer exists"

        new_loaded = await loader._load_one(info, services)

        # Re-run create_tables in case reloaded plugin added new models
        if self._db:
            try:
                await self._db.create_tables()
            except Exception:
                logger.exception("Failed to create tables after reload")

        idx = self._loaded_plugins.index(target)
        self._loaded_plugins[idx] = new_loaded

        if new_loaded.status == PluginStatus.ENABLED and new_loaded.instance:
            self._register_plugin_events(new_loaded)
            self._start_periodic_tasks(new_loaded)
            if self._discord:
                self._register_plugin_discord(new_loaded)
                try:
                    await self._discord.sync_commands()
                except Exception:
                    logger.exception("Failed to sync commands after reload")
            return True, ""

        return False, new_loaded.error
```

**Step 4: Modify `squadpy/__main__.py`**

Update to load `DatabaseConfig` and pass it to the server:
```python
"""SquadPy entry point: python -m squadpy"""

import asyncio
import sys
from pathlib import Path

from squadpy.config import ServerConfig, LoggingConfig, DatabaseConfig, load_config
from squadpy.server import SquadPyServer


def main():
    base_dir = Path.cwd()
    config_dir = base_dir / "config"

    # Load configs
    try:
        server_config = load_config(ServerConfig, config_dir / "server.toml")
    except Exception as e:
        print(f"Error loading server.toml: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        logging_config = load_config(LoggingConfig, config_dir / "logging.toml")
    except FileNotFoundError:
        logging_config = LoggingConfig()
    except Exception as e:
        print(f"Error loading logging.toml: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        db_config = load_config(DatabaseConfig, config_dir / "database.toml")
    except FileNotFoundError:
        db_config = None
    except Exception as e:
        print(f"Error loading database.toml: {e}", file=sys.stderr)
        sys.exit(1)

    server = SquadPyServer(
        server_config=server_config,
        logging_config=logging_config,
        base_dir=base_dir,
        db_config=db_config,
    )

    asyncio.run(server.start())


if __name__ == "__main__":
    main()
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_server_database.py -v`
Expected: All tests pass

Then run all tests to make sure nothing broke:
Run: `pytest tests/ -v`
Expected: All existing tests pass (194 + new tests)

**Step 6: Commit**

```bash
git add squadpy/server.py squadpy/__main__.py tests/test_server_database.py
git commit -m "feat: integrate database lifecycle into server orchestrator"
```

---

### Task 7: Error Handling — Invalid Config & Missing Requirements

**Files:**
- Modify: `tests/test_database.py`

**Step 1: Write failing tests**

Append to `tests/test_database.py`:
```python
class TestErrorHandling:
    async def test_invalid_driver_handled(self):
        """DatabaseManager handles initialization errors gracefully."""
        mgr = DatabaseManager()
        # A config with sqlite driver but missing aiosqlite would fail at connect time.
        # We can test the URL building for all valid drivers.
        for driver in ("sqlite", "postgresql", "mysql"):
            config = DatabaseConfig(enabled=True, driver=driver, path="test.db",
                                     host="h", port=1, username="u", password="p", database="d")
            url = mgr._build_url(config)
            assert driver in url or "aiosqlite" in url or "asyncpg" in url or "aiomysql" in url

    async def test_create_tables_before_init_raises(self):
        mgr = DatabaseManager()
        with pytest.raises(RuntimeError, match="not initialized"):
            await mgr.create_tables()
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_database.py::TestErrorHandling -v`
Expected: 2 passed (these test existing error paths)

**Step 3: Commit**

```bash
git add tests/test_database.py
git commit -m "test: add database error handling tests"
```

---

### Task 8: Requires Database — Plugin Requirement Check

**Files:**
- Modify: `tests/test_server_database.py`

This verifies the existing `requires` mechanism works with `"database"` → `"db"` service key.

**Step 1: Write the test**

Append to `tests/test_server_database.py`:
```python
from squadpy.plugin import Plugin
from squadpy.plugin_loader import PluginLoader, PluginStatus


class TestDatabaseRequirement:
    async def test_plugin_requiring_db_fails_when_disabled(self, tmp_path):
        """A plugin with requires=['db'] fails to load when db is None."""
        # Create a plugin that requires db
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
        assert results[0].instance.db is mock_db
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_server_database.py::TestDatabaseRequirement -v`
Expected: 2 passed

**Step 3: Commit**

```bash
git add tests/test_server_database.py
git commit -m "test: verify plugin requires=['db'] works with database service"
```

---

### Task 9: Full Integration Test — End-to-End Round-Trip

**Files:**
- Modify: `tests/test_database.py`

**Step 1: Write the test**

Append to `tests/test_database.py`:
```python
class TestEndToEnd:
    async def test_full_round_trip(self):
        """Initialize DB, create tables, insert, query, shutdown."""
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.create_tables()

        # Insert
        async with mgr.session() as session:
            session.add(_TestRecord(value="round_trip"))
            await session.commit()

        # Query
        async with mgr.session() as session:
            from sqlalchemy import select
            result = await session.execute(select(_TestRecord).where(_TestRecord.value == "round_trip"))
            record = result.scalar_one()
            assert record.value == "round_trip"
            assert record.id is not None

        # Shutdown
        await mgr.shutdown()
        assert mgr._engine is None

    async def test_multiple_sessions_isolated(self):
        """Two sessions don't see each other's uncommitted data."""
        config = DatabaseConfig(enabled=True, driver="sqlite", path=":memory:")
        mgr = DatabaseManager()
        await mgr.initialize(config)
        await mgr.create_tables()

        async with mgr.session() as s1:
            s1.add(_TestRecord(value="s1_data"))
            # Don't commit yet — s2 should not see this
            async with mgr.session() as s2:
                from sqlalchemy import select
                result = await s2.execute(select(_TestRecord))
                assert len(result.scalars().all()) == 0

        await mgr.shutdown()
```

**Step 2: Run tests**

Run: `pytest tests/test_database.py::TestEndToEnd -v`
Expected: 2 passed

**Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (194 existing + ~20 new = ~214 total)

**Step 4: Commit**

```bash
git add tests/test_database.py
git commit -m "test: add end-to-end database integration tests"
```

---

### Task 10: Final Verification & Cleanup

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 2: Verify imports work cleanly**

Run: `python -c "from squadpy.database import Base, DatabaseManager; print('ok')"`
Expected: `ok`

**Step 3: Verify entry point loads db config gracefully**

Run: `cd /tmp && python -c "from squadpy.config import DatabaseConfig, load_config; print(DatabaseConfig())"`
Expected: Prints default `DatabaseConfig` with `enabled=False`

**Step 4: Final commit if any cleanup needed, then update MEMORY.md**

Update the Phase 4 status in memory to mark it as complete with test count.
