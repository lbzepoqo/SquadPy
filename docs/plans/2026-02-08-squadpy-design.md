# SquadPy Design Document

A Python-based framework for Squad game server management, inspired by
[SquadJS](https://github.com/Team-Silver-Sphere/SquadJS) and
[SquadTS](https://github.com/ambroiseRabier/SquadTS).

## Goals

- Pythonic, async-first Squad server management framework
- Modular plugin system with per-plugin configuration and error isolation
- Robust RCON client that handles Squad's non-standard protocol quirks
- First-class Discord integration (embeds, buttons, threads, slash commands)
- Testable by design — mockable services, typed events, dependency injection
- Efficient and simple — no unnecessary complexity
- Deployable via Pterodactyl (clone-and-run)

## Tech Stack

- **Python 3.12+** with **asyncio** (stdlib)
- **discord.py** for Discord integration
- **SQLAlchemy** (async) for database — SQLite default, MySQL/PostgreSQL swappable
- **TOML** for configuration (stdlib `tomllib` for reading)
- **Pydantic** for config validation

## Project Structure

```
SquadPy/
├── squadpy/                    # Core framework
│   ├── __init__.py
│   ├── __main__.py             # Entry point (python -m squadpy)
│   ├── server.py               # Main server orchestrator
│   ├── rcon/
│   │   ├── client.py           # Async RCON client (Squad-quirks-aware)
│   │   └── protocol.py         # Packet encoding/decoding
│   ├── log_parser/
│   │   ├── reader.py           # LogReader abstraction
│   │   ├── local.py            # Local file tail implementation
│   │   ├── ftp.py              # FTP/SFTP implementation
│   │   └── patterns.py         # Regex patterns for Squad log lines
│   ├── events/
│   │   ├── emitter.py          # Async event bus
│   │   └── types.py            # Event dataclasses
│   ├── discord/
│   │   └── connector.py        # discord.py bot wrapper as core service
│   ├── database/
│   │   └── engine.py           # SQLAlchemy async setup
│   ├── plugin.py               # Base Plugin class, decorators
│   ├── config.py               # TOML config loader + validation
│   └── logger.py               # Logging setup + rotation
├── plugins/                    # Built-in plugins (each a subdirectory)
│   ├── auto_kick_unassigned/
│   │   └── plugin.py
│   └── tk_warn/
│       └── plugin.py
├── config/                     # All TOML configs
│   ├── server.toml
│   ├── logging.toml
│   ├── database.toml
│   └── plugins/
│       ├── auto_kick_unassigned.toml
│       └── tk_warn.toml
├── data/                       # Runtime data (SQLite DB, etc.)
├── logs/                       # Log files
├── tests/                      # Test suite
├── requirements.txt
└── pyproject.toml
```

## Architecture

### Core Data Flow

```
┌─────────────┐     log lines      ┌──────────────┐
│  Log Reader  │───────────────────>│  Log Parser   │
│ (local/FTP)  │                    │  (patterns)   │
└─────────────┘                    └──────┬────────┘
                                          │ parsed events
                                          v
┌─────────────┐                    ┌──────────────┐
│ RCON Client  │<──── commands ────│  Event Bus    │
│  (async)     │───── responses ──>│              │
└─────────────┘                    └──────┬────────┘
                                          │ dispatches to
                                          v
                                   ┌──────────────┐
                                   │   Plugins     │
                                   │ (subscribed   │
                                   │  via @on_event)│
                                   └──────┬────────┘
                                          │ can use
                                   ┌──────v────────┐
                                   │  Services      │
                                   │ - rcon         │
                                   │ - discord      │
                                   │ - database     │
                                   └───────────────┘
```

1. **Log Reader** tails the Squad server log (locally or via FTP/SFTP).
2. **Log Parser** matches each line against regex patterns and produces typed
   event objects.
3. **Event Bus** receives events and dispatches them to subscribed plugins.
4. **Plugins** react to events and call back into services (RCON, Discord, DB).
5. **RCON polling** (e.g., `ListPlayers` on interval) also produces events.

Plugins never talk to each other directly. They communicate through events,
keeping them decoupled and independently testable.

### Core Services

| Service    | Required | Description                                |
|------------|----------|--------------------------------------------|
| RCON       | Yes      | Command execution, server queries          |
| Log Reader | No       | Event-driven log parsing (most plugins need this) |
| Discord    | No       | Bot with embeds, buttons, threads, slash commands |
| Database   | No       | SQLite default, MySQL/PostgreSQL swappable |

RCON is the only required service. Plugins declare their dependencies via
`requires = [...]` and fail at load time with a clear message if a required
service is not configured.

## RCON Client

Squad's RCON deviates from the Source RCON spec in several ways:

- Packets can exceed the standard 4096-byte limit
- TCP can split packets mid-stream (fragmentation)
- `0100000` sequences denote chat message breaks (not in spec)
- Multi-packet responses need reassembly before parsing
- Under heavy load, responses can arrive out of order

Reference: https://github.com/Team-Silver-Sphere/SquadJS/pull/291

### Design

```python
class RconClient:
    async def connect(self, host, port, password): ...
    async def execute(self, command: str) -> str: ...
    async def close(self): ...
```

Internals:

- **8192-byte buffer** to handle oversized packets
- **Packet reassembly** — accumulate data until a complete, valid packet is
  received before parsing
- **Request-response matching** via packet IDs with support for out-of-order
  arrivals
- **Auto-reconnect** with configurable retry backoff
- **Request queuing** — pending commands queue during brief disconnections and
  fire once reconnected
- **Per-command timeout** — clean error instead of hanging forever

Convenience methods parse RCON text responses into Python dataclasses:

```python
players = await rcon.list_players()      # list[Player]
squads = await rcon.list_squads()        # list[Squad]
await rcon.broadcast("Server restarting in 5 minutes")
await rcon.warn(steam_id, "Please join a squad")
await rcon.kick(steam_id, "AFK")
await rcon.ban(steam_id, duration, "Cheating")
```

## Event System

Events are typed dataclasses:

```python
@dataclass
class PlayerConnected:
    steam_id: str
    name: str
    timestamp: datetime

@dataclass
class PlayerDied:
    victim: Player
    attacker: Player | None
    weapon: str
    is_teamkill: bool
    timestamp: datetime

@dataclass
class ChatMessage:
    player: Player
    channel: str        # "All", "Team", "Squad"
    message: str
    timestamp: datetime
```

IDE autocompletion works, tests can construct events easily, no guessing at
field names.

## Plugin System

### Plugin API

```python
from squadpy import Plugin, on_event, periodic

class TKWarn(Plugin):
    name = "TK Warn"
    description = "Tracks teamkills and warns/kicks offenders"
    requires = ["rcon"]

    async def on_enable(self):
        self.tk_counts: dict[str, int] = {}

    @on_event("player_died")
    async def handle_teamkill(self, event: PlayerDied):
        if not event.is_teamkill or not event.attacker:
            return
        sid = event.attacker.steam_id
        self.tk_counts[sid] = self.tk_counts.get(sid, 0) + 1
        threshold = self.config.get("kick_threshold", 5)
        await self.rcon.warn(sid, f"Team kill #{self.tk_counts[sid]}")
        if self.tk_counts[sid] >= threshold:
            await self.rcon.kick(sid, "Too many teamkills")

    @on_event("new_map")
    async def reset_counts(self, event):
        self.tk_counts.clear()

    @periodic(seconds=30)
    async def auto_save(self):
        if self.db:
            await self.db.save_tk_counts(self.tk_counts)

    async def on_disable(self):
        if self.db:
            await self.db.save_tk_counts(self.tk_counts)
```

Services available via `self`:

- `self.rcon` — RCON client
- `self.discord` — Discord connector (or `None`)
- `self.db` — Database session (or `None`)
- `self.config` — Plugin's parsed TOML config
- `self.logger` — Named logger (`squadpy.plugins.<name>`)
- `self.server` — Server state (current map, player list, etc.)

### Per-Plugin Configuration

Each plugin has its own TOML file in `config/plugins/`:

```toml
# config/plugins/tk_warn.toml
enabled = true

[settings]
kick_threshold = 5
warning_message = "Team kill #{count} recorded"
reset_on_map_change = true
```

A typo in one config file does not affect other plugins.

### Error Isolation

- A plugin failing to load does not stop others
- A plugin throwing during event handling gets caught and logged; other plugins
  still receive the event
- If a plugin errors repeatedly (e.g., 10 times in 60 seconds), it is
  auto-disabled with a warning
- Clear startup summary shows which plugins loaded, failed, or are disabled

### Plugin Hot-Reload

Plugins can be reloaded at runtime without restarting the app:

1. Call `on_disable()` (saves state)
2. Re-read the plugin's TOML config
3. Re-import the plugin module (fresh code)
4. Re-instantiate and call `on_enable()`
5. Re-register event subscriptions

Triggered via Discord slash command (`/reload <plugin_name>`) or future CLI.

## Discord Integration

Discord is a core service, not a plugin. Plugins use it via `self.discord`
and decorators.

### Connector

```python
class DiscordConnector:
    async def send(self, channel_id, content=None, embed=None, view=None): ...
    async def create_thread(self, message, name): ...
    async def edit_message(self, message_id, **kwargs): ...
    def get_channel(self, channel_id): ...
```

Plugins also get access to the raw `discord.py` bot for full power.

### Discord Decorators

| Decorator                          | Handles               |
|------------------------------------|-----------------------|
| `@slash_command`                   | Slash commands        |
| `@on_discord("button_click")`      | Button interactions   |
| `@on_discord("select_menu")`       | Dropdown selections   |
| `@on_discord("thread_message")`    | Messages in threads   |
| `@on_discord("modal_submit")`      | Modal form submissions|

### Example: Admin Request Plugin

```python
class AdminRequest(Plugin):
    requires = ["rcon", "discord"]

    @on_event("chat_message")
    async def handle_admin_request(self, event: ChatMessage):
        if not event.message.startswith("!admin"):
            return
        reason = event.message.removeprefix("!admin").strip()
        embed = discord.Embed(title="Admin Support Request", description=reason)
        embed.add_field(name="Player", value=event.player.name)
        embed.add_field(name="Squad", value=event.player.squad)
        embed.add_field(name="Team", value=event.player.team)
        view = AdminTicketView(self, event.player)
        msg = await self.discord.send(self.config["channel_id"], embed=embed, view=view)
        await self.discord.create_thread(msg, f"Ticket: {event.player.name}")

    @on_discord("button_click", custom_id="claim_ticket")
    async def handle_claim(self, interaction):
        await interaction.response.edit_message(
            content=f"Claimed by: {interaction.user.display_name}"
        )

    @on_discord("thread_message")
    async def relay_to_player(self, message, ticket):
        await self.rcon.warn(
            ticket.player.steam_id,
            f"[Admin] {message.author.display_name}: {message.content}"
        )
```

### Built-in Discord Plugins

- **PluginManager** — `/reload`, `/plugins`, `/status` slash commands
- **ServerStatus** — Periodically updated embed with player count, map, etc.

## Persistence & Data Safety

Three layers protect against data loss on crash or restart:

1. **Graceful shutdown** — `on_disable()` called on each plugin during normal
   shutdown (SIGTERM/SIGINT from Pterodactyl restart). Plugins flush state to DB.
2. **Periodic flush** — `@periodic` decorator lets plugins auto-save in-memory
   state every N seconds. A hard crash loses at most one interval of data.
3. **Write-through** — Critical actions (bans, warnings, ticket creation) write
   to DB immediately.

| Data type               | Strategy           | Max data loss on crash |
|-------------------------|--------------------|------------------------|
| Critical (bans, tickets)| Write-through      | None                   |
| Accumulated (TK counts) | Periodic flush     | ~30 seconds            |
| Session-only (timers)   | In-memory only     | All (by design)        |

## Logging

- Python stdlib `logging` module
- **Default level: INFO** (not noisy out of the box)
- Configurable verbosity per component
- Console output: clean, minimal
- File output: rotated log files

### File Rotation

- Current log: `logs/SquadPy.log`
- Backups: `logs/SquadPy_2026_02_08_<time>.log`
- Maximum 10 log files, oldest deleted first

### Configuration

```toml
# config/logging.toml
level = "INFO"                  # DEBUG, INFO, WARNING, ERROR

[console]
level = "INFO"

[file]
enabled = true
level = "DEBUG"
path = "logs"
max_files = 10
```

## Startup & Shutdown

### Startup Sequence

1. Load core configs (`server.toml`, `logging.toml`, `database.toml`)
2. Connect RCON and verify auth
3. Start log reader (if configured)
4. Connect Discord bot (if configured)
5. Connect database (if configured)
6. Load plugins one by one:
   - Read plugin's TOML config
   - Validate config
   - Instantiate plugin, inject services
   - Call `on_enable()`
   - Register event subscriptions
7. Print startup summary

### Startup Summary

```
SquadPy v0.1.0 — Server: My Squad Server

  Core Services:
    RCON            ok   connected (192.168.1.10:21114)
    Log Reader      ok   tailing (local)
    Discord         ok   connected (SquadPy#1234)
    Database        ok   sqlite (data/squadpy.db)

  Plugins:
    AutoKickUnassigned   ok       enabled
    TKWarn               ok       enabled
    DiscordChat          FAIL     missing 'channel_id' in config
    SeedReward           --       disabled
```

### Shutdown Sequence

1. Stop accepting new events
2. Call `on_disable()` on each plugin (parallel, with timeout)
3. Close Discord bot
4. Close database connections
5. Close RCON
6. Exit

## Testing

- All services are injectable — mock RCON, mock log reader, mock Discord
- Events are plain dataclasses — easy to construct in tests
- Plugins are classes — instantiate, call handler methods, assert results
- No global state — each test gets a fresh plugin instance
- Log parser testable with sample log lines (no server needed)
- RCON protocol testable with raw byte fixtures

## Implementation Roadmap

### Phase 1 — Core Foundation

- Project scaffolding, config loader, logging setup
- RCON client (Squad-quirks-aware, async, auto-reconnect)
- Event bus
- Plugin base class and loader with error isolation
- Startup summary display

### Phase 2 — Log Parser

- LogReader abstraction (local + FTP/SFTP)
- Squad log regex patterns (connect, disconnect, kills, chat, map changes)
- Events wired into the event bus

### Phase 3 — Discord Integration

- Discord connector as core service
- `@on_discord`, `@slash_command` decorators
- Built-in PluginManager plugin (`/reload`, `/plugins`, `/status`)

### Phase 4 — Database & Persistence

- SQLAlchemy async setup (SQLite default)
- `@periodic` state flush
- Graceful shutdown state saving

### Phase 5 — Built-in Plugins

- AutoKickUnassigned
- TKWarn
- ServerStatus (Discord embed)
- AdminRequest (ticket system foundation)
- DiscordChatBridge
