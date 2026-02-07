"""Squad server log regex patterns and match handlers.

Each rule is a (compiled_regex, handler_function) pair.
Handler signature: (match, chain_id, timestamp_str, event_store) -> BaseEvent | None
"""

import re
from dataclasses import dataclass
from typing import Callable

from squadpy.events.types import (
    BaseEvent,
    PlayerID,
    PlayerConnected,
    JoinSucceeded,
    PlayerDisconnected,
    PlayerDamaged,
    PlayerWounded,
    PlayerDied,
    PlayerRevived,
)
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.id_parser import parse_online_ids

# Common prefix: [timestamp][chain_id]
# Group 1 = timestamp, Group 2 = chain_id
_PREFIX = r"^\[([0-9.:-]+)\]\[([ 0-9]*)\]"

MatchHandler = Callable[[re.Match, int, str, EventStore], BaseEvent | None]


@dataclass
class Rule:
    """A log parsing rule: compiled regex + handler function."""

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

# PostLogin line captures: group 3 = controller instance name, group 4 = IP,
# group 5 = Online IDs string
_PLAYER_CONNECTED_RE = re.compile(
    _PREFIX
    + r"LogSquad: PostLogin: NewPlayer: .+\.([^\s]+) "
    + r"\(IP: ([\d.]+) \| Online IDs: ([^)]+)\)"
)


def _on_player_connected(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> PlayerConnected:
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
    return PlayerConnected(
        player=player, ip=ip, chain_id=chain_id, controller_name=controller_name
    )


# JoinSucceeded: group 3 = player name suffix
_JOIN_SUCCEEDED_RE = re.compile(_PREFIX + r"LogNet: Join succeeded: (.+)")


def _on_join_succeeded(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> JoinSucceeded:
    player_suffix = m.group(3)
    player_data = store.join_requests.pop(chain_id, {})
    player = PlayerID(
        eos_id=player_data.get("eos_id", ""),
        steam_id=player_data.get("steam_id", ""),
        name=player_suffix,
        controller=player_data.get("controller_name", ""),
    )
    return JoinSucceeded(
        player=player, chain_id=chain_id, player_suffix=player_suffix
    )


# PlayerDisconnected (UChannel::Close): group 3 = IP, group 4 = controller,
# group 5 = EOS ID
_PLAYER_DISCONNECTED_RE = re.compile(
    _PREFIX
    + r"LogNet: UChannel::Close: Sending CloseBunch\."
    + r".+RemoteAddr: ([\d.]+):\d+,"
    + r".+PC: ([^ ,]+),"
    + r".+UniqueId: RedpointEOS:([0-9a-f]+)"
)


def _on_player_disconnected(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> PlayerDisconnected:
    ip = m.group(3)
    controller_name = m.group(4)
    eos_id = m.group(5)
    store.disconnected[eos_id] = True
    player = PlayerID(eos_id=eos_id, controller=controller_name)
    return PlayerDisconnected(player=player, ip=ip, controller_name=controller_name)


# --- Combat events ---

# ActualDamage line: group 3 = victim name, group 4 = damage, group 5 = attacker name,
# group 6 = online IDs string, group 7 = controller ID, group 8 = weapon class
_PLAYER_DAMAGED_RE = re.compile(
    _PREFIX
    + r"LogSquad: Player: (.+) ActualDamage=([0-9.]+) from (.+) "
    + r"\(Online IDs: ([^|]+)\| Player Controller ID: ([^)]+)\)"
    + r"caused by ([A-Za-z0-9_-]+_C)_\d+"
)


def _on_player_damaged(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> PlayerDamaged:
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
    return PlayerDamaged(
        victim_name=victim_name, damage=damage, attacker=attacker, weapon=weapon_raw
    )


# Wound(): group 3 = victim name (with leading space), group 4 = damage,
# group 5 = attacker controller or "nullptr", group 6 = online IDs,
# group 7 = controller ID, group 8 = weapon class
_PLAYER_WOUNDED_RE = re.compile(
    _PREFIX
    + r"LogSquadTrace: \[DedicatedServer\](?:ASQSoldier::)?Wound\(\): Player:"
    + r"(.+) KillingDamage=(?:-)*([0-9.]+) from (.+) "
    + r"\(Online IDs: ([^|]+)\| Controller ID: ([^)]+)\) caused by "
    + r"([A-Za-z0-9_-]+_C)_\d+"
)


def _on_player_wounded(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> PlayerWounded:
    ids_raw = m.group(6)
    if "INVALID" in ids_raw:
        ids = {"eos_id": "", "steam_id": ""}
    else:
        ids = parse_online_ids(ids_raw)
    victim_name = m.group(3).strip()
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
    return PlayerWounded(
        victim_name=victim_name, damage=damage, attacker=attacker, weapon=weapon_raw
    )


# Die(): Same structure as Wound(), but uses "Contoller" (typo -- missing 'r')
# Use Conto?ller to handle both spellings
_PLAYER_DIED_RE = re.compile(
    _PREFIX
    + r"LogSquadTrace: \[DedicatedServer\](?:ASQSoldier::)?Die\(\): Player:"
    + r"(.+) KillingDamage=(?:-)*([0-9.]+) from (.+) "
    + r"\(Online IDs: ([^|]+)\| Conto?ller ID: ([^)]+)\) caused by "
    + r"([A-Za-z0-9_-]+_C)_\d+"
)


def _on_player_died(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> PlayerDied:
    ids_raw = m.group(6)
    if "INVALID" in ids_raw:
        ids = {"eos_id": "", "steam_id": ""}
    else:
        ids = parse_online_ids(ids_raw)
    victim_name = m.group(3).strip()
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
    return PlayerDied(
        victim_name=victim_name, damage=damage, attacker=attacker, weapon=weapon_raw
    )


# Revive: group 3 = reviver name (may have leading space), group 4 = reviver IDs,
# group 5 = victim name (may have leading space), group 6 = victim IDs
_PLAYER_REVIVED_RE = re.compile(
    _PREFIX
    + r"LogSquad: (.+) \(Online IDs: ([^)]+)\) has revived "
    + r"(.+) \(Online IDs: ([^)]+)\)\."
)


def _on_player_revived(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> PlayerRevived:
    reviver_name = m.group(3).strip()
    reviver_ids = parse_online_ids(m.group(4))
    victim_name = m.group(5).strip()
    victim_ids = parse_online_ids(m.group(6))
    reviver = PlayerID(
        eos_id=reviver_ids["eos_id"],
        steam_id=reviver_ids["steam_id"],
        name=reviver_name,
    )
    victim = PlayerID(
        eos_id=victim_ids["eos_id"],
        steam_id=victim_ids["steam_id"],
        name=victim_name,
    )
    return PlayerRevived(reviver=reviver, victim=victim)


def get_rules() -> list[Rule]:
    """Return ordered list of all log parsing rules."""
    return [
        Rule(_PLAYER_CONNECTED_RE, _on_player_connected),
        Rule(_JOIN_SUCCEEDED_RE, _on_join_succeeded),
        Rule(_PLAYER_DISCONNECTED_RE, _on_player_disconnected),
        Rule(_PLAYER_DAMAGED_RE, _on_player_damaged),
        Rule(_PLAYER_WOUNDED_RE, _on_player_wounded),
        Rule(_PLAYER_DIED_RE, _on_player_died),
        Rule(_PLAYER_REVIVED_RE, _on_player_revived),
    ]
