# Phase 2: Log Parser Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add log parsing to SquadPy — tail Squad server logs, match lines against regex patterns, correlate multi-line events, and emit typed events into the event bus.

**Architecture:** LogReader (local/SFTP) tails log files and yields lines. LogParser runs each line through ordered regex rules, manages an EventStore for cross-line correlation, and emits typed BaseEvent subclasses into the existing EventBus.

**Tech Stack:** Python 3.12+, asyncio, re, dataclasses, Pydantic, asyncssh (SFTP), pytest-asyncio

---

### Task 1: ID Parser Utility

**Files:**
- Create: `squadpy/log_parser/id_parser.py`
- Test: `tests/test_id_parser.py`

**Step 1: Write the failing tests**

```python
"""Tests for Online ID parsing utility."""

from squadpy.log_parser.id_parser import parse_online_ids


class TestParseOnlineIds:
    def test_both_eos_and_steam(self):
        raw = "EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392"
        result = parse_online_ids(raw)
        assert result == {
            "eos_id": "000250f5e359453bb9ad313db051f19e",
            "steam_id": "76561198376713392",
        }

    def test_eos_only(self):
        raw = "EOS: 000250f5e359453bb9ad313db051f19e"
        result = parse_online_ids(raw)
        assert result == {
            "eos_id": "000250f5e359453bb9ad313db051f19e",
            "steam_id": "",
        }

    def test_invalid_returns_empty(self):
        raw = "INVALID"
        result = parse_online_ids(raw)
        assert result == {"eos_id": "", "steam_id": ""}

    def test_empty_string(self):
        raw = ""
        result = parse_online_ids(raw)
        assert result == {"eos_id": "", "steam_id": ""}

    def test_with_pipe_separator(self):
        """Online IDs sometimes appear with pipe before Controller ID."""
        raw = "EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 "
        result = parse_online_ids(raw)
        assert result["eos_id"] == "0002ded45cb5412e8d5c7833a92d36b3"
        assert result["steam_id"] == "76561198376630934"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_id_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
"""Utility for parsing Squad Online IDs (EOS + Steam) from log lines."""

import re

_EOS_RE = re.compile(r"EOS:\s*([0-9a-f]{32})")
_STEAM_RE = re.compile(r"steam:\s*(\d{17})")


def parse_online_ids(raw: str) -> dict[str, str]:
    """Parse an Online IDs string into eos_id and steam_id.

    Input format: 'EOS: <32hex> steam: <17digits>'
    Returns: {'eos_id': '...', 'steam_id': '...'}
    Missing IDs default to empty string.
    """
    eos_match = _EOS_RE.search(raw)
    steam_match = _STEAM_RE.search(raw)
    return {
        "eos_id": eos_match.group(1) if eos_match else "",
        "steam_id": steam_match.group(1) if steam_match else "",
    }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_id_parser.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/id_parser.py tests/test_id_parser.py
git commit -m "feat(log_parser): add Online ID parser utility (EOS + Steam)"
```

---

### Task 2: Event Dataclasses

**Files:**
- Modify: `squadpy/events/types.py`
- Test: `tests/test_log_events.py`

**Step 1: Write the failing tests**

```python
"""Tests for log parser event dataclasses."""

from squadpy.events.types import (
    PlayerID,
    PlayerConnected,
    PlayerDisconnected,
    JoinSucceeded,
    PlayerDamaged,
    PlayerWounded,
    PlayerDied,
    PlayerRevived,
    PlayerPossess,
    PlayerUnpossess,
    NewGame,
    RoundEnded,
    RoundTickets,
    ServerTickRate,
    AdminBroadcast,
    DeployableDamaged,
)


class TestPlayerID:
    def test_defaults(self):
        pid = PlayerID()
        assert pid.steam_id == ""
        assert pid.eos_id == ""
        assert pid.name == ""
        assert pid.controller == ""


class TestPlayerConnected:
    def test_event_name(self):
        e = PlayerConnected()
        assert e.event_name == "player_connected"

    def test_fields(self):
        pid = PlayerID(eos_id="abc", steam_id="123", name="Test")
        e = PlayerConnected(player=pid, ip="1.2.3.4", chain_id=42)
        assert e.player.eos_id == "abc"
        assert e.ip == "1.2.3.4"
        assert e.chain_id == 42


class TestPlayerDied:
    def test_event_name(self):
        e = PlayerDied()
        assert e.event_name == "player_died"

    def test_fields(self):
        attacker = PlayerID(eos_id="atk", steam_id="456")
        e = PlayerDied(
            victim_name="victim",
            damage=300.0,
            attacker=attacker,
            weapon="BP_Frag_C",
        )
        assert e.victim_name == "victim"
        assert e.attacker.eos_id == "atk"
        assert e.weapon == "BP_Frag_C"


class TestRoundEnded:
    def test_draw(self):
        e = RoundEnded()
        assert e.winner is None
        assert e.loser is None


class TestDeployableDamaged:
    def test_event_name(self):
        e = DeployableDamaged()
        assert e.event_name == "deployable_damaged"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_log_events.py -v`
Expected: FAIL with `ImportError`

**Step 3: Write the implementation**

Add to `squadpy/events/types.py` (keep existing `BaseEvent`):

```python
"""Base event type and core event definitions."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BaseEvent:
    """Base class for all SquadPy events."""
    event_name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# --- Shared models ---

@dataclass
class PlayerID:
    """Player identity across platforms."""
    steam_id: str = ""
    eos_id: str = ""
    name: str = ""
    controller: str = ""


# --- Log parser events ---

@dataclass
class PlayerConnected(BaseEvent):
    event_name: str = "player_connected"
    player: PlayerID = field(default_factory=PlayerID)
    ip: str = ""
    chain_id: int = 0
    controller_name: str = ""


@dataclass
class JoinSucceeded(BaseEvent):
    event_name: str = "join_succeeded"
    player: PlayerID = field(default_factory=PlayerID)
    chain_id: int = 0
    player_suffix: str = ""


@dataclass
class PlayerDisconnected(BaseEvent):
    event_name: str = "player_disconnected"
    player: PlayerID = field(default_factory=PlayerID)
    ip: str = ""
    controller_name: str = ""


@dataclass
class PlayerDamaged(BaseEvent):
    event_name: str = "player_damaged"
    victim_name: str = ""
    damage: float = 0.0
    attacker: PlayerID = field(default_factory=PlayerID)
    weapon: str = ""


@dataclass
class PlayerWounded(BaseEvent):
    event_name: str = "player_wounded"
    victim_name: str = ""
    damage: float = 0.0
    attacker: PlayerID = field(default_factory=PlayerID)
    weapon: str = ""


@dataclass
class PlayerDied(BaseEvent):
    event_name: str = "player_died"
    victim_name: str = ""
    damage: float = 0.0
    attacker: PlayerID = field(default_factory=PlayerID)
    weapon: str = ""


@dataclass
class PlayerRevived(BaseEvent):
    event_name: str = "player_revived"
    reviver: PlayerID = field(default_factory=PlayerID)
    victim: PlayerID = field(default_factory=PlayerID)


@dataclass
class PlayerPossess(BaseEvent):
    event_name: str = "player_possess"
    player: PlayerID = field(default_factory=PlayerID)
    possess_classname: str = ""


@dataclass
class PlayerUnpossess(BaseEvent):
    event_name: str = "player_unpossess"
    player: PlayerID = field(default_factory=PlayerID)
    health: float = 0.0
    exited_vehicle: bool = False
    vehicle_name: str = ""
    seat_number: int = -1


@dataclass
class NewGame(BaseEvent):
    event_name: str = "new_game"
    dlc: str = ""
    map_classname: str = ""
    layer_classname: str = ""
    winner: dict[str, Any] | None = None


@dataclass
class RoundEnded(BaseEvent):
    event_name: str = "round_ended"
    winner: dict[str, Any] | None = None
    loser: dict[str, Any] | None = None


@dataclass
class RoundTickets(BaseEvent):
    """Stored in EventStore, not emitted directly."""
    event_name: str = "round_tickets"
    team: str = ""
    subfaction: str = ""
    faction: str = ""
    action: str = ""
    tickets: int = 0
    layer: str = ""
    level: str = ""


@dataclass
class ServerTickRate(BaseEvent):
    event_name: str = "server_tick_rate"
    tick_rate: float = 0.0


@dataclass
class AdminBroadcast(BaseEvent):
    event_name: str = "admin_broadcast"
    message: str = ""
    from_player: str = ""


@dataclass
class DeployableDamaged(BaseEvent):
    event_name: str = "deployable_damaged"
    deployable: str = ""
    damage: float = 0.0
    damage_source: str = ""
    damage_type: str = ""
    direct_hit: bool = False
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_log_events.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/events/types.py tests/test_log_events.py
git commit -m "feat(events): add all log parser event dataclasses"
```

---

### Task 3: LogConfig and server.toml.example

**Files:**
- Modify: `squadpy/config.py` (add `LogConfig`, update `ServerConfig`)
- Modify: `config/server.toml.example`
- Modify: `tests/test_config.py`

**Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
from squadpy.config import ServerConfig, LoggingConfig, LogConfig, load_config


class TestLogConfig:
    def test_defaults(self):
        config = LogConfig()
        assert config.enabled is False
        assert config.mode == "local"
        assert config.path == ""
        assert config.poll_interval == 1.0

    def test_local_mode(self):
        config = LogConfig(enabled=True, mode="local", path="/var/log/squad/SquadGame.log")
        assert config.enabled is True
        assert config.path == "/var/log/squad/SquadGame.log"

    def test_sftp_mode(self):
        config = LogConfig(
            enabled=True, mode="sftp", path="/logs/SquadGame.log",
            host="10.0.0.1", port=22, username="squad", password="pass",
        )
        assert config.mode == "sftp"
        assert config.host == "10.0.0.1"

    def test_invalid_mode_raises(self):
        with pytest.raises(Exception):
            LogConfig(mode="ftp")

    def test_invalid_poll_interval_raises(self):
        with pytest.raises(Exception):
            LogConfig(poll_interval=0)


class TestServerConfigWithLog:
    def test_log_is_optional(self):
        config = ServerConfig(rcon={"host": "127.0.0.1", "password": "pass"})
        assert config.log.enabled is False

    def test_log_section_parsed(self):
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "pass"},
            log={"enabled": True, "mode": "local", "path": "/tmp/SquadGame.log"},
        )
        assert config.log.enabled is True
        assert config.log.path == "/tmp/SquadGame.log"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py::TestLogConfig -v`
Expected: FAIL with `ImportError`

**Step 3: Write the implementation**

Add to `squadpy/config.py` before `ServerConfig`:

```python
class LogConfig(BaseModel):
    enabled: bool = False
    mode: Literal["local", "sftp"] = "local"
    path: str = ""
    poll_interval: float = 1.0
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""

    @field_validator("poll_interval")
    @classmethod
    def validate_poll_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"poll_interval must be positive, got {v}")
        return v
```

Update `ServerConfig`:

```python
class ServerConfig(BaseModel):
    rcon: RconConfig
    log: LogConfig = LogConfig()
```

Update `config/server.toml.example` to add `[log]` section:

```toml
[rcon]
host = "127.0.0.1"
port = 21114
password = "your_rcon_password"

[log]
# enabled = true
# mode = "local"                               # "local" or "sftp"
# path = "/path/to/SquadGame/SquadGame.log"    # log file path
# poll_interval = 1.0                          # seconds between checks

# SFTP settings (only used when mode = "sftp")
# host = "192.168.1.10"
# port = 22
# username = "squad"
# password = "your_sftp_password"
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All PASS (new and existing)

**Step 5: Commit**

```
git add squadpy/config.py config/server.toml.example tests/test_config.py
git commit -m "feat(config): add LogConfig with local/sftp mode support"
```

---

### Task 4: EventStore

**Files:**
- Create: `squadpy/log_parser/event_store.py`
- Test: `tests/test_event_store.py`

**Step 1: Write the failing tests**

```python
"""Tests for the EventStore cross-line correlation state."""

from squadpy.log_parser.event_store import EventStore


class TestEventStore:
    def test_initial_state(self):
        store = EventStore()
        assert store.session == {}
        assert store.players == {}
        assert store.join_requests == {}
        assert store.disconnected == {}
        assert store.round_winner is None
        assert store.round_loser is None

    def test_clear_resets_all(self):
        store = EventStore()
        store.session["test"] = {"data": 1}
        store.players["eos123"] = {"name": "Player"}
        store.join_requests[42] = {"ip": "1.2.3.4"}
        store.disconnected["eos123"] = True
        store.round_winner = {"team": "1"}
        store.round_loser = {"team": "2"}
        store.clear()
        assert store.session == {}
        assert store.players == {}
        assert store.join_requests == {}
        assert store.disconnected == {}
        assert store.round_winner is None
        assert store.round_loser is None

    def test_session_stores_damage_correlation(self):
        store = EventStore()
        store.session["VictimName"] = {
            "attacker_eos_id": "abc",
            "weapon": "BP_Frag_C",
        }
        assert store.session["VictimName"]["weapon"] == "BP_Frag_C"

    def test_join_request_by_chain_id(self):
        store = EventStore()
        store.join_requests[401] = {
            "controller_name": "BP_PlayerController_C_123",
            "ip": "1.2.3.4",
            "eos_id": "abc",
            "steam_id": "123",
        }
        player = store.join_requests.pop(401)
        assert player["eos_id"] == "abc"
        assert 401 not in store.join_requests

    def test_round_tickets_storage(self):
        store = EventStore()
        store.round_winner = {"team": "1", "subfaction": "MEA", "tickets": 50}
        store.round_loser = {"team": "2", "subfaction": "USA", "tickets": 0}
        assert store.round_winner["tickets"] == 50
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_event_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
"""EventStore for cross-line correlation state during log parsing."""

from typing import Any


class EventStore:
    """Mutable state for correlating events across multiple log lines.

    Mirrors the SquadJS eventStore pattern:
    - session: damage/wound correlation by player name
    - players: player info by EOS ID
    - join_requests: pending joins by chain ID (consumed by JoinSucceeded)
    - disconnected: recently disconnected EOS IDs
    - round_winner/round_loser: held until RoundEnded emits them
    """

    def __init__(self):
        self.session: dict[str, Any] = {}
        self.players: dict[str, Any] = {}
        self.join_requests: dict[int, Any] = {}
        self.disconnected: dict[str, bool] = {}
        self.round_winner: dict[str, Any] | None = None
        self.round_loser: dict[str, Any] | None = None

    def clear(self) -> None:
        """Reset all state. Called on NEW_GAME."""
        self.session.clear()
        self.players.clear()
        self.join_requests.clear()
        self.disconnected.clear()
        self.round_winner = None
        self.round_loser = None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_event_store.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/event_store.py tests/test_event_store.py
git commit -m "feat(log_parser): add EventStore for cross-line correlation"
```

---

### Task 5: Regex Patterns — Part A (Connection Events)

**Files:**
- Create: `squadpy/log_parser/patterns.py`
- Test: `tests/test_patterns.py`

These tests use real log lines from the sample files. Player IPs and Steam IDs in the test fixtures are from the sample data — this is fine since the test file is committed but the raw logs are gitignored.

**Step 1: Write the failing tests**

```python
"""Tests for Squad log line regex patterns."""

from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import get_rules, match_line
from squadpy.events.types import (
    PlayerConnected, JoinSucceeded, PlayerDisconnected,
)


class TestPlayerConnected:
    def test_vanilla_postlogin(self):
        line = '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerConnected)
        assert event.player.eos_id == "000250f5e359453bb9ad313db051f19e"
        assert event.player.steam_id == "76561198376713392"
        assert event.ip == "174.110.37.249"
        assert event.chain_id == 401

    def test_modded_postlogin(self):
        line = '[2026.02.02-02.40.04:646][926]LogSquad: PostLogin: NewPlayer: BP_PlayerController_SATSeed_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_PlayerController_SATSeed_C_2147480511 (IP: 61.245.141.66 | Online IDs: EOS: 000234112f50474f82d740a777a6b2d0 steam: 76561198375634826)'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerConnected)
        assert event.player.eos_id == "000234112f50474f82d740a777a6b2d0"
        assert event.chain_id == 926

    def test_stores_join_request(self):
        line = '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)'
        store = EventStore()
        match_line(line, store)
        assert 401 in store.join_requests
        assert store.join_requests[401]["eos_id"] == "000250f5e359453bb9ad313db051f19e"


class TestJoinSucceeded:
    def test_basic(self):
        # First, set up a join request in the store
        store = EventStore()
        store.join_requests[401] = {
            "controller_name": "BP_PlayerController_C_2147476661",
            "ip": "174.110.37.249",
            "eos_id": "000250f5e359453bb9ad313db051f19e",
            "steam_id": "76561198376713392",
        }
        line = '[2026.02.06-15.02.11:099][401]LogNet: Join succeeded: PAPA_ Ξ_TAN'
        event = match_line(line, store)
        assert isinstance(event, JoinSucceeded)
        assert event.player_suffix == "PAPA_ Ξ_TAN"
        assert event.player.eos_id == "000250f5e359453bb9ad313db051f19e"
        assert event.chain_id == 401

    def test_consumes_join_request(self):
        store = EventStore()
        store.join_requests[712] = {"eos_id": "abc", "steam_id": "123", "ip": "1.1.1.1", "controller_name": "x"}
        line = '[2026.02.06-15.02.15:974][712]LogNet: Join succeeded: Uɴɴ. Gunrunner'
        match_line(line, store)
        assert 712 not in store.join_requests


class TestPlayerDisconnected:
    def test_vanilla(self):
        line = '[2026.02.06-16.07.47:345][330]LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 174.110.37.249:58734, Name: RedpointEOSIpNetConnection_2147476691, Driver: Name:GameNetDriver Def:GameNetDriver RedpointEOSNetDriver_2147482413, IsServer: YES, PC: BP_PlayerController_C_2147476661, Owner: BP_PlayerController_C_2147476661, UniqueId: RedpointEOS:000250f5e359453bb9ad313db051f19e'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDisconnected)
        assert event.player.eos_id == "000250f5e359453bb9ad313db051f19e"
        assert event.ip == "174.110.37.249"
        assert event.controller_name == "BP_PlayerController_C_2147476661"

    def test_marks_disconnected_in_store(self):
        line = '[2026.02.06-16.07.47:345][330]LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 174.110.37.249:58734, Name: RedpointEOSIpNetConnection_2147476691, Driver: Name:GameNetDriver Def:GameNetDriver RedpointEOSNetDriver_2147482413, IsServer: YES, PC: BP_PlayerController_C_2147476661, Owner: BP_PlayerController_C_2147476661, UniqueId: RedpointEOS:000250f5e359453bb9ad313db051f19e'
        store = EventStore()
        match_line(line, store)
        assert store.disconnected["000250f5e359453bb9ad313db051f19e"] is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_patterns.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `squadpy/log_parser/patterns.py`:

```python
"""Squad server log regex patterns and match handlers.

Each rule is a (compiled_regex, handler_function) pair.
Handler signature: (match, chain_id, timestamp_str, event_store) -> BaseEvent | None
"""

import re
from dataclasses import dataclass
from typing import Any, Callable

from squadpy.events.types import (
    BaseEvent, PlayerID, PlayerConnected, JoinSucceeded, PlayerDisconnected,
    PlayerDamaged, PlayerWounded, PlayerDied, PlayerRevived,
    PlayerPossess, PlayerUnpossess, NewGame, RoundEnded, RoundTickets,
    ServerTickRate, AdminBroadcast, DeployableDamaged,
)
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.id_parser import parse_online_ids

# Common prefix: [timestamp][chain_id]
_PREFIX = r"^\[([0-9.:-]+)\]\[([ 0-9]*)\]"

MatchHandler = Callable[[re.Match, int, str, EventStore], BaseEvent | None]


@dataclass
class Rule:
    regex: re.Pattern
    handler: MatchHandler


def _parse_chain_id(raw: str) -> int:
    """Parse chain ID from log prefix, handling spaces."""
    stripped = raw.strip()
    return int(stripped) if stripped else 0


def match_line(line: str, store: EventStore) -> BaseEvent | None:
    """Match a log line against all rules, return event or None."""
    for rule in get_rules():
        m = rule.regex.match(line)
        if m:
            time_str = m.group(1)
            chain_id = _parse_chain_id(m.group(2))
            return rule.handler(m, chain_id, time_str, store)
    return None


# --- Connection events ---

_PLAYER_CONNECTED_RE = re.compile(
    _PREFIX + r"LogSquad: PostLogin: NewPlayer: .+\.([^\s]+) \(IP: ([\d.]+) \| Online IDs: ([^)]+)\)"
)

def _on_player_connected(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerConnected:
    controller_name = m.group(3)
    ip = m.group(4)
    ids = parse_online_ids(m.group(5))
    player = PlayerID(
        eos_id=ids["eos_id"],
        steam_id=ids["steam_id"],
        controller=controller_name,
    )
    store.join_requests[chain_id] = {
        "controller_name": controller_name,
        "ip": ip,
        "eos_id": ids["eos_id"],
        "steam_id": ids["steam_id"],
    }
    store.players[ids["eos_id"]] = {
        "controller_name": controller_name,
        "ip": ip,
        "eos_id": ids["eos_id"],
        "steam_id": ids["steam_id"],
    }
    if ids["eos_id"] in store.disconnected:
        del store.disconnected[ids["eos_id"]]
    return PlayerConnected(player=player, ip=ip, chain_id=chain_id, controller_name=controller_name)


_JOIN_SUCCEEDED_RE = re.compile(
    _PREFIX + r"LogNet: Join succeeded: (.+)"
)

def _on_join_succeeded(m: re.Match, chain_id: int, time: str, store: EventStore) -> JoinSucceeded:
    player_suffix = m.group(3)
    player_data = store.join_requests.pop(chain_id, {})
    player = PlayerID(
        eos_id=player_data.get("eos_id", ""),
        steam_id=player_data.get("steam_id", ""),
        name=player_suffix,
        controller=player_data.get("controller_name", ""),
    )
    return JoinSucceeded(player=player, chain_id=chain_id, player_suffix=player_suffix)


_PLAYER_DISCONNECTED_RE = re.compile(
    _PREFIX + r"LogNet: UChannel::Close: Sending CloseBunch\..+RemoteAddr: ([\d.]+):\d+,.+PC: ([^ ,]+),.+UniqueId: RedpointEOS:([0-9a-f]+)"
)

def _on_player_disconnected(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerDisconnected:
    ip = m.group(3)
    controller_name = m.group(4)
    eos_id = m.group(5)
    store.disconnected[eos_id] = True
    player = PlayerID(eos_id=eos_id, controller=controller_name)
    return PlayerDisconnected(player=player, ip=ip, controller_name=controller_name)


def get_rules() -> list[Rule]:
    """Return ordered list of all log parsing rules."""
    return [
        Rule(_PLAYER_CONNECTED_RE, _on_player_connected),
        Rule(_JOIN_SUCCEEDED_RE, _on_join_succeeded),
        Rule(_PLAYER_DISCONNECTED_RE, _on_player_disconnected),
    ]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_patterns.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/patterns.py tests/test_patterns.py
git commit -m "feat(log_parser): add regex patterns for connection events"
```

---

### Task 6: Regex Patterns — Part B (Combat Events)

**Files:**
- Modify: `squadpy/log_parser/patterns.py`
- Modify: `tests/test_patterns.py`

**Step 1: Add failing tests**

Append to `tests/test_patterns.py`:

```python
from squadpy.events.types import PlayerDamaged, PlayerWounded, PlayerDied, PlayerRevived


class TestPlayerDamaged:
    def test_with_attacker(self):
        line = '[2026.02.06-16.57.06:079][ 49]LogSquad: Player: enwez ActualDamage=58.952755 from  lord billybean (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Player Controller ID: BP_PlayerController_C_2147285821)caused by BP_KBA3_HEAT_C_2147362075'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDamaged)
        assert event.victim_name == "enwez"
        assert event.damage == 58.952755
        assert event.attacker.eos_id == "0002ded45cb5412e8d5c7833a92d36b3"
        assert event.weapon == "BP_KBA3_HEAT_C"

    def test_self_damage(self):
        line = '[2026.02.06-16.41.00:573][464]LogSquad: Player: Uɴɴ. Gunrunner ActualDamage=72.000000 from nullptr (Online IDs: INVALID | Player Controller ID: None)caused by BP_Projectile_7_62mm_C_2147303529'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDamaged)
        assert event.attacker.eos_id == ""
        assert event.victim_name == "Uɴɴ. Gunrunner"

    def test_stores_in_session(self):
        line = '[2026.02.06-16.57.06:079][ 49]LogSquad: Player: enwez ActualDamage=58.952755 from  lord billybean (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Player Controller ID: BP_PlayerController_C_2147285821)caused by BP_KBA3_HEAT_C_2147362075'
        store = EventStore()
        match_line(line, store)
        assert "enwez" in store.session


class TestPlayerWounded:
    def test_with_attacker(self):
        line = '[2026.02.06-16.57.19:764][922]LogSquadTrace: [DedicatedServer]Wound(): Player: enwez KillingDamage=37.075439 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Controller ID: BP_PlayerController_C_2147285821) caused by BP_KBA3_HEAT_C_2147362075'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerWounded)
        assert event.victim_name == "enwez"
        assert event.damage == 37.075439
        assert event.attacker.eos_id == "0002ded45cb5412e8d5c7833a92d36b3"
        assert event.weapon == "BP_KBA3_HEAT_C"

    def test_nullptr_attacker(self):
        line = '[2026.02.06-16.41.37:573][824]LogSquadTrace: [DedicatedServer]Wound(): Player: Uɴɴ. Gunrunner KillingDamage=71.000000 from nullptr (Online IDs: INVALID | Controller ID: None) caused by BP_Projectile_7_62mm_C_2147300368'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerWounded)
        assert event.attacker.eos_id == ""


class TestPlayerDied:
    def test_with_attacker(self):
        line = '[2026.02.06-16.57.23:024][130]LogSquadTrace: [DedicatedServer]Die(): Player: enwez KillingDamage=-300.000000 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Contoller ID: BP_PlayerController_C_2147285821) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147279843'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDied)
        assert event.victim_name == "enwez"
        assert event.attacker.eos_id == "0002ded45cb5412e8d5c7833a92d36b3"

    def test_nullptr_attacker(self):
        line = '[2026.02.06-16.41.39:656][957]LogSquadTrace: [DedicatedServer]Die(): Player: Uɴɴ. Gunrunner KillingDamage=-300.000000 from nullptr (Online IDs: INVALID | Contoller ID: None) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147305683'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDied)
        assert event.attacker.eos_id == ""

    def test_correlates_with_prior_damage(self):
        store = EventStore()
        store.session["enwez"] = {
            "attacker_eos_id": "0002ded45cb5412e8d5c7833a92d36b3",
            "attacker_steam_id": "76561198376630934",
            "weapon": "BP_KBA3_HEAT_C",
        }
        line = '[2026.02.06-16.57.23:024][130]LogSquadTrace: [DedicatedServer]Die(): Player: enwez KillingDamage=-300.000000 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Contoller ID: BP_PlayerController_C_2147285821) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147279843'
        event = match_line(line, store)
        assert isinstance(event, PlayerDied)


class TestPlayerRevived:
    def test_revive(self):
        line = '[2026.02.06-19.15.02:917][959]LogSquad:  Uɴɴ. MegaDeth (Online IDs: EOS: 00026d000720444fb2f4328f9164e9d0 steam: 76561197982173556) has revived Uɴɴ.✘ Sith Lord Grogu (Online IDs: EOS: 0002677dbc8e4269b108f244a38029e5 steam: 76561198128476165).'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerRevived)
        assert event.reviver.eos_id == "00026d000720444fb2f4328f9164e9d0"
        assert event.reviver.name == "Uɴɴ. MegaDeth"
        assert event.victim.eos_id == "0002677dbc8e4269b108f244a38029e5"
        assert event.victim.name == "Uɴɴ.✘ Sith Lord Grogu"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_patterns.py::TestPlayerDamaged -v`
Expected: FAIL

**Step 3: Add combat patterns to `squadpy/log_parser/patterns.py`**

Add these regex patterns and handlers, then add them to `get_rules()`:

```python
# --- Combat events ---

_PLAYER_DAMAGED_RE = re.compile(
    _PREFIX + r"LogSquad: Player: (.+) ActualDamage=([0-9.]+) from (.+) \(Online IDs: ([^|]+)\| Player Controller ID: ([^)]+)\)caused by ([A-Za-z0-9_-]+)_C_\d+"
)

def _on_player_damaged(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerDamaged:
    victim_name = m.group(3)
    damage = float(m.group(4))
    ids = parse_online_ids(m.group(6))
    attacker_controller = m.group(7).strip()
    weapon_raw = m.group(8)
    attacker = PlayerID(
        eos_id=ids["eos_id"],
        steam_id=ids["steam_id"],
        name=m.group(5).strip(),
        controller=attacker_controller,
    )
    store.session[victim_name] = {
        "attacker_eos_id": ids["eos_id"],
        "attacker_steam_id": ids["steam_id"],
        "attacker_controller": attacker_controller,
        "weapon": weapon_raw,
    }
    if ids["eos_id"]:
        store.players.setdefault(ids["eos_id"], {})["controller"] = attacker_controller
    return PlayerDamaged(victim_name=victim_name, damage=damage, attacker=attacker, weapon=weapon_raw)


_PLAYER_WOUNDED_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\]Wound\(\): Player:(.+) KillingDamage=(?:-)*([0-9.]+) from ([A-Za-z_0-9]+) \(Online IDs: ([^|]+)\| Controller ID: ([^)]+)\) caused by ([A-Za-z0-9_-]+)_C"
)

def _on_player_wounded(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerWounded | None:
    if "INVALID" in m.group(4):
        ids = {"eos_id": "", "steam_id": ""}
    else:
        ids = parse_online_ids(m.group(4))
    victim_name = m.group(3)
    damage = float(m.group(4) if m.group(4).replace('.','').isdigit() else m.group(4))
    # re-extract damage from the correct group
    damage = float(m.group(4))
    ...
```

Actually — let me provide the exact, correct implementation. The regex groups shift because of `_PREFIX` capturing groups 1 and 2. Let me be precise about which group is which.

For `_PLAYER_WOUNDED_RE`, the groups after prefix (1=time, 2=chainID) are:
- 3: player name (note: space after `Player:` in the log)
- 4: damage value
- 5: attacker controller or `nullptr`
- 6: online IDs string
- 7: controller ID
- 8: weapon class

```python
_PLAYER_WOUNDED_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQSoldier::)?Wound\(\): Player:(.+) KillingDamage=(?:-)*([0-9.]+) from (.+) \(Online IDs: ([^|]+)\| Controller ID: ([^)]+)\) caused by ([A-Za-z0-9_-]+)_C"
)

def _on_player_wounded(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerWounded | None:
    ids_raw = m.group(6)
    if "INVALID" in ids_raw:
        ids = {"eos_id": "", "steam_id": ""}
    else:
        ids = parse_online_ids(ids_raw)
    victim_name = m.group(3)
    damage = float(m.group(4))
    weapon_raw = m.group(8)
    attacker = PlayerID(
        eos_id=ids["eos_id"],
        steam_id=ids["steam_id"],
        controller=m.group(5).strip(),
    )
    correlated = store.session.get(victim_name, {})
    store.session[victim_name] = {
        **correlated,
        "attacker_eos_id": ids["eos_id"],
        "attacker_steam_id": ids["steam_id"],
        "weapon": weapon_raw,
    }
    return PlayerWounded(victim_name=victim_name, damage=damage, attacker=attacker, weapon=weapon_raw)


_PLAYER_DIED_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQSoldier::)?Die\(\): Player:(.+) KillingDamage=(?:-)*([0-9.]+) from (.+) \(Online IDs: ([^|]+)\| Conto?ller ID: ([^)]+)\) caused by ([A-Za-z0-9_-]+)_C"
)

def _on_player_died(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerDied | None:
    ids_raw = m.group(6)
    if "INVALID" in ids_raw:
        ids = {"eos_id": "", "steam_id": ""}
    else:
        ids = parse_online_ids(ids_raw)
    victim_name = m.group(3)
    damage = float(m.group(4))
    weapon_raw = m.group(8)
    attacker = PlayerID(
        eos_id=ids["eos_id"],
        steam_id=ids["steam_id"],
        controller=m.group(5).strip(),
    )
    correlated = store.session.get(victim_name, {})
    store.session[victim_name] = {
        **correlated,
        "attacker_eos_id": ids["eos_id"],
        "attacker_steam_id": ids["steam_id"],
        "weapon": weapon_raw,
    }
    return PlayerDied(victim_name=victim_name, damage=damage, attacker=attacker, weapon=weapon_raw)


_PLAYER_REVIVED_RE = re.compile(
    _PREFIX + r"LogSquad: (.+) \(Online IDs: ([^)]+)\) has revived (.+) \(Online IDs: ([^)]+)\)\."
)

def _on_player_revived(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerRevived:
    reviver_name = m.group(3).strip()
    reviver_ids = parse_online_ids(m.group(4))
    victim_name = m.group(5).strip()
    victim_ids = parse_online_ids(m.group(6))
    reviver = PlayerID(eos_id=reviver_ids["eos_id"], steam_id=reviver_ids["steam_id"], name=reviver_name)
    victim = PlayerID(eos_id=victim_ids["eos_id"], steam_id=victim_ids["steam_id"], name=victim_name)
    return PlayerRevived(reviver=reviver, victim=victim)
```

Note: The `Die()` regex uses `Conto?ller` to handle both `Controller` and the typo `Contoller`.

Add to `get_rules()`:

```python
Rule(_PLAYER_DAMAGED_RE, _on_player_damaged),
Rule(_PLAYER_WOUNDED_RE, _on_player_wounded),
Rule(_PLAYER_DIED_RE, _on_player_died),
Rule(_PLAYER_REVIVED_RE, _on_player_revived),
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_patterns.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/patterns.py tests/test_patterns.py
git commit -m "feat(log_parser): add regex patterns for combat events"
```

---

### Task 7: Regex Patterns — Part C (Possess, Game State, Server Events)

**Files:**
- Modify: `squadpy/log_parser/patterns.py`
- Modify: `tests/test_patterns.py`

**Step 1: Add failing tests**

```python
from squadpy.events.types import (
    PlayerPossess, PlayerUnpossess, NewGame, RoundEnded,
    ServerTickRate, AdminBroadcast, DeployableDamaged,
)


class TestPlayerPossess:
    def test_infantry(self):
        line = '[2026.02.06-15.05.03:337][386]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Uɴɴ. Gunrunner (Online IDs: EOS: 00022f823cdc4f1cad945c19ff4e8b37 steam: 76561198031492269) Pawn=BP_Soldier_TLF_Medic_01_C_2147464264 FullPath=BP_Soldier_TLF_Medic_01_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_Soldier_TLF_Medic_01_C_2147464264'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerPossess)
        assert event.player.eos_id == "00022f823cdc4f1cad945c19ff4e8b37"
        assert event.possess_classname == "BP_Soldier_TLF_Medic_01_C"

    def test_vehicle(self):
        line = '[2026.02.06-15.28.52:780][490]LogSquadTrace: [DedicatedServer]OnPossess(): PC=PAPA_ Ξ_TAN (Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392) Pawn=BP_Loach_CAS_Small_C_2147396130 FullPath=BP_Loach_CAS_Small_C /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF:PersistentLevel.BP_Loach_CAS_Small_C_2147396130'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerPossess)
        assert event.possess_classname == "BP_Loach_CAS_Small_C"


class TestPlayerUnpossess:
    def test_normal(self):
        line = '[2026.02.06-15.18.55:664][475]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=Uɴɴ. Gunrunner (Online IDs: EOS: 00022f823cdc4f1cad945c19ff4e8b37 steam: 76561198031492269) current health value 100.000000'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerUnpossess)
        assert event.player.eos_id == "00022f823cdc4f1cad945c19ff4e8b37"
        assert event.health == 100.0
        assert event.exited_vehicle is False

    def test_vehicle_exit(self):
        line = '[2026.02.06-15.36.45:676][655]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=PAPA_ Ξ_TAN (Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392) Exited Vehicle Pawn=PAPA_ Ξ_TAN (Asset Name=BP_Loach_CAS_Small_C) FullPath=BP_Loach_CAS_Small_C /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF:PersistentLevel.BP_Loach_CAS_Small_C_2147396130 Seat Number=0'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerUnpossess)
        assert event.exited_vehicle is True
        assert event.vehicle_name == "BP_Loach_CAS_Small_C"
        assert event.seat_number == 0


class TestNewGame:
    def test_vanilla_map(self):
        line = '[2026.02.06-15.19.26:022][383]LogWorld: Bringing World /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF up for play (max tick rate 64) at 2026.02.06-15.19.26'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, NewGame)
        assert event.dlc == "Game"
        assert event.map_classname == "Jensens_Range"
        assert event.layer_classname == "Jensens_Range_WPMC-TLF"

    def test_modded_map(self):
        line = '[2026.02.07-05.58.50:012][867]LogWorld: Bringing World /HawksLayerPack/Maps/Mutaha/Gameplay_Layers/HLP_Mutaha_GRAAS_v1.HLP_Mutaha_GRAAS_v1 up for play (max tick rate 64) at 2026.02.07-05.58.50'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, NewGame)
        assert event.dlc == "HawksLayerPack"
        assert event.layer_classname == "HLP_Mutaha_GRAAS_v1"

    def test_transition_map_ignored(self):
        line = '[2026.02.06-15.19.25:580][366]LogWorld: Bringing World /Game/Maps/TransitionMap.TransitionMap up for play (max tick rate 64) at 2026.02.06-15.19.25'
        store = EventStore()
        event = match_line(line, store)
        assert event is None

    def test_clears_event_store(self):
        store = EventStore()
        store.session["old"] = {"data": 1}
        store.players["eos"] = {"name": "test"}
        line = '[2026.02.06-15.19.26:022][383]LogWorld: Bringing World /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF up for play (max tick rate 64) at 2026.02.06-15.19.26'
        match_line(line, store)
        assert store.session == {}


class TestRoundEnded:
    def test_with_winner_and_loser(self):
        store = EventStore()
        store.round_winner = {"team": "1", "subfaction": "MEA", "tickets": 50}
        store.round_loser = {"team": "2", "subfaction": "USA", "tickets": 0}
        line = '[2026.02.06-15.18.55:666][475]LogGameState: Match State Changed from InProgress to WaitingPostMatch'
        event = match_line(line, store)
        assert isinstance(event, RoundEnded)
        assert event.winner["team"] == "1"
        assert event.loser["team"] == "2"
        assert store.round_winner is None
        assert store.round_loser is None

    def test_draw(self):
        store = EventStore()
        line = '[2026.02.06-15.18.55:666][475]LogGameState: Match State Changed from InProgress to WaitingPostMatch'
        event = match_line(line, store)
        assert isinstance(event, RoundEnded)
        assert event.winner is None
        assert event.loser is None


class TestRoundWinnerAndTickets:
    def test_round_winner_stores_not_emits(self):
        line = '[2026.02.06-15.18.55:664][475]LogSquadTrace: [DedicatedServer]DetermineMatchWinner(): Manticore Security Task Force won on Sumari Bala'
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_winner is not None
        assert store.round_winner["winner"] == "Manticore Security Task Force"

    def test_draw_stores(self):
        line = '[2026.02.06-15.18.55:664][475]LogSquadTrace: [DedicatedServer]DetermineMatchWinner(): The game was a draw on Sumari Bala'
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_winner is not None
        assert store.round_winner["winner"] is None

    def test_round_tickets_stores_winner(self):
        line = "[2026.02.06-20.45.07:818][740]LogSquadGameEvents: Display: Team 1, Irregular Battle Group ( Middle Eastern Insurgents ) has won the match with 2 Tickets on layer Sumari Bala Seed v1 (level Sumari Bala)!"
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_winner is not None
        assert store.round_winner["tickets"] == 2

    def test_round_tickets_stores_loser(self):
        line = "[2026.02.06-20.45.07:818][740]LogSquadGameEvents: Display: Team 2, 21st Division ( Ground Forces of Iran ) has lost the match with 0 Tickets on layer Sumari Bala Seed v1 (level Sumari Bala)!"
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_loser is not None
        assert store.round_loser["tickets"] == 0


class TestServerTickRate:
    def test_tick_rate(self):
        line = '[2026.02.06-15.02.16:900][771]LogSquad: USQGameState: Server Tick Rate: 63.78'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, ServerTickRate)
        assert event.tick_rate == 63.78


class TestAdminBroadcast:
    def test_broadcast(self):
        line = '[2026.02.06-11.00.09:436][125]LogSquad: ADMIN COMMAND: Message broadcasted <Custom squad creation will be unlocked in 10 seconds. Default squad names are allowed.> from RCON'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, AdminBroadcast)
        assert "Custom squad creation" in event.message
        assert event.from_player == "RCON"


class TestDeployableDamaged:
    def test_deployable(self):
        line = '[2026.02.06-17.05.08:591][826]LogSquadTrace: [DedicatedServer]TakeDamage(): ASQDeployable::TakeDamage[SQRadialDamage] BP_I_Sandbag_80 for 115.000000 damage (type=BP_Fragmentation_DamageType_C) direct hit = 0'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, DeployableDamaged)
        assert event.deployable == "BP_I_Sandbag_80"
        assert event.damage == 115.0
        assert event.damage_source == "SQRadialDamage"
        assert event.damage_type == "BP_Fragmentation_DamageType_C"
        assert event.direct_hit is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_patterns.py::TestPlayerPossess -v`
Expected: FAIL

**Step 3: Add remaining patterns to `squadpy/log_parser/patterns.py`**

```python
# --- Possess/Unpossess ---

_PLAYER_POSSESS_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQPlayerController::)?OnPossess\(\): PC=(.+) \(Online IDs: ([^)]+)\) Pawn=([A-Za-z0-9_]+)_C_\d+"
)

def _on_player_possess(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerPossess:
    player_name = m.group(3)
    ids = parse_online_ids(m.group(4))
    pawn_class = m.group(5)
    player = PlayerID(eos_id=ids["eos_id"], steam_id=ids["steam_id"], name=player_name)
    return PlayerPossess(player=player, possess_classname=pawn_class)


_PLAYER_UNPOSSESS_VEHICLE_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQPlayerController::)?OnUnPossess\(\): PC=(.+) \(Online IDs: ([^)]+)\) Exited Vehicle .+Asset Name=([A-Za-z0-9_]+)_C\).+Seat Number=(\d+)"
)

_PLAYER_UNPOSSESS_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQPlayerController::)?OnUnPossess\(\): PC=(.+) \(Online IDs: ([^)]+)\) current health value ([0-9.]+)"
)

def _on_player_unpossess_vehicle(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerUnpossess:
    ids = parse_online_ids(m.group(4))
    player = PlayerID(eos_id=ids["eos_id"], steam_id=ids["steam_id"], name=m.group(3))
    return PlayerUnpossess(
        player=player, exited_vehicle=True,
        vehicle_name=m.group(5), seat_number=int(m.group(6)),
    )

def _on_player_unpossess(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerUnpossess:
    ids = parse_online_ids(m.group(4))
    player = PlayerID(eos_id=ids["eos_id"], steam_id=ids["steam_id"], name=m.group(3))
    return PlayerUnpossess(player=player, health=float(m.group(5)))


# --- Game state events ---

_NEW_GAME_RE = re.compile(
    _PREFIX + r"LogWorld: Bringing World /([A-Za-z]+)/(?:Maps/)?([A-Za-z0-9_-]+)/(?:.+/)?([A-Za-z0-9_-]+)\.\3"
)

def _on_new_game(m: re.Match, chain_id: int, time: str, store: EventStore) -> NewGame | None:
    layer = m.group(5)
    if layer == "TransitionMap":
        return None
    winner = store.round_winner
    store.clear()
    return NewGame(dlc=m.group(3), map_classname=m.group(4), layer_classname=layer, winner=winner)


_ROUND_ENDED_RE = re.compile(
    _PREFIX + r"LogGameState: Match State Changed from InProgress to WaitingPostMatch"
)

def _on_round_ended(m: re.Match, chain_id: int, time: str, store: EventStore) -> RoundEnded:
    winner = store.round_winner
    loser = store.round_loser
    store.round_winner = None
    store.round_loser = None
    return RoundEnded(winner=winner, loser=loser)


_ROUND_WINNER_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQGameMode::)?DetermineMatchWinner\(\): (.+) won on (.+)"
)

_ROUND_DRAW_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQGameMode::)?DetermineMatchWinner\(\): The game was a draw on (.+)"
)

def _on_round_winner(m: re.Match, chain_id: int, time: str, store: EventStore) -> None:
    store.round_winner = {"winner": m.group(3), "layer": m.group(4)}
    return None

def _on_round_draw(m: re.Match, chain_id: int, time: str, store: EventStore) -> None:
    store.round_winner = {"winner": None, "layer": m.group(3)}
    return None


_ROUND_TICKETS_RE = re.compile(
    _PREFIX + r"LogSquadGameEvents: Display: Team ([0-9]), (.+?) \( (.+?) \) has (won|lost) the match with ([0-9]+) Tickets on layer (.+) \(level (.+)\)!"
)

def _on_round_tickets(m: re.Match, chain_id: int, time: str, store: EventStore) -> None:
    data = {
        "team": m.group(3),
        "subfaction": m.group(4),
        "faction": m.group(5),
        "action": m.group(6),
        "tickets": int(m.group(7)),
        "layer": m.group(8),
        "level": m.group(9),
    }
    if data["action"] == "won":
        store.round_winner = data
    else:
        store.round_loser = data
    return None


# --- Server events ---

_SERVER_TICK_RATE_RE = re.compile(
    _PREFIX + r"LogSquad: USQGameState: Server Tick Rate: ([0-9.]+)"
)

def _on_server_tick_rate(m: re.Match, chain_id: int, time: str, store: EventStore) -> ServerTickRate:
    return ServerTickRate(tick_rate=float(m.group(3)))


_ADMIN_BROADCAST_RE = re.compile(
    _PREFIX + r"LogSquad: ADMIN COMMAND: Message broadcasted <(.+)> from (.+)"
)

def _on_admin_broadcast(m: re.Match, chain_id: int, time: str, store: EventStore) -> AdminBroadcast:
    return AdminBroadcast(message=m.group(3), from_player=m.group(4))


_DEPLOYABLE_DAMAGED_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\]TakeDamage\(\): ASQDeployable::TakeDamage\[([A-Za-z0-9_]+)\] ([A-Za-z0-9_]+) for ([0-9.]+) damage \(type=([A-Za-z0-9_]+)\) direct hit = ([01])"
)

def _on_deployable_damaged(m: re.Match, chain_id: int, time: str, store: EventStore) -> DeployableDamaged:
    return DeployableDamaged(
        deployable=m.group(4),
        damage=float(m.group(5)),
        damage_source=m.group(3),
        damage_type=m.group(6),
        direct_hit=m.group(7) == "1",
    )
```

Update `get_rules()` to include all rules in order (put vehicle unpossess before normal unpossess since it's more specific):

```python
def get_rules() -> list[Rule]:
    return [
        Rule(_PLAYER_CONNECTED_RE, _on_player_connected),
        Rule(_JOIN_SUCCEEDED_RE, _on_join_succeeded),
        Rule(_PLAYER_DISCONNECTED_RE, _on_player_disconnected),
        Rule(_PLAYER_DAMAGED_RE, _on_player_damaged),
        Rule(_PLAYER_WOUNDED_RE, _on_player_wounded),
        Rule(_PLAYER_DIED_RE, _on_player_died),
        Rule(_PLAYER_REVIVED_RE, _on_player_revived),
        Rule(_PLAYER_POSSESS_RE, _on_player_possess),
        Rule(_PLAYER_UNPOSSESS_VEHICLE_RE, _on_player_unpossess_vehicle),
        Rule(_PLAYER_UNPOSSESS_RE, _on_player_unpossess),
        Rule(_ROUND_DRAW_RE, _on_round_draw),
        Rule(_ROUND_WINNER_RE, _on_round_winner),
        Rule(_ROUND_TICKETS_RE, _on_round_tickets),
        Rule(_ROUND_ENDED_RE, _on_round_ended),
        Rule(_NEW_GAME_RE, _on_new_game),
        Rule(_SERVER_TICK_RATE_RE, _on_server_tick_rate),
        Rule(_ADMIN_BROADCAST_RE, _on_admin_broadcast),
        Rule(_DEPLOYABLE_DAMAGED_RE, _on_deployable_damaged),
    ]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_patterns.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/patterns.py tests/test_patterns.py
git commit -m "feat(log_parser): add regex patterns for possess, game state, and server events"
```

---

### Task 8: LocalLogReader

**Files:**
- Create: `squadpy/log_parser/reader.py`
- Create: `squadpy/log_parser/local.py`
- Test: `tests/test_local_reader.py`

**Step 1: Write the failing tests**

```python
"""Tests for the local file log reader."""

import asyncio
from pathlib import Path

import pytest

from squadpy.log_parser.local import LocalLogReader


class TestLocalLogReader:
    @pytest.fixture
    def log_file(self, tmp_path) -> Path:
        path = tmp_path / "SquadGame.log"
        path.write_text("existing line 1\nexisting line 2\n")
        return path

    async def test_seeks_to_end_on_start(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.05)
        await reader.start()
        lines = []
        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 1:
                    break
        # Write a new line after start
        with open(log_file, "a") as f:
            f.write("new line\n")
        await asyncio.wait_for(collect(), timeout=1.0)
        assert lines == ["new line"]
        await reader.stop()

    async def test_tails_multiple_lines(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.05)
        await reader.start()
        lines = []
        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 3:
                    break
        with open(log_file, "a") as f:
            f.write("line A\nline B\nline C\n")
        await asyncio.wait_for(collect(), timeout=1.0)
        assert lines == ["line A", "line B", "line C"]
        await reader.stop()

    async def test_handles_missing_file(self, tmp_path):
        reader = LocalLogReader(str(tmp_path / "nonexistent.log"), poll_interval=0.05)
        with pytest.raises(FileNotFoundError):
            await reader.start()

    async def test_stop_ends_iteration(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.05)
        await reader.start()
        async def collect():
            async for _ in reader.tail():
                pass
        # Stop should cause tail() to end
        await reader.stop()
        await asyncio.wait_for(collect(), timeout=1.0)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_local_reader.py -v`
Expected: FAIL

**Step 3: Write the implementations**

`squadpy/log_parser/reader.py`:

```python
"""Abstract base class for log readers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LogReader(ABC):
    """Base class for log readers that tail Squad server log files."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize and prepare for tailing."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop tailing and clean up resources."""

    @abstractmethod
    def tail(self) -> AsyncIterator[str]:
        """Yield new log lines as they appear."""
```

`squadpy/log_parser/local.py`:

```python
"""Local file log reader — async tail implementation."""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from squadpy.log_parser.reader import LogReader

logger = logging.getLogger("squadpy.log_parser.local")


class LocalLogReader(LogReader):
    """Tails a local log file, yielding new lines as they appear."""

    def __init__(self, path: str, poll_interval: float = 1.0):
        self._path = Path(path)
        self._poll_interval = poll_interval
        self._running = False
        self._file = None

    async def start(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Log file not found: {self._path}")
        self._file = open(self._path, "r", encoding="utf-8", errors="replace")
        self._file.seek(0, 2)  # seek to end
        self._running = True
        logger.info("Tailing local log: %s", self._path)

    async def stop(self) -> None:
        self._running = False
        if self._file:
            self._file.close()
            self._file = None

    async def tail(self) -> AsyncIterator[str]:
        while self._running:
            line = self._file.readline()
            if line:
                stripped = line.rstrip("\n\r")
                if stripped:
                    yield stripped
            else:
                await asyncio.sleep(self._poll_interval)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_local_reader.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/reader.py squadpy/log_parser/local.py tests/test_local_reader.py
git commit -m "feat(log_parser): add LogReader ABC and local file tail reader"
```

---

### Task 9: LogParser Integration

**Files:**
- Create: `squadpy/log_parser/parser.py`
- Test: `tests/test_log_parser.py`

**Step 1: Write the failing tests**

```python
"""Integration tests for the LogParser — feeds lines, verifies events."""

import asyncio

import pytest

from squadpy.events.emitter import EventBus
from squadpy.events.types import (
    BaseEvent, PlayerConnected, JoinSucceeded, PlayerDamaged,
    PlayerWounded, PlayerDied, RoundEnded, ServerTickRate,
)
from squadpy.log_parser.parser import LogParser
from squadpy.log_parser.reader import LogReader


class MockLogReader(LogReader):
    """Feeds pre-set lines to the parser."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def tail(self):
        for line in self._lines:
            if not self._running:
                break
            yield line


class TestLogParser:
    async def test_emits_player_connected(self):
        lines = [
            '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 1
        assert isinstance(events[0], PlayerConnected)

    async def test_connect_then_join(self):
        lines = [
            '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)',
            '[2026.02.06-15.02.11:099][401]LogNet: Join succeeded: PAPA_ Ξ_TAN',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 2
        assert isinstance(events[0], PlayerConnected)
        assert isinstance(events[1], JoinSucceeded)
        assert events[1].player.eos_id == "000250f5e359453bb9ad313db051f19e"

    async def test_damage_wound_die_sequence(self):
        lines = [
            '[2026.02.06-16.57.06:079][ 49]LogSquad: Player: enwez ActualDamage=58.952755 from  lord billybean (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Player Controller ID: BP_PlayerController_C_2147285821)caused by BP_KBA3_HEAT_C_2147362075',
            '[2026.02.06-16.57.19:764][922]LogSquadTrace: [DedicatedServer]Wound(): Player: enwez KillingDamage=37.075439 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Controller ID: BP_PlayerController_C_2147285821) caused by BP_KBA3_HEAT_C_2147362075',
            '[2026.02.06-16.57.23:024][130]LogSquadTrace: [DedicatedServer]Die(): Player: enwez KillingDamage=-300.000000 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Contoller ID: BP_PlayerController_C_2147285821) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147279843',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 3
        assert isinstance(events[0], PlayerDamaged)
        assert isinstance(events[1], PlayerWounded)
        assert isinstance(events[2], PlayerDied)

    async def test_unmatched_lines_ignored(self):
        lines = [
            '[2026.02.06-15.02.16:900][771]LogSquad: USQGameState: Server Tick Rate: 63.78',
            'some random unmatched line',
            '[2026.02.06-15.02.26:935][411]LogSquad: USQGameState: Server Tick Rate: 63.78',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 2
        assert all(isinstance(e, ServerTickRate) for e in events)

    async def _run_parser(self, lines: list[str]) -> list[BaseEvent]:
        """Helper: run parser with mock reader and capture all emitted events."""
        collected: list[BaseEvent] = []
        bus = EventBus()

        async def capture(event: BaseEvent):
            collected.append(event)

        # Subscribe to all possible event names
        event_names = [
            "player_connected", "join_succeeded", "player_disconnected",
            "player_damaged", "player_wounded", "player_died", "player_revived",
            "player_possess", "player_unpossess", "new_game", "round_ended",
            "server_tick_rate", "admin_broadcast", "deployable_damaged",
        ]
        for name in event_names:
            bus.subscribe(name, capture)

        reader = MockLogReader(lines)
        parser = LogParser(reader=reader, event_bus=bus)
        await parser.run()
        return collected
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_log_parser.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
"""LogParser — matches log lines against patterns and emits events."""

import logging

from squadpy.events.emitter import EventBus
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line
from squadpy.log_parser.reader import LogReader

logger = logging.getLogger("squadpy.log_parser")


class LogParser:
    """Consumes lines from a LogReader, matches patterns, emits events."""

    def __init__(self, reader: LogReader, event_bus: EventBus):
        self.reader = reader
        self.event_bus = event_bus
        self.event_store = EventStore()

    async def run(self) -> None:
        """Main loop: read lines, match patterns, emit events."""
        await self.reader.start()
        try:
            async for line in self.reader.tail():
                try:
                    event = match_line(line, self.event_store)
                    if event is not None:
                        await self.event_bus.emit(event)
                except Exception:
                    logger.exception("Error parsing line: %s", line[:200])
        finally:
            await self.reader.stop()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_log_parser.py -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/parser.py tests/test_log_parser.py
git commit -m "feat(log_parser): add LogParser with pattern matching and event emission"
```

---

### Task 10: Module Exports and Server Integration

**Files:**
- Modify: `squadpy/log_parser/__init__.py`
- Modify: `squadpy/server.py`
- Modify: `squadpy/config.py` (import in server.py)
- Modify: `tests/test_server.py`

**Step 1: Write the failing tests**

Add to `tests/test_server.py`:

```python
from squadpy.config import ServerConfig, LoggingConfig


class TestServerLogReaderIntegration:
    def test_log_reader_in_services_when_configured(self):
        """Server config with log enabled should register log_reader service."""
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
            log={"enabled": True, "mode": "local", "path": "/tmp/test.log"},
        )
        assert config.log.enabled is True

    def test_log_reader_not_in_services_when_disabled(self):
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
        )
        assert config.log.enabled is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py::TestServerLogReaderIntegration -v`
Expected: FAIL (LogConfig not yet on ServerConfig if Task 3 hasn't been done, or PASS if it has)

**Step 3: Write the implementation**

Update `squadpy/log_parser/__init__.py`:

```python
"""Log parser package — reads Squad server logs and emits events."""

from squadpy.log_parser.parser import LogParser
from squadpy.log_parser.reader import LogReader
from squadpy.log_parser.local import LocalLogReader
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.id_parser import parse_online_ids

__all__ = ["LogParser", "LogReader", "LocalLogReader", "EventStore", "parse_online_ids"]
```

Update `squadpy/server.py` — add log reader startup between RCON and plugins:

In imports, add:

```python
from squadpy.config import ServerConfig, LoggingConfig, LogConfig
from squadpy.log_parser import LogParser, LocalLogReader
```

In `SquadPyServer.__init__`, add:

```python
self._log_parser: LogParser | None = None
self._log_parser_task: asyncio.Task | None = None
```

In `SquadPyServer.start()`, after RCON connect and before plugin loading, add:

```python
# Start log reader (if configured)
log_ok = False
log_detail = ""
if self._server_config.log.enabled:
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
        log_ok = True
        log_detail = f"tailing ({self._server_config.log.mode})"
    except Exception as e:
        log_detail = str(e)
        logger.error("Log reader failed: %s", e)
else:
    log_detail = "not configured"
```

Add `"log_reader"` to services dict:

```python
services = {
    "rcon": self._rcon if rcon_ok else None,
    "log_reader": self._log_parser if log_ok else None,
    "discord": None,
    "db": None,
    "server": self,
}
```

Update `_print_summary` to use the actual log reader status:

```python
format_service_line("Log Reader", log_ok, log_detail),
```

(Change the method signature to accept `log_ok` and `log_detail` params.)

In `stop()`, cancel the log parser task:

```python
if self._log_parser_task:
    self._log_parser_task.cancel()
```

**Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```
git add squadpy/log_parser/__init__.py squadpy/server.py tests/test_server.py
git commit -m "feat: integrate log parser into server orchestrator"
```

---

### Task 11: Validate Regex Against Real Logs

**Files:**
- Create: `tests/test_patterns_real_logs.py` (only runs if sample files exist)

**Step 1: Write validation test**

This test reads real log files and ensures no crashes + reasonable match counts:

```python
"""Validate regex patterns against real Squad log files.

Skipped if sample files don't exist (they're gitignored).
"""

import pytest
from pathlib import Path

from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

SAMPLES_DIR = Path(__file__).parent / "fixtures" / "samples"


@pytest.mark.skipif(
    not SAMPLES_DIR.exists() or not list(SAMPLES_DIR.glob("*.log")),
    reason="No sample log files available",
)
class TestRealLogs:
    @pytest.fixture(params=list(SAMPLES_DIR.glob("*.log")) if SAMPLES_DIR.exists() else [])
    def log_file(self, request):
        return request.param

    def test_no_crashes(self, log_file):
        """Every line should either match a pattern or be silently skipped."""
        store = EventStore()
        match_count = 0
        line_count = 0
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_count += 1
                result = match_line(line.rstrip(), store)
                if result is not None:
                    match_count += 1
        # Sanity: we should match at least some lines in a real log
        assert match_count > 0, f"No matches in {log_file.name} ({line_count} lines)"
        print(f"\n{log_file.name}: {match_count}/{line_count} lines matched")
```

**Step 2: Run the validation**

Run: `pytest tests/test_patterns_real_logs.py -v -s`
Expected: PASS for all 3 log files, with match counts printed

**Step 3: Fix any regex patterns that crash or fail to match**

If any patterns crash on real data, fix them. Common issues:
- Unicode in player names not matching `[A-z]` character classes
- Edge cases in Online IDs format
- Unexpected whitespace or field ordering

Iterate: fix pattern → re-run validation → repeat until clean.

**Step 4: Commit**

```
git add tests/test_patterns_real_logs.py
git commit -m "test: add real log validation for regex patterns"
```

---

### Task 12: SFTP Log Reader (Stub)

**Files:**
- Create: `squadpy/log_parser/sftp.py`

**Step 1: Write a stub with clear error**

```python
"""SFTP log reader — requires asyncssh."""

from squadpy.log_parser.reader import LogReader


class SFTPLogReader(LogReader):
    """Reads Squad logs from a remote server via SFTP."""

    def __init__(self, host: str, port: int, username: str, password: str,
                 path: str, poll_interval: float = 1.0):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._path = path
        self._poll_interval = poll_interval

    async def start(self) -> None:
        raise NotImplementedError(
            "SFTP log reader requires 'asyncssh' package. "
            "Install with: pip install asyncssh"
        )

    async def stop(self) -> None:
        pass

    async def tail(self):
        raise NotImplementedError
        yield  # make it a generator
```

No tests needed for the stub. Full implementation deferred until `asyncssh` is added as a dependency.

**Step 2: Add to exports**

Update `squadpy/log_parser/__init__.py` to export `SFTPLogReader`.

**Step 3: Commit**

```
git add squadpy/log_parser/sftp.py squadpy/log_parser/__init__.py
git commit -m "feat(log_parser): add SFTP log reader stub"
```

---

### Task 13: Final Cleanup and Full Test Run

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 2: Run real log validation**

Run: `pytest tests/test_patterns_real_logs.py -v -s`
Expected: All 3 log files pass without crashes

**Step 3: Update CLAUDE.md if needed**

Add log_parser to the project layout table if not already there.

**Step 4: Final commit**

```
git add -A
git commit -m "chore: phase 2 cleanup and final integration"
```
