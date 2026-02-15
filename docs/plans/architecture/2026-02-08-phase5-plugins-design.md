# Phase 5 Design — Built-in Plugins

## Overview

Phase 5 adds five built-in plugins and the core infrastructure they depend on (RCON convenience methods, ChatMessage event). No changes to the plugin framework itself — everything builds on existing patterns from Phases 1-4.

## Prerequisites: Core Changes

### RCON Convenience Methods

Add typed dataclasses and helper methods to the RCON client so plugins don't duplicate parsing logic.

**New file `squadpy/rcon/types.py`**:

```python
@dataclass
class RconPlayer:
    id: int              # In-game player index
    steam_id: str
    eos_id: str
    name: str
    team_id: int         # 1 or 2
    squad_id: int        # 0 = unassigned

@dataclass
class RconSquad:
    id: int
    name: str
    size: int
    team_id: int
    team_name: str
    is_locked: bool
```

**New methods on `RconClient`**:

| Method | RCON Command | Returns |
|--------|-------------|---------|
| `list_players()` | `ListPlayers` | `list[RconPlayer]` |
| `list_squads()` | `ListSquads` | `list[RconSquad]` |
| `broadcast(msg)` | `AdminBroadcast <msg>` | `str` |
| `warn(steam_id, msg)` | `AdminWarn <id> <msg>` | `str` |
| `kick(steam_id, reason)` | `AdminKick <id> <reason>` | `str` |
| `show_current_map()` | `ShowCurrentMap` | `str` |
| `show_next_map()` | `ShowNextMap` | `str` |

Each convenience method calls `self.execute()` internally. Parsing uses regex on the well-known RCON response formats.

### ChatMessage Event

**New event in `squadpy/events/types.py`**:

```python
@dataclass
class ChatMessage(BaseEvent):
    event_name: str = "chat_message"
    player_name: str = ""
    steam_id: str = ""
    channel: str = ""       # "ChatAll", "ChatTeam", "ChatSquad", "ChatAdmin"
    message: str = ""
```

**Parsing in `server.py` `_handle_chat()`**: Squad RCON chat packets arrive as text like `[ChatAll] [SteamID:12345678901234567] Player Name : message text`. Parse with regex, construct `ChatMessage`, emit onto `self._event_bus`. If parse fails, log and continue.

## Plugin 1: AutoKickUnassigned

**Purpose**: Periodically checks for players not in any squad and kicks them after a grace period (multiple warnings).

**Directory**: `plugins/auto_kick_unassigned/plugin.py`
**Requires**: `["rcon"]`

**Config** (`auto_kick_unassigned.toml.example`):
```toml
enabled = true

[settings]
check_interval = 30
warnings_before_kick = 3
min_players = 20
warning_message = "Please join a squad or you will be kicked"
kick_message = "Kicked for not joining a squad"
```

**Behavior**:
- `@periodic(seconds=check_interval)` polls `rcon.list_players()` and `rcon.list_squads()`
- Tracks `dict[str, int]` mapping steam_id -> consecutive unassigned check count
- Each check: player with no squad_id gets count incremented + `rcon.warn()`. Count >= `warnings_before_kick` triggers `rcon.kick()`
- Players who join a squad get removed from tracking
- Skip enforcement when player count < `min_players` (seeding protection)
- Session-only data, resets on restart (by design)

## Plugin 2: TKWarn

**Purpose**: Tracks teamkills per round, warns offenders, kicks after threshold.

**Directory**: `plugins/tk_warn/plugin.py`
**Requires**: `["rcon"]`

**Config** (`tk_warn.toml.example`):
```toml
enabled = true

[settings]
kick_threshold = 5
warning_message = "Team kill #{count} recorded. {threshold} = kick."
kick_message = "Kicked for excessive teamkills ({count})"
```

**Behavior**:
- Maintains player cache (`dict[str, RconPlayer]` keyed by name) refreshed via `@periodic` calling `rcon.list_players()` — provides team_id per player
- `@on_event("player_wounded")` — looks up attacker and victim in player cache. Same `team_id` and attacker != victim = teamkill
  - Increments `tk_counts[attacker_steam_id]`
  - Sends `rcon.warn()` with count
  - Count >= `kick_threshold` triggers `rcon.kick()`
- Uses `player_wounded` (fires before `player_died`, gives chance to warn)
- `@on_event("new_game")` — resets `tk_counts`
- Session-only, no DB

## Plugin 3: ServerStatus

**Purpose**: Persistent Discord embed showing live server info, edited in place.

**Directory**: `plugins/server_status/plugin.py`
**Requires**: `["rcon", "discord"]`

**Config** (`server_status.toml.example`):
```toml
enabled = true

[settings]
channel_id = 0
update_interval = 60
```

**Behavior**:
- `on_enable()` sends initial embed to channel, stores `discord.Message` for future edits
- `@periodic(seconds=update_interval)` queries `rcon.list_players()`, `rcon.show_current_map()`, `rcon.show_next_map()`, builds updated embed, calls `self.discord.edit_message()`
- Embed fields: current map/layer, next map/layer, player count ("48/100"), squad count, tick rate
- `@on_event("server_tick_rate")` caches latest tick rate
- `@on_event("new_game")` caches map/layer from event
- If stored message is unavailable, posts a new one on next cycle
- `on_disable()` edits embed to show "Offline"

## Plugin 4: AdminRequest

**Purpose**: `!admin <reason>` in-game chat creates a Discord ticket with embed, claim button, auto-thread, and message relay.

**Directory**: `plugins/admin_request/plugin.py`
**Requires**: `["rcon", "discord"]`

**Config** (`admin_request.toml.example`):
```toml
enabled = true

[settings]
channel_id = 0
ping_role_id = 0
command_prefix = "!admin"
```

**Behavior**:
- Maintains `active_tickets: dict[int, TicketInfo]` (thread_id -> ticket data)
- `@periodic` refreshes player cache via `rcon.list_players()`
- `@on_event("chat_message")` — on prefix match:
  - Build embed with player name, reason, timestamp
  - Create `discord.ui.View` with "Claim" button (custom_id `"claim_ticket"`)
  - Send to channel, optionally ping role
  - Create thread from message: `"Ticket: {player_name}"`
  - Store ticket info keyed by thread ID
  - Warn player: "Your admin request has been submitted"
- `@on_discord("button_click", custom_id="claim_ticket")` — edit embed to show claimer, disable button
- `@on_discord("thread_message")` — relay admin's message to player via `rcon.warn()`
- Session-only tickets, lost on restart (acceptable for V1)

## Plugin 5: DiscordChatBridge

**Purpose**: Two-way bridge between in-game chat and a Discord channel.

**Directory**: `plugins/discord_chat_bridge/plugin.py`
**Requires**: `["rcon", "discord"]`

**Config** (`discord_chat_bridge.toml.example`):
```toml
enabled = true

[settings]
channel_id = 0
chat_channels = ["ChatAll"]
show_channel_prefix = true
discord_to_game_format = "[Discord] {author}: {message}"
```

**Behavior**:
- **Game -> Discord**: `@on_event("chat_message")` — if channel in `chat_channels`, send as plain text to Discord channel. Optionally prefix with `[All]` etc.
- **Discord -> Game**: Register `on_message` listener via `self.discord.bot.add_listener()` in `on_enable()`. If message is in bridged channel, from non-bot user, call `rcon.broadcast()` with formatted message.
- `on_disable()` removes the listener via `self.discord.bot.remove_listener()`
- Ignores bot messages to prevent echo loops
- No DB — purely real-time relay

## File List

### Core changes
| File | Change |
|------|--------|
| `squadpy/rcon/types.py` | **New** — `RconPlayer`, `RconSquad` dataclasses |
| `squadpy/rcon/client.py` | Add 7 convenience methods |
| `squadpy/events/types.py` | Add `ChatMessage` event |
| `squadpy/server.py` | Parse chat in `_handle_chat()`, emit `ChatMessage` |

### Plugins (new directories)
| File | Plugin |
|------|--------|
| `plugins/auto_kick_unassigned/plugin.py` | AutoKickUnassigned |
| `plugins/tk_warn/plugin.py` | TKWarn |
| `plugins/server_status/plugin.py` | ServerStatus |
| `plugins/admin_request/plugin.py` | AdminRequest |
| `plugins/discord_chat_bridge/plugin.py` | DiscordChatBridge |

### Example configs
| File |
|------|
| `config/plugins/auto_kick_unassigned.toml.example` |
| `config/plugins/tk_warn.toml.example` |
| `config/plugins/server_status.toml.example` |
| `config/plugins/admin_request.toml.example` |
| `config/plugins/discord_chat_bridge.toml.example` |

### Tests
| File | Covers |
|------|--------|
| `tests/test_rcon_helpers.py` | RCON response parsing |
| `tests/test_chat_message.py` | Chat packet -> ChatMessage event |
| `tests/test_plugin_auto_kick.py` | AutoKickUnassigned |
| `tests/test_plugin_tk_warn.py` | TKWarn |
| `tests/test_plugin_server_status.py` | ServerStatus |
| `tests/test_plugin_admin_request.py` | AdminRequest |
| `tests/test_plugin_chat_bridge.py` | DiscordChatBridge |

## Implementation Order

1. RCON types + convenience methods + tests
2. ChatMessage event + server.py parsing + tests
3. AutoKickUnassigned + tests
4. TKWarn + tests
5. ServerStatus + tests
6. AdminRequest + tests
7. DiscordChatBridge + tests
