# Phase 5 Implementation Plan — Built-in Plugins

Reference: `docs/plans/architecture/2026-02-08-phase5-plugins-design.md`
Sample RCON responses: `tests/fixtures/samples/rcon/`

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

@dataclass
class MapInfo:
    level: str           # e.g. "Tallil Outskirts"
    layer: str           # e.g. "SAT_Tallil_Seed_v1"
    factions: str        # e.g. "VDV WPMC" (may be empty)
```

## Step 2: RCON Convenience Methods (`squadpy/rcon/client.py`)

Add parsing functions and convenience methods. Import `parse_online_ids` from `squadpy.log_parser.id_parser`.

### Response Formats (from real RCON samples)

**ListPlayers** — structure:
```
----- Active Players -----
ID: 87 | Online IDs: EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950 | Name: [INAF]  AMIN OPLEN | Team ID: 1 | Squad ID: 1 | Is Leader: False | Role: USA_MachineGunner_01
ID: 4 | Online IDs: EOS: 00026eafb0e34413b5a02ad6db6eb5ab steam: 76561198328202223 | Name:  Eiennein | Team ID: 1 | Squad ID: N/A | Is Leader: False | Role: USA_Rifleman_01
...
----- Recently Disconnected Players [Max of 15] -----
ID: 0 | Online IDs: EOS: 0002b2ce5d254f63821146034328df0e steam: 76561198431814563 | Since Disconnect: 00m.35s | Name:  UpsideDownFloof
```

**Quirks from real data:**
- Header line: `----- Active Players -----` (skip)
- Footer section: `----- Recently Disconnected Players [Max of 15] -----` (stop parsing here)
- Recently disconnected players have DIFFERENT format (`Since Disconnect:` field, no Team/Squad/Role)
- Squad ID can be `N/A` (unassigned players)
- Team ID can be `N/A` (rare, seen during map transitions)
- Role values can have trailing commas (e.g. `WPMC_Rifleman_08,`) — strip them
- Player names can contain `|` characters (e.g. `ɴямʟ |  SkandiaP [TH]`)
- Player names can have leading/trailing spaces (e.g. ` Bondu`, `  Caleb Martin`)
- Player names contain Unicode (clan tags, CJK characters, symbols)
- Names are preserved as-is (don't strip spaces — they're part of the display name)

Regex (uses greedy `.+` for name — backtrack finds the last ` | Team ID:`):
```python
_PLAYER_RE = re.compile(
    r"^ID: (?P<id>\d+) \| Online IDs:(?P<ids>[^|]+)\| Name: (?P<name>.+) \| "
    r"Team ID: (?P<team_id>\d+|N/A) \| Squad ID: (?P<squad_id>\d+|N/A) \| "
    r"Is Leader: (?P<is_leader>True|False) \| Role: (?P<role>.+?)(?:,?)$"
)
```

Note: The `[^|]+` for Online IDs works because EOS/steam IDs don't contain `|`. The `name` field uses `.+` (greedy) which correctly backtracks to the last ` | Team ID:`. The role uses `.+?` with optional trailing comma.

**ListSquads** — structure:
```
----- Active Squads -----
Team ID: 1 (Overwatch 6 Patrol Group)
ID: 1 | Name: Squad 1 | Size: 1 | Locked: True | Creator Name: Arrex | Creator Online IDs: EOS: 0002d52d94444153aa5084c59a43850f steam: 76561198112209427
...
Team ID: 2 (7th Armored Brigade "Saar me-Golan")
ID: 1 | Name: RWS | Size: 1 | Locked: True | Creator Name: Sillychilli <3 | Creator Online IDs: EOS: 000231a3763c417d9d1e16883f5b1e27 steam: 76561199123057630
```

**Quirks from real data:**
- Header: `----- Active Squads -----` (skip)
- Team names can contain quotes and special characters
- Squad IDs can skip numbers (e.g. 8 → 10, no squad 9)
- Creator names can have special characters and spaces

Regexes:
```python
_TEAM_RE = re.compile(r"^Team ID: (?P<team_id>\d+) \((?P<team_name>.+)\)")
_SQUAD_RE = re.compile(
    r"^ID: (?P<id>\d+) \| Name: (?P<name>.+) \| Size: (?P<size>\d+) \| "
    r"Locked: (?P<locked>True|False) \| Creator Name: (?P<creator_name>.+) \| "
    r"Creator Online IDs:(?P<creator_ids>.+)$"
)
```

**ShowCurrentMap** — real format:
```
Current level is Tallil Outskirts, layer is SAT_Tallil_Seed_v1, factions VDV WPMC
```

Note: Has `, factions <faction1> <faction2>` suffix — different from SquadJS which only parses level+layer.

Regex:
```python
_CURRENT_MAP_RE = re.compile(
    r"^Current level is (?P<level>[^,]+), layer is (?P<layer>[^,]+)"
    r"(?:, factions (?P<factions>.+))?$"
)
```

**ShowNextMap** — two variants:
```
# Voting enabled (next map not set):
Next map is not defined

# Voting disabled (next map set):
Next level is Sumari Bala, layer is Sumari_Seed_v1, factions RGF+Support INS
```

Regex + special case:
```python
_NEXT_MAP_RE = re.compile(
    r"^Next level is (?P<level>[^,]+), layer is (?P<layer>[^,]+)"
    r"(?:, factions (?P<factions>.+))?$"
)
# Check "Next map is not defined" first before trying regex
```

### New methods on RconClient

```python
async def list_players(self) -> list[RconPlayer]: ...
async def list_squads(self) -> list[RconSquad]: ...
async def broadcast(self, message: str) -> str: ...
async def warn(self, player_id: str, message: str) -> str: ...
async def kick(self, player_id: str, reason: str) -> str: ...
async def show_current_map(self) -> MapInfo | None: ...
async def show_next_map(self) -> MapInfo | None: ...   # Returns None when "not defined"
```

`warn` and `kick` quote the player_id: `AdminWarn "{id}" {message}`, `AdminKick "{id}" {reason}`.

`show_current_map` and `show_next_map` return `MapInfo` (not raw string) — level, layer, and factions parsed out.

### Tests (`tests/test_rcon_helpers.py`)

Load real sample data from `tests/fixtures/samples/rcon/` for parsing tests:

- Parse ListPlayers Sample 1 (99 active players, 2 unassigned with `N/A`, names with `|` and Unicode, trailing commas in roles)
- Parse ListPlayers Sample 2 (2 active players both unassigned, 1 recently disconnected — verify disconnected section is skipped)
- Parse ListSquads (2 teams, squad IDs skip numbers, various squad names)
- Parse ShowCurrentMap (with factions suffix)
- Parse ShowNextMap — voting enabled (`None` returned)
- Parse ShowNextMap — voting disabled (with factions suffix including `+Support`)
- Test convenience methods call `execute()` with correct command strings (mock execute)
- Empty / malformed responses → empty list, no crash

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

Parse RCON chat packet body format (from SquadJS source):
```
[ChatAll] [Online IDs:EOS: <32hex> steam: <17digits>] PlayerName : message text
```

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
- Player names with special characters parsed correctly

## Step 4: AutoKickUnassigned Plugin

### `plugins/auto_kick_unassigned/plugin.py`

```python
class AutoKickUnassigned(Plugin):
    name = "Auto Kick Unassigned"
    requires = ["rcon"]
```

- `on_enable()`: init `self._warnings: dict[str, int]` (steam_id -> count)
- `@periodic(seconds=30)` `check_unassigned()`:
  - `players = await self.rcon.list_players()`
  - If `len(players) < min_players`: clear warnings, return
  - Build set of currently assigned steam_ids
  - Remove tracking for players now in a squad
  - For each player with `squad_id == 0`:
    - Increment warning count
    - `await self.rcon.warn(steam_id, warning_message)`
    - If count >= `warnings_before_kick`: `await self.rcon.kick(steam_id, kick_message)`
- `@on_event("new_game")`: clear warnings

### `config/plugins/auto_kick_unassigned.toml.example`

```toml
enabled = true

[settings]
warnings_before_kick = 3
min_players = 20
warning_message = "Please join a squad or you will be kicked"
kick_message = "Kicked for not joining a squad"
```

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

```toml
enabled = true

[settings]
kick_threshold = 5
warning_message = "Team kill #{count} recorded. {threshold} = kick."
kick_message = "Kicked for excessive teamkills ({count})"
```

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

- `on_enable()`: init `self._message = None`, `self._tick_rate = 0.0`, send initial embed
- `@periodic(seconds=60)` `update_status()`:
  - `players = await self.rcon.list_players()`
  - `current_map = await self.rcon.show_current_map()`
  - `next_map = await self.rcon.show_next_map()`
  - Build embed: map/layer, factions, player count, squad count, next map, tick rate
  - If `self._message`: try `self.discord.edit_message(self._message, embed=embed)`, catch and post new
  - Else: post new message, store reference
- `@on_event("server_tick_rate")`: cache `event.tick_rate`
- `@on_event("new_game")`: cache map info for immediate accuracy
- `on_disable()`: edit embed to "Offline" status

### `config/plugins/server_status.toml.example`

```toml
enabled = true

[settings]
channel_id = 0
update_interval = 60
```

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
  - If `event.message` doesn't start with command_prefix trigger word: return
  - Extract reason text (everything after prefix)
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

```toml
enabled = true

[settings]
channel_id = 0
ping_role_id = 0
command_prefix = "!admin"
```

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

```toml
enabled = true

[settings]
channel_id = 0
chat_channels = ["ChatAll"]
show_channel_prefix = true
discord_to_game_format = "[Discord] {author}: {message}"
```

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
