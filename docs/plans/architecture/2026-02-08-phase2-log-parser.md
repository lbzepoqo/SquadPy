# Phase 2 — Log Parser Design

## Overview

Add log parsing to SquadPy: tail Squad server logs (local or SFTP), match lines
against regex patterns, correlate multi-line events via an event store, and emit
typed events into the existing event bus.

## Module Structure

```
squadpy/log_parser/
├── __init__.py          # Public exports
├── reader.py            # Abstract LogReader ABC
├── local.py             # Local file tail (async)
├── sftp.py              # SFTP remote reader (asyncssh)
├── parser.py            # LogParser — regex matching, state, event emission
├── patterns.py          # All regex rules (one per event type)
└── id_parser.py         # Online ID parsing utility (Steam/EOS extraction)
```

## Log Reader Abstraction

```python
class LogReader(ABC):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def tail(self) -> AsyncIterator[str]: ...
```

- **LocalLogReader** — async file polling, seeks to end on startup, configurable
  poll interval (default 1s).
- **SFTPLogReader** — connects via `asyncssh`, periodically downloads new bytes,
  yields new lines. Configurable poll interval.

## Log Parser

Central coordinator between reader and event bus:

1. Consumes lines from a `LogReader`
2. Matches each line against an ordered list of regex rules (first match wins)
3. Manages the `EventStore` for cross-line correlation
4. Emits typed `BaseEvent` subclasses into the `EventBus`

```python
class LogParser:
    def __init__(self, reader: LogReader, event_bus: EventBus):
        self.reader = reader
        self.event_bus = event_bus
        self.event_store = EventStore()
        self.rules = get_rules()

    async def run(self) -> None:
        async for line in self.reader.tail():
            for rule in self.rules:
                match = rule.regex.match(line)
                if match:
                    event = rule.on_match(match, self.event_store)
                    if event:
                        await self.event_bus.emit(event)
                    break
```

## Event Store

Mutable state for correlating events across log lines (mirrors SquadJS eventStore):

```python
class EventStore:
    session: dict[str, Any]        # wound/damage correlation by player name
    players: dict[str, Any]        # player info by EOS ID
    join_requests: dict[int, Any]  # pending joins by chain ID
    disconnected: dict[str, bool]  # recently disconnected EOS IDs
    round_winner: dict | None      # held until ROUND_ENDED emits
    round_loser: dict | None

    def clear(self) -> None:       # called on NEW_GAME
```

## Event Dataclasses

All events inherit `BaseEvent`. Player identity uses a shared model:

```python
@dataclass
class PlayerID:
    steam_id: str = ""
    eos_id: str = ""
    name: str = ""
    controller: str = ""
```

### Full Event Set (15 events, matching SquadJS parity)

| Event | Key Fields | Notes |
|-------|-----------|-------|
| PlayerConnected | player_id, ip, chain_id | From PostLogin log line |
| JoinSucceeded | player_id, chain_id | Consumes join_requests from store |
| PlayerDisconnected | player_id, ip, chain_id | Marks EOS ID as disconnected in store |
| PlayerDamaged | victim_name, attacker (PlayerID), damage, weapon | Stores in session for correlation |
| PlayerWounded | victim_name, attacker (PlayerID), damage, weapon | Spreads correlated data from store |
| PlayerDied | victim_name, attacker (PlayerID), damage, weapon | Spreads correlated data from store |
| PlayerRevived | reviver (PlayerID), victim (PlayerID) | |
| PlayerPossess | player_id, possess_classname | Stores chain ID in session |
| PlayerUnpossess | player_id, switch_possess (bool) | |
| NewGame | dlc, map_classname, layer_classname | Clears event store |
| RoundEnded | winner, loser (nullable — draws) | Consumes stored winner/loser |
| RoundTickets | team, subfaction, faction, action, tickets, layer, level | Stores in event_store, not emitted |
| RoundWinner | winner, layer | Stores in event_store, not emitted |
| ServerTickRate | tick_rate (float) | |
| AdminBroadcast | message, from_player | |
| DeployableDamaged | deployable, damage, weapon, player_suffix, damage_type, health_remaining | |

Notes:
- RoundWinner and RoundTickets update the store but don't emit — RoundEnded consumes them
- Combat events spread correlated attacker data from the session store
- PlayerID fields populated via id_parser from `Online IDs:` strings

## ID Parser

Extracts platform IDs from Squad's `Online IDs:` format:

```
Online IDs: EOS: abc123def Steam: 76561198012345678
```

```python
def parse_online_ids(raw: str) -> dict[str, str]:
    """Returns {"eos_id": "abc123def", "steam_id": "76561198012345678"}"""
```

## Config

Add `[log]` section to `ServerConfig`:

```python
class LogConfig(BaseModel):
    enabled: bool = False
    mode: Literal["local", "sftp"] = "local"
    path: str = ""
    poll_interval: float = 1.0

    # SFTP-only
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
```

`server.toml.example`:

```toml
[log]
enabled = true
mode = "local"
path = "/path/to/SquadGame/SquadGame.log"
poll_interval = 1.0
```

## Server Integration

Startup sequence gains a log reader step between RCON and plugin loading:

1. Connect RCON
2. **Start log reader + parser** (if `log.enabled`) — create reader, wrap in
   LogParser, start `parser.run()` as background asyncio.Task
3. Register `"log_reader"` in services dict
4. Load plugins
5. Startup summary shows Log Reader status

Parser task cancelled during shutdown between stopping periodic tasks and
disabling plugins.

## Testing

| Test File | Coverage |
|-----------|----------|
| test_patterns.py | One test per regex rule with real Squad log lines |
| test_id_parser.py | ID parser edge cases (single/both platforms, INVALID) |
| test_event_store.py | Correlation chains (damage→wound→die, join→succeed, tickets→round_ended) |
| test_log_parser.py | Integration: feed log lines, verify events via mock EventBus |
| test_local_reader.py | Local tail with temp file, startup seek-to-end |
| test_config.py | Extend for LogConfig validation |

No SFTP tests (needs mock SSH server — deferred). Reader abstraction allows
testing everything else with local reader or direct line feeding.
