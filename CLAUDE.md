# SquadPy

Python-based Squad game server management framework. Inspired by SquadJS/SquadTS.

## Quick Reference

| What | Where |
|------|-------|
| Design doc | `docs/plans/2026-02-08-squadpy-design.md` |
| Run | `python -m squadpy` |
| Test | `pytest tests/ -v` |
| Venv | `.venv/` — activate: `. .venv/bin/activate` |
| Python | 3.12+ required |
| Deps | `pydantic`, `pytest`, `pytest-asyncio` |

## Architecture

```
Log Reader (local/SFTP) → Log Parser (regex + state) → Event Bus → Plugins
                                                          ↑
RCON Client (async, Squad-quirks-aware) ──────────────────┘
```

Core services: RCON (required), Log Reader, Discord, Database (all optional).
Plugins declare `requires = ["rcon", "discord", ...]` — fail at load if missing.

## Project Layout

| Path | Purpose |
|------|---------|
| `squadpy/` | Core framework |
| `squadpy/rcon/` | RCON protocol + async client |
| `squadpy/log_parser/` | Log reader, regex patterns, parser |
| `squadpy/events/` | Event bus + typed event dataclasses |
| `squadpy/discord/` | Discord connector (core service) |
| `squadpy/database/` | SQLAlchemy async setup |
| `squadpy/plugin.py` | Base Plugin class, `@on_event`, `@periodic` |
| `squadpy/plugin_loader.py` | Discovery, validation, error isolation |
| `squadpy/config.py` | TOML loader + Pydantic models |
| `squadpy/server.py` | Orchestrator — startup, shutdown, lifecycle |
| `plugins/` | Built-in plugins (each a subdirectory with `plugin.py`) |
| `config/` | TOML configs — `*.toml.example` tracked, real `*.toml` gitignored |
| `tests/` | Test suite (`pytest-asyncio`, `asyncio_mode = "auto"`) |

## Code Patterns

**Events** — dataclasses inheriting `BaseEvent`:
```python
@dataclass
class SomeEvent(BaseEvent):
    event_name: str = "some_event"  # used for bus dispatch
    field: str = ""
```

**Plugins** — classes inheriting `Plugin`:
```python
class MyPlugin(Plugin):
    name = "My Plugin"
    requires = ["rcon"]

    @on_event("player_connected")
    async def handle(self, event): ...

    @periodic(seconds=30)
    async def tick(self): ...
```

**Config** — Pydantic models validated from TOML:
```python
class SomeConfig(BaseModel):
    field: str = "default"

config = load_config(SomeConfig, Path("config/some.toml"))
```

**Tests** — all async, use `pytest-asyncio` auto mode. No `@pytest.mark.asyncio` needed.

## Conventions

- asyncio stdlib only — no third-party event loops
- Pydantic for all config validation, dataclasses for events
- Error isolation: plugins fail independently, never crash the server
- Logging: `logging.getLogger("squadpy.<component>")` — INFO default
- File rotation: max 10 logs, timestamped backups (`SquadPy_YYYY_MM_DD_HHMMSS.log`)
- Example configs: `*.toml.example` tracked in git, real `*.toml` gitignored

## Squad RCON Quirks

Non-standard protocol — 8192-byte buffer, `0100000` chat break sequences, TCP fragmentation, multi-packet reassembly, request-response ID matching. See `squadpy/rcon/` and the design doc for details.
