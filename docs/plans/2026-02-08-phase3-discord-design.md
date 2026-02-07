# Phase 3 — Discord Integration Design

## Overview

Add Discord as a core service to SquadPy. Plugins interact with Discord via
convenience methods on `DiscordConnector` and decorators (`@slash_command`,
`@on_discord`). A built-in PluginManager plugin provides `/status`, `/plugins`,
and `/reload` slash commands as proof of the system.

## Design Decisions

- **Single event loop** — `bot.start()` runs as an `asyncio.Task`, no threads
- **Guild sync only** — `guild_id` is required config; no global command sync
- **Convenience + raw access** — `DiscordConnector` provides `send()`,
  `create_thread()`, etc. for common operations; `self.discord.bot` exposed
  for full discord.py power
- **Auto-namespaced `custom_id`** — interaction handlers are prefixed with
  `plugin_name:` to prevent collisions between plugins; transparent to authors

## 1. Discord Config

Added to `config.py` as a Pydantic model. Added to `server.toml.example` under
`[discord]`.

```python
class DiscordConfig(BaseModel):
    enabled: bool = False
    token: str = ""
    guild_id: int = 0
    command_prefix: str = "!"
```

```toml
# [discord]
# enabled = true
# token = "your_bot_token_here"
# guild_id = 123456789012345678
```

Validation: if `enabled = true` but `token` or `guild_id` are missing/default,
Pydantic raises a clear error at startup. Channel IDs belong in individual
plugin configs, not here.

## 2. DiscordConnector

`squadpy/discord/connector.py` — wraps `discord.py` `commands.Bot`.

```python
class DiscordConnector:
    def __init__(self, config: DiscordConfig):
        self.bot = commands.Bot(...)
        self.guild_id = config.guild_id
        self.guild: discord.Guild          # resolved on_ready
        self._ready = asyncio.Event()

    # Lifecycle
    async def start(self, token: str) -> None
    async def wait_until_ready(self) -> None
    async def close(self) -> None

    # Convenience (the 80% API)
    async def send(self, channel_id, content=None, embed=None, view=None) -> Message
    async def edit_message(self, message, **kwargs) -> Message
    async def create_thread(self, message, name) -> Thread
    def get_channel(self, channel_id) -> Channel | None

    # Interaction routing (internal)
    def register_slash_command(self, plugin_name, func, **kwargs) -> None
    def register_interaction_handler(self, plugin_name, event_type, custom_id, func) -> None
    async def sync_commands(self) -> None
```

Key behaviors:
- `start()` fires `bot.start(token)` as `asyncio.Task`
- `wait_until_ready()` uses `asyncio.Event` set in `on_ready`
- Interaction handlers stored in dict keyed by `plugin_name:custom_id`
- `sync_commands()` called once after all plugins are loaded
- `close()` calls `bot.close()` during shutdown

## 3. Decorators

Added to `squadpy/plugin.py` alongside `@on_event` and `@periodic`.

### `@slash_command`

```python
@slash_command(name="status", description="Show server status")
async def show_status(self, interaction: discord.Interaction):
    await interaction.response.send_message("Players: 78/100")
```

Registers an `app_commands` command on `bot.tree` scoped to the guild. Decorator
stores metadata on the method; plugin loader reads it during load and calls
`connector.register_slash_command()`.

### `@on_discord`

```python
@on_discord("button_click", custom_id="claim_ticket")
async def handle_claim(self, interaction: discord.Interaction):
    await interaction.response.edit_message(content="Claimed!")
```

Supported event types: `button_click`, `select_menu`, `modal_submit`,
`thread_message`.

**Component interactions** (button, select, modal): routed via namespaced
`custom_id`. The connector's `on_interaction` listener matches
`plugin_name:custom_id` and dispatches. Plugin authors use plain
`custom_id="claim_ticket"` — the connector auto-prefixes on registration.
A helper on the connector ensures buttons/views created by a plugin get the
right prefix automatically.

**Thread messages**: no `custom_id` routing. Plugins track which threads they
own; handler fires for messages in those threads. Plugin-managed state.

Error isolation: same as `@on_event` — exceptions caught, logged, don't affect
other handlers.

## 4. Server Orchestrator Integration

Changes to `squadpy/server.py`.

### Startup (between RCON connect and plugin loading)

1. If `discord.enabled`, instantiate `DiscordConnector(config.discord)`
2. `connector.start(token)` — bot runs as asyncio task
3. `await connector.wait_until_ready()` — block until connected
4. `services["discord"] = connector`
5. Load plugins (Discord-requiring plugins now get the connector)
6. After all plugins loaded: `connector.sync_commands()` once

### Shutdown

1. `on_disable()` on each plugin (existing)
2. `await connector.close()`
3. Close other services (existing)

### Startup Summary

```
  Core Services:
    RCON            ok   connected (192.168.1.10:21114)
    Log Reader      ok   tailing (local)
    Discord         ok   connected (SquadPy#1234)
    Database        --   not configured
```

If Discord fails to connect (bad token, network), it logs the error, sets
`services["discord"] = None`. Discord-requiring plugins fail to load with a
clear message. Non-Discord plugins load fine.

## 5. Plugin Loader Changes

Extend `squadpy/plugin_loader.py` to scan for new decorator markers.

### During plugin load (after instantiation)

1. Scan methods for `_slash_command_meta` → `connector.register_slash_command()`
2. Scan methods for `_on_discord_meta` → `connector.register_interaction_handler()`

### During plugin unload (hot-reload)

1. Deregister plugin's slash commands from bot tree
2. Remove plugin's interaction handlers from routing dict
3. `connector.sync_commands()` to update guild

The existing `requires` check handles the case where Discord is unavailable —
no changes needed.

## 6. Built-in PluginManager Plugin

`plugins/plugin_manager/plugin.py` with
`config/plugins/plugin_manager.toml.example`.

```python
class PluginManager(Plugin):
    name = "Plugin Manager"
    requires = ["rcon", "discord"]
```

### Slash Commands

**`/status`** — Server overview embed:
- Server name, current map/layer
- Player count (RCON `ListPlayers`)
- Uptime
- Core service status

**`/plugins`** — Plugin list embed:
- Name, status (enabled/disabled/failed), description
- Color-coded: green enabled, red failed, grey disabled

**`/reload <plugin_name>`** — Hot-reload a plugin:
- Calls `server.reload_plugin(plugin_name)`
- Reports success/failure
- Permission-gated via configurable admin role

### Config

```toml
enabled = true

[settings]
admin_role_id = 123456789012345678
```

## 7. Testing Strategy

All tests mock discord.py — no real bot connections.

### Connector tests (`tests/test_discord_connector.py`)
- Mock `commands.Bot` — verify lifecycle (start, close)
- `send()`, `edit_message()`, `create_thread()` call correct bot methods
- `register_slash_command()` adds to bot tree
- `register_interaction_handler()` stores with namespaced key
- Interaction routing dispatches to correct handler

### Decorator tests (`tests/test_discord_decorators.py`)
- `@slash_command` sets correct metadata on method
- `@on_discord("button_click", custom_id="x")` sets correct metadata
- Unknown event type raises at decoration time

### Integration tests (`tests/test_discord_integration.py`)
- Plugin loader discovers and registers new markers
- Hot-reload deregisters old handlers, registers new, calls sync
- `requires = ["discord"]` fails when Discord is None
- Namespaced `custom_id`: two plugins with same ID don't collide

### PluginManager tests (`tests/test_plugin_manager.py`)
- `/status` returns embed with expected fields
- `/plugins` lists loaded plugins
- `/reload` calls `server.reload_plugin()`, reports result
- `/reload` without admin role is rejected

## Files to Create/Modify

| File | Action |
|------|--------|
| `squadpy/config.py` | Add `DiscordConfig` model, add to `ServerConfig` |
| `squadpy/discord/connector.py` | New — `DiscordConnector` class |
| `squadpy/discord/__init__.py` | Export `DiscordConnector` |
| `squadpy/plugin.py` | Add `@slash_command`, `@on_discord` decorators |
| `squadpy/plugin_loader.py` | Scan for new decorator markers, register with connector |
| `squadpy/server.py` | Discord startup/shutdown, update summary |
| `squadpy/__init__.py` | Export new decorators |
| `config/server.toml.example` | Add `[discord]` section |
| `plugins/plugin_manager/plugin.py` | New — PluginManager plugin |
| `config/plugins/plugin_manager.toml.example` | New — PluginManager config |
| `tests/test_discord_connector.py` | New — connector tests |
| `tests/test_discord_decorators.py` | New — decorator tests |
| `tests/test_discord_integration.py` | New — integration tests |
| `tests/test_plugin_manager.py` | New — PluginManager tests |
| `pyproject.toml` | Add `discord.py` dependency |
