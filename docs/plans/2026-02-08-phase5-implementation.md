# Phase 5 Implementation Plan — Built-in Plugins

Reference: `docs/plans/2026-02-08-phase5-plugins-design.md`

## Step 1: RCON Types (`squadpy/rcon/types.py`)

New file with dataclasses for RCON response parsing results.

```python
from dataclasses import dataclass

@dataclass
class RconPlayer:
    id: int              # In-game player index from ListPlayers
    steam_id: str
    eos_id: str
    name: str
    team_id: int         # 1 or 2, 0 if N/A
    squad_id: int        # 0 if unassigned (N/A)
    is_leader: bool
    role: str

@dataclass
class RconSquad:
    id: int
    name: str
    size: int
    locked: bool
    creator_name: str
    creator_steam_id: str
    creator_eos_id: str
    team_id: int
    team_name: str
```

## Step 2: RCON Convenience Methods (`squadpy/rcon/client.py`)

Add parsing functions and convenience methods. Import `parse_online_ids` from `squadpy.log_parser.id_parser`.

### Response Formats (from SquadJS source)

**ListPlayers** — each line:
```
ID: 0 | Online IDs: EOS: <32hex> steam: <17digits> | Name: PlayerName | Team ID: 1 | Squad ID: 1 | Is Leader: True | Role: USA_Rifleman_01
```
Team ID and Squad ID can be `N/A` (unassigned).

Regex:
```python
_PLAYER_RE = re.compile(
    r"^ID: (?P<id>\d+) \| Online IDs:(?P<ids>[^|]+)\| Name: (?P<name>.+) \| "
    r"Team ID: (?P<team_id>\d+|N/A) \| Squad ID: (?P<squad_id>\d+|N/A) \| "
    r"Is Leader: (?P<is_leader>True|False) \| Role: (?P<role>.+)$"
)
```

**ListSquads** — team headers + squad lines:
```
----- Active Squads -----
Team ID: 1 (United States Army)
ID: 1 | Name: Squad 1 | Size: 9 | Locked: False | Creator Name: PlayerName | Creator Online IDs: EOS: <hex> steam: <digits>
Team ID: 2 (Russian Ground Forces)
ID: 1 | Name: Squad 1 | Size: 4 | Locked: True | Creator Name: AnotherPlayer | Creator Online IDs: EOS: <hex> steam: <digits>
```

Regexes:
```python
_TEAM_RE = re.compile(r"^Team ID: (?P<team_id>\d+) \((?P<team_name>.+)\)")
_SQUAD_RE = re.compile(
    r"^ID: (?P<id>\d+) \| Name: (?P<name>.+) \| Size: (?P<size>\d+) \| "
    r"Locked: (?P<locked>True|False) \| Creator Name: (?P<creator_name>.+) \| "
    r"Creator Online IDs:(?P<creator_ids>.+)$"
)
```

**ShowCurrentMap**: `Current level is <level>, layer is <layer>`
**ShowNextMap**: `Next level is <level>, layer is <layer>`

### New methods on RconClient

```python
async def list_players(self) -> list[RconPlayer]: ...
async def list_squads(self) -> list[RconSquad]: ...
async def broadcast(self, message: str) -> str: ...
async def warn(self, player_id: str, message: str) -> str: ...
async def kick(self, player_id: str, reason: str) -> str: ...
async def show_current_map(self) -> str: ...
async def show_next_map(self) -> str: ...
```

`warn` and `kick` quote the player_id: `AdminWarn "{id}" {message}`, `AdminKick "{id}" {reason}`.

### Tests (`tests/test_rcon_helpers.py`)

- Parse sample ListPlayers responses (multiple players, empty, N/A team/squad)
- Parse sample ListSquads responses (multiple teams, locked/unlocked)
- Parse ShowCurrentMap / ShowNextMap
- Test convenience methods call execute() with correct command strings (mock execute)

## Step 3: ChatMessage Event

### `squadpy/events/types.py` — add ChatMessage

```python
@dataclass
class ChatMessage(BaseEvent):
    event_name: str = "chat_message"
    player_name: str = ""
    steam_id: str = ""
    eos_id: str = ""
    channel: str = ""       # "ChatAll", "ChatTeam", "ChatSquad", "ChatAdmin"
    message: str = ""
```

### `squadpy/server.py` — update `_handle_chat()`

Parse RCON chat packet body format:
```
[ChatAll] [Online IDs:EOS: <32hex> steam: <17digits>] PlayerName : message text
```

Note: SquadJS regex uses `[Online IDs:...]` (with space before IDs content).

Regex:
```python
_CHAT_RE = re.compile(
    r"\[(?P<channel>ChatAll|ChatTeam|ChatSquad|ChatAdmin)\] "
    r"\[Online IDs:(?P<ids>[^\]]+)\] "
    r"(?P<name>.+?) : (?P<message>.*)"
)
```

Parse, build ChatMessage, emit to event bus. If no match, just log (admin cam, warn, kick messages also come through chat packets — don't crash on those).

### Tests (`tests/test_chat_message.py`)

- Parse various chat formats (ChatAll, ChatTeam, ChatSquad, ChatAdmin)
- Non-matching chat packets (admin cam, warn) don't crash
- ChatMessage is emitted on event bus

## Step 4: AutoKickUnassigned Plugin

### `plugins/auto_kick_unassigned/plugin.py`

```python
class AutoKickUnassigned(Plugin):
    name = "Auto Kick Unassigned"
    requires = ["rcon"]
```

- `on_enable()`: init `self._warnings: dict[str, int]` (steam_id -> count)
- `@periodic(seconds=check_interval)` `check_unassigned()`:
  - `players = await self.rcon.list_players()`
  - If `len(players) < min_players`: clear warnings, return
  - For each player with `squad_id == 0`:
    - Increment warning count
    - `await self.rcon.warn(steam_id, warning_message)`
    - If count >= `warnings_before_kick`: `await self.rcon.kick(steam_id, kick_message)`
  - Remove tracking for players now in a squad
- `@on_event("new_game")`: clear warnings

Note: `check_interval` from config is the desired interval, but `@periodic` takes a static value. We'll read config in `on_enable()` and use a default for the decorator, then in the periodic method check if enough time has elapsed based on config. Actually, simpler: use a reasonable default like 30s in the decorator — the config example matches this.

### `config/plugins/auto_kick_unassigned.toml.example`

### Tests (`tests/test_plugin_auto_kick.py`)

- Mock RCON returns players (some unassigned, some in squads)
- After N checks, unassigned players get warned then kicked
- Players who join squad stop getting warned
- Below min_players threshold → no kicks
- New game resets warnings

## Step 5: TKWarn Plugin

### `plugins/tk_warn/plugin.py`

```python
class TKWarn(Plugin):
    name = "TK Warn"
    requires = ["rcon"]
```

- `on_enable()`: init `self._tk_counts: dict[str, int]`, `self._player_cache: dict[str, RconPlayer]`
- `@periodic(seconds=30)` `refresh_players()`: `self._player_cache` keyed by player name from `rcon.list_players()`
- `@on_event("player_wounded")` `handle_wound(event)`:
  - Look up `event.victim_name` and `event.attacker.name` in `_player_cache`
  - If both found, same `team_id`, different players → TK
  - Increment `_tk_counts[attacker.steam_id]`
  - `rcon.warn(attacker.steam_id, ...)` with count
  - If count >= `kick_threshold`: `rcon.kick(attacker.steam_id, ...)`
- `@on_event("new_game")` `reset_counts()`: clear `_tk_counts`

### `config/plugins/tk_warn.toml.example`

### Tests (`tests/test_plugin_tk_warn.py`)

- TK detected when attacker and victim on same team
- Non-TK (different teams) → no warning
- Count increments, warning sent each time
- Kick at threshold
- New game resets counts
- Missing player in cache → no crash

## Step 6: ServerStatus Plugin

### `plugins/server_status/plugin.py`

```python
class ServerStatus(Plugin):
    name = "Server Status"
    requires = ["rcon", "discord"]
```

- `on_enable()`: init `self._message = None`, `self._tick_rate = 0.0`, `self._current_map = ""`, send initial embed
- `@periodic(seconds=update_interval)` `update_status()`:
  - `players = await self.rcon.list_players()`
  - `current_map = await self.rcon.show_current_map()`
  - `next_map = await self.rcon.show_next_map()`
  - Build embed: map, player count, squad count, next map, tick rate
  - If `self._message`: try `self.discord.edit_message(self._message, embed=embed)`, catch and post new
  - Else: post new message, store reference
- `@on_event("server_tick_rate")`: cache `event.tick_rate`
- `@on_event("new_game")`: cache map info for immediate accuracy
- `on_disable()`: edit embed to "Offline" status

### `config/plugins/server_status.toml.example`

### Tests (`tests/test_plugin_server_status.py`)

- Initial embed posted on enable
- Periodic update edits existing message
- If message deleted, new one posted
- Tick rate and new_game events update cached values
- Disable sets offline status

## Step 7: AdminRequest Plugin

### `plugins/admin_request/plugin.py`

```python
class AdminRequest(Plugin):
    name = "Admin Request"
    requires = ["rcon", "discord"]
```

- `on_enable()`: init `self._tickets: dict[int, dict]` (thread_id -> {steam_id, player_name, claimed_by}), `self._player_cache`
- `@periodic(seconds=30)` `refresh_players()`: update player cache from RCON
- `@on_event("chat_message")` `handle_chat(event)`:
  - If not `event.message.startswith(command_prefix)`: return
  - Extract reason text
  - Build embed: "Admin Request", player name, reason, timestamp
  - Create View with "Claim" button (custom_id `"claim_ticket"`)
  - Send to channel, optional role ping
  - Create thread from message
  - Store ticket info
  - Warn player in-game: "Your admin request has been submitted"
- `@on_discord("button_click", custom_id="claim_ticket")` `handle_claim(interaction)`:
  - Edit embed: add "Claimed by" field, disable button
  - Update ticket info
- `@on_discord("thread_message")` `handle_thread_msg(interaction)`:
  - Look up ticket by thread ID
  - If found and player still online: `rcon.warn(steam_id, "[Admin] {author}: {message}")`

### `config/plugins/admin_request.toml.example`

### Tests (`tests/test_plugin_admin_request.py`)

- Chat message with prefix creates embed + thread
- Non-prefix messages ignored
- Claim button edits embed
- Thread message relays to player via RCON warn
- Player not in cache → no crash

## Step 8: DiscordChatBridge Plugin

### `plugins/discord_chat_bridge/plugin.py`

```python
class DiscordChatBridge(Plugin):
    name = "Discord Chat Bridge"
    requires = ["rcon", "discord"]
```

- `on_enable()`: register `on_message` listener on `self.discord.bot`
- **Game → Discord**: `@on_event("chat_message")` `relay_to_discord(event)`:
  - If `event.channel` not in `chat_channels`: return
  - Format: `[All] **PlayerName**: message` or just `**PlayerName**: message`
  - `await self.discord.send(channel_id, content=formatted)`
- **Discord → Game**: `_on_discord_message(message)` listener:
  - If `message.channel.id != channel_id`: return
  - If `message.author.bot`: return
  - Format: `[Discord] AuthorName: message`
  - `await self.rcon.broadcast(formatted)`
- `on_disable()`: remove listener via `self.discord.bot.remove_listener(self._on_discord_message)`

### `config/plugins/discord_chat_bridge.toml.example`

### Tests (`tests/test_plugin_chat_bridge.py`)

- Game chat in configured channels → Discord send
- Game chat in non-configured channels → no send
- Discord message in bridge channel → RCON broadcast
- Bot messages → ignored (no echo loop)
- Messages in other channels → ignored

## Implementation Order

1. Step 1: RCON types
2. Step 2: RCON convenience methods + tests
3. Step 3: ChatMessage event + server.py parsing + tests
4. Step 4: AutoKickUnassigned + config + tests
5. Step 5: TKWarn + config + tests
6. Step 6: ServerStatus + config + tests
7. Step 7: AdminRequest + config + tests
8. Step 8: DiscordChatBridge + config + tests

Each step is independently committable. Run `pytest tests/ -v` after each step to verify no regressions.
