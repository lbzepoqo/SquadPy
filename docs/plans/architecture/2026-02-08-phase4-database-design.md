# Phase 4 — Database & Persistence Design

## Overview

Add async database support so plugins can persist data using SQLAlchemy. SQLite
works out of the box; PostgreSQL and MySQL are supported but require the admin to
install the async driver. Plugins get a session factory — they define their own
models and write their own queries.

## Design Decisions

- **Session factory, not service API** — plugins get `self.db.session()` and write
  SQLAlchemy queries directly. No abstraction layer to fight.
- **Shared declarative base** — all plugins import `Base` from `squadpy.database`
  and extend it. `create_all()` runs once after all models are imported.
- **No migrations** — `create_all()` creates missing tables but never alters
  existing ones. Schema changes are handled manually (or delete the DB file).
  Alembic can be added later if demand appears.
- **Only aiosqlite as a required dep** — SQLite is the default and covers 90% of
  users. PostgreSQL/MySQL admins install `asyncpg`/`aiomysql` themselves.

## 1. Dependencies

New in `pyproject.toml`:
```toml
dependencies = [
    "pydantic>=2.0",
    "discord.py>=2.3",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
]
```

Optional (user-installed):
- `asyncpg` — for `driver = "postgresql"`
- `aiomysql` — for `driver = "mysql"`

## 2. Module Structure

```
squadpy/database/
    __init__.py      # Exports: Base, DatabaseManager
    models.py        # DeclarativeBase definition
    manager.py       # DatabaseManager class (engine, sessions, lifecycle)
```

## 3. Connection URL Mapping

| Config driver | Async dialect          | Required package           |
|---------------|------------------------|----------------------------|
| sqlite        | `sqlite+aiosqlite`     | aiosqlite (bundled dep)    |
| postgresql    | `postgresql+asyncpg`   | asyncpg (user-installed)   |
| mysql         | `mysql+aiomysql`       | aiomysql (user-installed)  |

For SQLite, the `path` config field is used (parent directories auto-created).
For PostgreSQL/MySQL, `host`, `port`, `username`, `password`, and `database` are
used. The existing `DatabaseConfig` model covers all fields — no config changes.

## 4. DatabaseManager API

```python
class DatabaseManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self, config: DatabaseConfig) -> None:
        """Build connection URL from config, create engine and session factory.

        For SQLite: creates parent directories for the db file.
        Engine uses pool_pre_ping=True for non-SQLite drivers.
        """

    def session(self) -> AsyncSession:
        """Return a new AsyncSession. Caller manages lifecycle:

            async with db.session() as session:
                session.add(record)
                await session.commit()

        No auto-commit — plugins explicitly commit.
        No auto-flush — prevents surprise queries.
        """

    async def create_tables(self) -> None:
        """Run Base.metadata.create_all() to create any missing tables.
        Called once after all plugin models have been imported.

        Uses run_sync:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        """

    async def shutdown(self) -> None:
        """Dispose engine and close all connections."""
```

**Key behaviors:**
- `session()` returns from `async_sessionmaker` which is itself a context manager
- SQLite gets `connect_args={"check_same_thread": False}`
- Non-SQLite engines get `pool_pre_ping=True` for connection health checks

## 5. Declarative Base

```python
# squadpy/database/models.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

Plugins extend this:
```python
from sqlalchemy.orm import Mapped, mapped_column
from squadpy.database import Base

class TKRecord(Base):
    __tablename__ = "tk_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    attacker: Mapped[str]
    victim: Mapped[str]
    weapon: Mapped[str]
    timestamp: Mapped[float]
```

## 6. Server Integration

### Startup Order

1. Load `DatabaseConfig` from `config/database.toml`
2. If enabled, create `DatabaseManager` and call `initialize(config)`
3. Load plugins (imports their model modules, registering tables on `Base`)
4. Call `db.create_tables()` — all plugin tables now exist
5. Pass `db` in services dict to plugins (replaces current `"db": None`)
6. Continue normal startup (periodic tasks, event bus, etc.)

### Shutdown Order

1. Cancel periodic tasks (existing)
2. Call `on_disable()` on each plugin — plugins flush state to DB (existing)
3. Call `db.shutdown()` — dispose engine, close connections (new)

### Entry Point

`__main__.py` loads `DatabaseConfig` from `config/database.toml` and passes it
to the server.

### Startup Summary

```
Database:     SQLite (data/squadpy.db)
Database:     PostgreSQL (myhost:5432/squad)
Database:     not configured
```

### Hot-Reload

When plugins are reloaded, the `db` reference stays the same — no reconnection.
`create_tables()` is called again after reload in case new plugins added models.

## 7. Plugin Access

- `self.db` is `DatabaseManager | None`
- Plugins with `requires = ["database"]` fail to load if database isn't configured
- Plugins without that requirement check `if self.db:` before using

### Persistence Patterns (from main design doc)

| Data type                | Strategy       | Max data loss on crash |
|--------------------------|----------------|------------------------|
| Critical (bans, tickets) | Write-through  | None                   |
| Accumulated (TK counts)  | Periodic flush | ~30 seconds            |
| Session-only (timers)    | In-memory only | All (by design)        |

```python
# Write-through (critical data)
@on_event("player_banned")
async def on_ban(self, event):
    async with self.db.session() as session:
        session.add(BanRecord(...))
        await session.commit()

# Periodic flush (accumulated data)
@periodic(seconds=30)
async def auto_save(self):
    if self.db:
        async with self.db.session() as session:
            # bulk save in-memory state
            await session.commit()

# Graceful shutdown flush
async def on_disable(self):
    if self.db:
        async with self.db.session() as session:
            # final flush
            await session.commit()
```

## 8. Error Handling

- Invalid driver config → log warning, server continues with `db = None`
- Missing async driver package (e.g. `asyncpg` not installed) → clear error at
  startup, server continues with `db = None`
- Session errors in plugins → handled by existing plugin error isolation
- Database is optional — server runs fine without it

## 9. Testing Strategy

All tests use in-memory SQLite (`sqlite+aiosqlite://`) — no file cleanup needed.

1. **URL building** — connection URL construction from `DatabaseConfig` for all
   three drivers
2. **DatabaseManager lifecycle** — `initialize()`, `create_tables()`, `session()`,
   `shutdown()` with real in-memory SQLite
3. **Session behavior** — no auto-commit, context manager cleanup, concurrent
   sessions
4. **Model definition** — define test model on `Base`, create tables, verify
   insert/query round-trip
5. **Server integration** — orchestrator initializes DB when enabled, passes to
   plugins, calls `create_tables()` after loading, calls `shutdown()` on teardown.
   Disabled config results in `db = None`
6. **Error handling** — invalid config logs warning, `requires = ["database"]`
   plugins fail to load when DB disabled
