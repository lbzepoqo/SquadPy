# SquadPy

A Python-based framework for [Squad](https://joinsquad.com/) game server management. Inspired by [SquadJS](https://github.com/Team-Silver-Sphere/SquadJS) and [SquadTS](https://github.com/ambroiseRabier/SquadTS).

## Features

- **Async RCON client** — handles Squad's non-standard protocol (oversized packets, TCP fragmentation, multi-packet reassembly)
- **Log parser** — tails server logs (local or SFTP), extracts 15+ event types via regex
- **Event-driven plugin system** — `@on_event`, `@periodic`, `@slash_command` decorators with per-plugin TOML config
- **Discord integration** — embeds, buttons, threads, slash commands as a core service
- **Database** — SQLAlchemy async with SQLite default, MySQL/PostgreSQL swappable
- **Error isolation** — plugins fail independently, auto-disable after repeated errors, never crash the server
- **Hot-reload** — reload plugins at runtime via Discord `/reload` command

## Requirements

- Python 3.12+
- A running Squad dedicated server with RCON enabled

## Quick Start

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-username/SquadPy.git
   cd SquadPy
   ```

2. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Copy example configs**

   ```bash
   cp config/server.toml.example config/server.toml
   cp config/logging.toml.example config/logging.toml
   ```

4. **Edit `config/server.toml`** with your server's RCON details

   ```toml
   [rcon]
   host = "127.0.0.1"
   port = 21114
   password = "your_rcon_password"
   ```

5. **Run**

   ```bash
   python -m squadpy
   ```

## Configuration

All configuration uses TOML files in the `config/` directory. Example files (`*.toml.example`) are provided for every config — copy them and remove the `.example` suffix.

| Config | Purpose |
|--------|---------|
| `config/server.toml` | RCON connection, log reader, Discord bot |
| `config/logging.toml` | Log level, file rotation settings |
| `config/database.toml` | Database driver and connection (optional) |
| `config/plugins/*.toml` | Per-plugin settings |

### Optional Services

Enable these by uncommenting the relevant sections in `config/server.toml`:

- **Log reader** — required for most event-driven plugins (kills, connections, chat)
- **Discord** — required for slash commands, embeds, and Discord-facing plugins
- **Database** — required for plugins that persist data across restarts

## Architecture

```
Log Reader (local/SFTP) --> Log Parser (regex + state) --> Event Bus --> Plugins
                                                              ^
RCON Client (async, Squad-quirks-aware) ----------------------+
```

Plugins subscribe to events and call back into services (RCON, Discord, Database). They never talk to each other directly — communication happens through events, keeping plugins decoupled and independently testable.

## Built-in Plugins

| Plugin | Requires | Description |
|--------|----------|-------------|
| **AutoKickUnassigned** | rcon | Warns then kicks players not in a squad |
| **TKWarn** | rcon | Tracks teamkills, warns offenders, kicks after threshold |
| **ServerStatus** | rcon, discord | Live-updating Discord embed with server info |
| **AdminRequest** | rcon, discord | `!admin` chat command creates Discord tickets with threads |
| **DiscordChatBridge** | rcon, discord | Two-way game chat <-> Discord channel bridge |
| **PluginManager** | discord | `/status`, `/plugins`, `/reload` slash commands |

Enable plugins by copying their example config:

```bash
cp config/plugins/auto_kick_unassigned.toml.example config/plugins/auto_kick_unassigned.toml
```

## Writing Plugins

Create a directory under `plugins/` with a `plugin.py` file:

```python
from squadpy.plugin import Plugin, on_event, periodic

class MyPlugin(Plugin):
    name = "My Plugin"
    description = "Does something useful"
    requires = ["rcon"]

    async def on_enable(self):
        self.logger.info("Plugin enabled")

    @on_event("player_connected")
    async def greet_player(self, event):
        await self.rcon.warn(event.eos_id, "Welcome to the server!")

    @periodic(seconds=60)
    async def periodic_task(self):
        players = await self.rcon.list_players()
        self.logger.info(f"{len(players)} players online")

    async def on_disable(self):
        self.logger.info("Plugin disabled")
```

**Available services** on `self`:

| Service | Description |
|---------|-------------|
| `self.rcon` | RCON client — execute commands, list players/squads, broadcast, warn, kick |
| `self.discord` | Discord connector — send messages, create threads, edit embeds |
| `self.db` | Database session factory (`None` if not configured) |
| `self.config` | Plugin's parsed TOML config |
| `self.logger` | Named logger (`squadpy.plugins.<name>`) |
| `self.event_bus` | Event bus for emitting custom events |

**Decorators**:

| Decorator | Description |
|-----------|-------------|
| `@on_event("event_name")` | Subscribe to server events |
| `@periodic(seconds=N)` | Run a method on an interval |
| `@slash_command(name, description)` | Register a Discord slash command |
| `@on_discord("button_click", custom_id="...")` | Handle Discord interactions |

## Events

Events are typed dataclasses. Key events include:

- `PlayerConnected`, `PlayerDisconnected` — join/leave
- `PlayerDamaged`, `PlayerWounded`, `PlayerDied`, `PlayerRevived` — combat
- `PlayerPossess`, `PlayerUnpossess` — vehicle/role changes
- `ChatMessage` — in-game chat (All/Team/Squad channels)
- `NewGame`, `RoundEnded`, `RoundTickets` — match lifecycle
- `ServerTickRate`, `AdminBroadcast`, `DeployableDamaged` — server state

## Testing

```bash
pytest tests/ -v
```

All tests are async using `pytest-asyncio` with auto mode. Services are mockable — no running server needed.

## Project Layout

```
squadpy/              Core framework
  rcon/               RCON protocol + async client
  log_parser/         Log reader, regex patterns, parser
  events/             Event bus + typed event dataclasses
  discord/            Discord connector (core service)
  database/           SQLAlchemy async setup
  plugin.py           Base Plugin class + decorators
  plugin_loader.py    Plugin discovery + error isolation
  config.py           TOML loader + Pydantic models
  server.py           Orchestrator (startup, shutdown, lifecycle)
plugins/              Built-in plugins (each a subdirectory)
config/               TOML configs (*.toml.example tracked, *.toml gitignored)
tests/                Test suite
```

## License

This project is not yet licensed. All rights reserved.
