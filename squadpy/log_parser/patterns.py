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
    Teamkill,
    SquadCreated,
    PlayerRevived,
    PlayerPossess,
    PlayerUnpossess,
    NewGame,
    RoundEnded,
    ServerTickRate,
    AdminBroadcast,
    PlayerWarned,
    PlayerKicked,
    PlayerBanned,
    AdminCamPossess,
    AdminCamUnpossess,
    DeployableDamaged,
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


def _clean_player_name(name: str) -> str:
    """Normalize leading clan-tag style prefixes for fuzzy name matching."""
    stripped = name.strip()
    return re.sub(r"^(?:\[[^\]]+\]\s*)+", "", stripped).strip()


def _names_match(left: str, right: str) -> bool:
    """Compare player names with exact, normalized, and suffix fallbacks."""
    left_raw = left.strip()
    right_raw = right.strip()
    if not left_raw or not right_raw:
        return False
    if left_raw == right_raw:
        return True

    left_clean = _clean_player_name(left_raw)
    right_clean = _clean_player_name(right_raw)
    if left_clean and right_clean and left_clean == right_clean:
        return True

    return (
        left_raw.endswith(right_raw)
        or right_raw.endswith(left_raw)
        or (left_clean and right_clean and left_clean.endswith(right_clean))
        or (left_clean and right_clean and right_clean.endswith(left_clean))
    )


def _team_for_name(name: str, store: EventStore) -> int | None:
    """Resolve team assignment from cached player-team mappings."""
    name_raw = name.strip()
    if not name_raw:
        return None

    if name_raw in store.player_teams_by_name:
        return store.player_teams_by_name[name_raw]

    clean = _clean_player_name(name_raw)
    if clean in store.player_teams_by_name:
        return store.player_teams_by_name[clean]

    for known_name, team_id in store.player_teams_by_name.items():
        if _names_match(name_raw, known_name):
            return team_id
    return None


def _team_id_for_display_name(team_name: str, store: EventStore) -> int | None:
    """Resolve team ID from cached ListSquads team display names."""
    lookup = team_name.strip()
    if not lookup:
        return None

    if lookup in store.team_ids_by_name:
        return store.team_ids_by_name[lookup]

    normalized_lookup = re.sub(r"\s+", " ", lookup).strip().casefold()
    for known_name, team_id in store.team_ids_by_name.items():
        normalized_known = re.sub(r"\s+", " ", known_name).strip().casefold()
        if normalized_lookup == normalized_known:
            return team_id
    return None


def _find_player_by_name(name: str, store: EventStore) -> PlayerID:
    """Best-effort lookup of EOS/Steam identity by in-log player name."""
    fallback_name = _clean_player_name(name) or name.strip()
    for eos_id, record in store.players.items():
        record_name = str(record.get("name", "")).strip()
        if not record_name:
            continue
        if _names_match(name, record_name):
            return PlayerID(
                eos_id=eos_id,
                steam_id=str(record.get("steam_id", "")),
                name=record_name,
            )
    return PlayerID(name=fallback_name)


def _remember_player(player: PlayerID, store: EventStore) -> None:
    """Persist player identity and backfill known team assignment."""
    if not player.eos_id:
        return

    record = store.players.setdefault(player.eos_id, {})
    if player.steam_id:
        record["steam_id"] = player.steam_id
    if player.controller:
        record["controller"] = player.controller
    if player.name:
        record["name"] = player.name.strip()
        team_id = _team_for_name(player.name, store)
        if team_id is not None:
            record["team_id"] = team_id


def _queue_teamkill_if_detected(
    store: EventStore,
    attacker: PlayerID,
    victim_name: str,
    weapon: str,
) -> None:
    """Queue a Teamkill event when attacker/victim resolve to the same team."""
    attacker_team: int | None = None
    attacker_name = attacker.name.strip()
    attacker_steam = attacker.steam_id

    if attacker.eos_id:
        record = store.players.get(attacker.eos_id, {})
        if not attacker_name:
            attacker_name = str(record.get("name", "")).strip()
        if not attacker_steam:
            attacker_steam = str(record.get("steam_id", "")).strip()
        team_raw = record.get("team_id")
        if isinstance(team_raw, int):
            attacker_team = team_raw
    if attacker_team is None and attacker_name:
        attacker_team = _team_for_name(attacker_name, store)

    victim = _find_player_by_name(victim_name, store)
    victim_team = _team_for_name(victim.name or victim_name, store)

    if attacker_team is None or victim_team is None:
        return
    if attacker_team != victim_team:
        return

    if attacker.eos_id and victim.eos_id and attacker.eos_id == victim.eos_id:
        return
    if attacker_name and victim.name and _names_match(attacker_name, victim.name):
        return

    store.pending_events.append(
        Teamkill(
            attacker=PlayerID(
                eos_id=attacker.eos_id,
                steam_id=attacker_steam,
                name=attacker_name,
                controller=attacker.controller,
            ),
            victim=victim,
            weapon=weapon,
        )
    )


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
    _remember_player(player, store)
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
    _remember_player(player, store)
    return JoinSucceeded(
        player=player, chain_id=chain_id, player_suffix=player_suffix
    )


# Team assignment: group 3 = player name, group 4 = team id
_PLAYER_ADDED_TO_TEAM_RE = re.compile(
    _PREFIX + r"LogSquad: Player\s+(.+?)\s+has been added to Team\s+([0-9]+)"
)


def _on_player_added_to_team(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> None:
    player_name = m.group(3).strip()
    team_id = int(m.group(4))

    # Cache by raw and cleaned names for later combat correlation.
    store.player_teams_by_name[player_name] = team_id
    cleaned = _clean_player_name(player_name)
    if cleaned:
        store.player_teams_by_name[cleaned] = team_id

    for record in store.players.values():
        record_name = str(record.get("name", "")).strip()
        if record_name and _names_match(player_name, record_name):
            record["team_id"] = team_id
    return None


# Squad creation:
# group 3 = creator name, group 4 = creator online IDs, group 5 = squad id,
# group 6 = squad name, group 7 = team display name
_SQUAD_CREATED_RE = re.compile(
    _PREFIX
    + r"LogSquad:\s+(.+?)\s+\(Online IDs:\s*([^)]+)\)\s+has created Squad\s+([0-9]+)\s+\(Squad Name:\s*(.+?)\)\s+on\s+(.+)$"
)


def _on_squad_created(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> SquadCreated:
    creator_name = m.group(3).strip()
    creator_ids = parse_online_ids(m.group(4))
    squad_id = int(m.group(5))
    squad_name = m.group(6).strip()
    team_name = m.group(7).strip()

    creator = PlayerID(
        eos_id=creator_ids["eos_id"],
        steam_id=creator_ids["steam_id"],
        name=creator_name,
    )
    _remember_player(creator, store)

    team_id = _team_id_for_display_name(team_name, store)
    if team_id is None and creator.eos_id:
        raw_team_id = store.players.get(creator.eos_id, {}).get("team_id")
        if isinstance(raw_team_id, int):
            team_id = raw_team_id

    if team_id is not None and creator_name:
        store.player_teams_by_name[creator_name] = team_id
        cleaned = _clean_player_name(creator_name)
        if cleaned:
            store.player_teams_by_name[cleaned] = team_id
        if creator.eos_id:
            store.players.setdefault(creator.eos_id, {})["team_id"] = team_id

    return SquadCreated(
        team_id=team_id or 0,
        team_name=team_name,
        squad_id=squad_id,
        squad_name=squad_name,
        creator=creator,
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
        "last_event": "damage",
    }
    if ids["eos_id"]:
        store.players.setdefault(ids["eos_id"], {})["controller"] = attacker_controller
    _remember_player(attacker, store)
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
    attacker_controller = m.group(5).strip()
    attacker = PlayerID(
        eos_id=ids["eos_id"],
        steam_id=ids["steam_id"],
        controller=attacker_controller,
    )
    correlated = store.session.get(victim_name, {})
    store.session[victim_name] = {
        **correlated,
        "attacker_eos_id": ids["eos_id"],
        "attacker_steam_id": ids["steam_id"],
        "attacker_controller": attacker_controller,
        "weapon": weapon_raw,
        "last_event": "wound",
    }
    _remember_player(attacker, store)
    _queue_teamkill_if_detected(
        store=store,
        attacker=attacker,
        victim_name=victim_name,
        weapon=weapon_raw,
    )
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
    attacker_controller = m.group(5).strip()
    attacker = PlayerID(
        eos_id=ids["eos_id"],
        steam_id=ids["steam_id"],
        controller=attacker_controller,
    )
    correlated = store.session.get(victim_name, {})
    same_attacker = (
        (
            bool(ids["eos_id"])
            and str(correlated.get("attacker_eos_id", "")) == ids["eos_id"]
        )
        or (
            bool(ids["steam_id"])
            and str(correlated.get("attacker_steam_id", "")) == ids["steam_id"]
        )
        or (
            attacker_controller
            and attacker_controller != "nullptr"
            and str(correlated.get("attacker_controller", "")) == attacker_controller
        )
    )
    is_followup_wound = (
        correlated.get("last_event") == "wound"
        and same_attacker
    )
    store.session[victim_name] = {
        **correlated,
        "attacker_eos_id": ids["eos_id"],
        "attacker_steam_id": ids["steam_id"],
        "attacker_controller": attacker_controller,
        "weapon": weapon_raw,
        "last_event": "died",
    }
    _remember_player(attacker, store)
    # SquadJS emits TEAMKILL from Wound; add a die-path fallback for cases that
    # skip Wound entirely (for example insta-kill or revived-then-die edge paths).
    if not is_followup_wound:
        _queue_teamkill_if_detected(
            store=store,
            attacker=attacker,
            victim_name=victim_name,
            weapon=weapon_raw,
        )
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


# --- Possess/Unpossess ---

# OnPossess:
# group 3 = player name, group 4 = online IDs, group 5 = pawn class name,
# group 6 = optional full path payload.
_PLAYER_POSSESS_RE = re.compile(
    _PREFIX
    + r"LogSquadTrace: \[DedicatedServer\](?:ASQPlayerController::)?OnPossess\(\): "
    + r"PC=(.+) \(Online IDs: ([^)]+)\) Pawn=([A-Za-z0-9_]+_C)_\d+"
    + r"(?: FullPath=(.+))?"
)


def _on_player_possess(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerPossess:
    player_name = m.group(3).strip()
    ids = parse_online_ids(m.group(4))
    pawn_class = m.group(5)
    full_path = (m.group(6) or "").strip()
    player = PlayerID(eos_id=ids["eos_id"], steam_id=ids["steam_id"], name=player_name)
    _remember_player(player, store)
    if pawn_class == "BP_DeveloperAdminCam_C":
        store.pending_admin_cam_possess[chain_id] = {
            "admin": player,
            "target": "Admin Camera",
            "context": {
                "pawn_classname": pawn_class,
                "full_path": full_path,
            },
        }
    return PlayerPossess(player=player, possess_classname=pawn_class)


# OnUnPossess (vehicle exit variant — more specific, must be checked BEFORE normal variant):
# group 3 = player name, group 4 = online IDs, group 5 = vehicle asset name, group 6 = seat number
_PLAYER_UNPOSSESS_VEHICLE_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQPlayerController::)?OnUnPossess\(\): PC=(.+) \(Online IDs: ([^)]+)\) Exited Vehicle .+Asset Name=([A-Za-z0-9_]+_C)\).+Seat Number=(\d+)"
)


def _on_player_unpossess_vehicle(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerUnpossess:
    ids = parse_online_ids(m.group(4))
    player = PlayerID(eos_id=ids["eos_id"], steam_id=ids["steam_id"], name=m.group(3))
    _remember_player(player, store)
    return PlayerUnpossess(
        player=player, exited_vehicle=True,
        vehicle_name=m.group(5), seat_number=int(m.group(6)),
    )


# OnUnPossess (normal variant): group 3 = player name, group 4 = online IDs, group 5 = health
_PLAYER_UNPOSSESS_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQPlayerController::)?OnUnPossess\(\): PC=(.+) \(Online IDs: ([^)]+)\) current health value ([0-9.]+)"
)


def _on_player_unpossess(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerUnpossess:
    ids = parse_online_ids(m.group(4))
    player = PlayerID(eos_id=ids["eos_id"], steam_id=ids["steam_id"], name=m.group(3))
    _remember_player(player, store)
    return PlayerUnpossess(player=player, health=float(m.group(5)))


# OnUnPossess (bare variant used by admin-cam exit):
# group 3 = player name, group 4 = online IDs
_PLAYER_UNPOSSESS_BARE_RE = re.compile(
    _PREFIX
    + r"LogSquadTrace: \[DedicatedServer\](?:ASQPlayerController::)?OnUnPossess\(\): "
    + r"PC=(.+) \(Online IDs: ([^)]+)\)$"
)


def _on_player_unpossess_bare(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> AdminCamUnpossess | None:
    player_name = m.group(3).strip()
    ids = parse_online_ids(m.group(4))
    admin = PlayerID(
        eos_id=ids["eos_id"],
        steam_id=ids["steam_id"],
        name=player_name,
    )
    session_key = admin.eos_id or admin.name
    session = store.active_admin_cam_sessions.pop(session_key, None)
    if session is None:
        return None
    session_context = dict(session.get("context", {}))
    session_context["open_chain_id"] = session.get("open_chain_id")
    session_context["close_chain_id"] = chain_id
    return AdminCamUnpossess(
        admin=admin,
        target=session.get("target", "Admin Camera"),
        context=session_context,
    )


# Admin Camera possess marker: emitted after admin-cam OnPossess on same chain id.
_ADMIN_CAM_POSSESSED_RE = re.compile(
    _PREFIX + r"LogSquad: Warning: Admin Camera possessed\."
)


def _on_admin_cam_possessed(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> AdminCamPossess | None:
    context = store.pending_admin_cam_possess.pop(chain_id, None)
    if context is None:
        return None
    admin: PlayerID = context["admin"]
    session_key = admin.eos_id or admin.name
    store.active_admin_cam_sessions[session_key] = {
        "admin": admin,
        "target": context["target"],
        "context": context["context"],
        "open_chain_id": chain_id,
    }
    return AdminCamPossess(
        admin=admin,
        target=context["target"],
        context={
            **context["context"],
            "open_chain_id": chain_id,
        },
    )


# --- Game state events ---

# NewGame (Bringing World): group 3 = DLC/source, group 4 = map name, group 5 = layer name
# Path format: /<DLC>/Maps/<MapName>/Gameplay_Layers/<LayerName>.<LayerName>
# TransitionMap (/Game/Maps/TransitionMap.TransitionMap) has no subdirectory so won't match.
_NEW_GAME_RE = re.compile(
    _PREFIX + r"LogWorld: Bringing World /([A-Za-z0-9_]+)/Maps/([A-Za-z0-9_-]+)/.+/([A-Za-z0-9_-]+)\.\5"
)


def _on_new_game(m: re.Match, chain_id: int, time: str, store: EventStore) -> NewGame | None:
    layer = m.group(5)
    if layer == "TransitionMap":
        return None
    winner = store.round_winner
    store.clear()
    return NewGame(dlc=m.group(3), map_classname=m.group(4), layer_classname=layer, winner=winner)


# RoundEnded (Match State Changed): no extra groups beyond prefix
_ROUND_ENDED_RE = re.compile(
    _PREFIX + r"LogGameState: Match State Changed from InProgress to WaitingPostMatch"
)


def _on_round_ended(m: re.Match, chain_id: int, time: str, store: EventStore) -> RoundEnded:
    winner = store.round_winner
    loser = store.round_loser
    store.round_winner = None
    store.round_loser = None
    return RoundEnded(winner=winner, loser=loser)


# RoundWinner (DetermineMatchWinner — win): group 3 = winner name, group 4 = layer name
_ROUND_WINNER_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQGameMode::)?DetermineMatchWinner\(\): (.+) won on (.+)"
)


def _on_round_winner(m: re.Match, chain_id: int, time: str, store: EventStore) -> None:
    store.round_winner = {"winner": m.group(3), "layer": m.group(4)}
    return None


# RoundDraw (DetermineMatchWinner — draw): group 3 = layer name
_ROUND_DRAW_RE = re.compile(
    _PREFIX + r"LogSquadTrace: \[DedicatedServer\](?:ASQGameMode::)?DetermineMatchWinner\(\): The game was a draw on (.+)"
)


def _on_round_draw(m: re.Match, chain_id: int, time: str, store: EventStore) -> None:
    store.round_winner = {"winner": None, "layer": m.group(3)}
    return None


# RoundTickets: group 3 = team number, group 4 = subfaction, group 5 = faction,
# group 6 = "won"/"lost", group 7 = tickets, group 8 = layer, group 9 = level
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

# Server Tick Rate: group 3 = tick rate value
_SERVER_TICK_RATE_RE = re.compile(
    _PREFIX + r"LogSquad: USQGameState: Server Tick Rate: ([0-9.]+)"
)


def _on_server_tick_rate(m: re.Match, chain_id: int, time: str, store: EventStore) -> ServerTickRate:
    return ServerTickRate(tick_rate=float(m.group(3)))


# Admin Broadcast: group 3 = message, group 4 = from player/source
_ADMIN_BROADCAST_RE = re.compile(
    _PREFIX + r"LogSquad: ADMIN COMMAND: Message broadcasted <(.+)> from (.+)"
)


def _on_admin_broadcast(m: re.Match, chain_id: int, time: str, store: EventStore) -> AdminBroadcast:
    return AdminBroadcast(message=m.group(3), from_player=m.group(4))


# Admin Warned: group 3 = admin/source actor, group 4 = warned player name,
# group 5 = warn message, group 6 = command source (for example RCON)
_PLAYER_WARNED_RE = re.compile(
    _PREFIX
    + r'LogSquad: ADMIN COMMAND: (.+?) has warned player\s+(.+?)\. Message was "(.+)" from (.+)'
)


def _on_player_warned(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerWarned:
    return PlayerWarned(
        admin=m.group(3).strip(),
        player=PlayerID(name=m.group(4).strip()),
        reason=m.group(5),
        source=m.group(6).strip(),
    )


# Admin Kicked: group 3 = admin/source actor, group 4 = kicked player name,
# group 5 = kick reason/message, group 6 = command source (for example RCON)
_PLAYER_KICKED_RE = re.compile(
    _PREFIX
    + r'LogSquad: ADMIN COMMAND: (.+?) has kicked player\s+(.+?)\. (?:Reason was|Message was) "(.+)" from (.+)'
)


def _on_player_kicked(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerKicked:
    return PlayerKicked(
        admin=m.group(3).strip(),
        player=PlayerID(name=m.group(4).strip()),
        reason=m.group(5),
        source=m.group(6).strip(),
    )


# Ban prelude (online game): group 3 = player name, group 4 = reason
_PLAYER_BAN_REQUEST_RE = re.compile(
    _PREFIX
    + r"LogOnlineGame: Display: Banning player:\s*(.+?)\s*;\s*Reason = (.+)"
)


def _on_player_ban_request(m: re.Match, chain_id: int, time: str, store: EventStore) -> None:
    context = store.pending_bans.get(chain_id, {})
    context["player_name"] = m.group(3).strip()
    context["reason"] = m.group(4).strip()
    store.pending_bans[chain_id] = context
    return None


# Ban prelude (kick line): group 3 = player name, group 4 = duration days, group 5 = reason
_PLAYER_BAN_KICK_RE = re.compile(
    _PREFIX
    + r"LogOnlineGame: Display: Kicking player:\s*(.+?)\s*;\s*Reason = Banned from the server for ([0-9]+) Day\(s\)\. Admin Reason: (.+?)(?:\.)?$"
)


def _on_player_ban_kick(m: re.Match, chain_id: int, time: str, store: EventStore) -> None:
    context = store.pending_bans.get(chain_id, {})
    context["player_name"] = m.group(3).strip()
    context["duration"] = f"{m.group(4).strip()} Day(s)"
    context["reason"] = m.group(5).strip()
    store.pending_bans[chain_id] = context
    return None


# Admin Banned detailed line:
# group 3 = admin/source actor, group 4 = target player slot index,
# group 5 = target EOS ID, group 6 = target Steam ID,
# group 7 = target player name, group 8 = interval token,
# group 9 = source detail (for example RCON or player X ...).
_PLAYER_BANNED_ADMIN_RE = re.compile(
    _PREFIX
    + r"LogSquad: ADMIN COMMAND:\s+(.+?)\s+Banned player\s+([0-9]+)\.\s+\[Online IDs=\s+EOS:\s+([0-9A-Fa-f]+)\s+steam:\s+([0-9]+)\]\s+(.+?)\s+for interval\s+(-?[0-9]+)\s+from\s+(.+)"
)


def _normalize_ban_admin(raw: str) -> str:
    admin = raw.strip()
    if admin.upper() == "N/A":
        return "N/A"
    # In-game bans append the actor EOS ID in brackets; keep only the visible name.
    admin = re.sub(r"\s*\[EOSID\s+[0-9A-Fa-f]+\]\s*$", "", admin).strip()
    return admin


def _normalize_ban_source(raw: str) -> str:
    source = raw.strip()
    if source.upper() == "RCON":
        return "RCON"
    if source.lower().startswith("player "):
        return "IN_GAME"
    return source


def _on_player_banned_admin(m: re.Match, chain_id: int, time: str, store: EventStore) -> PlayerBanned:
    context = store.pending_bans.pop(chain_id, {})
    duration = str(context.get("duration", "")).strip()
    reason = str(context.get("reason", "")).strip()
    if not duration:
        duration = m.group(8).strip()
    return PlayerBanned(
        admin=_normalize_ban_admin(m.group(3)),
        player=PlayerID(
            eos_id=m.group(5).strip(),
            steam_id=m.group(6).strip(),
            name=m.group(7).strip(),
        ),
        duration=duration,
        reason=reason,
        source=_normalize_ban_source(m.group(9)),
    )


# Legacy Admin Banned line retained for compatibility with older fixtures:
# group 3 = admin/source actor, group 4 = banned player name,
# group 5 = optional ban duration/length, group 6 = ban reason/message,
# group 7 = command source (for example RCON)
_PLAYER_BANNED_LEGACY_RE = re.compile(
    _PREFIX
    + r'LogSquad: ADMIN COMMAND: (.+?) has banned player\s+(.+?)\. '
    + r'(?:(?:Ban (?:length|duration) was|for)\s+"?([^".]+)"?\.\s+)?'
    + r'(?:Reason was|Message was)\s+"(.+)"\s+from\s+(.+)'
)


def _on_player_banned_legacy(
    m: re.Match, chain_id: int, time: str, store: EventStore
) -> PlayerBanned:
    return PlayerBanned(
        admin=m.group(3).strip(),
        player=PlayerID(name=m.group(4).strip()),
        duration=(m.group(5) or "").strip(),
        reason=m.group(6),
        source=m.group(7).strip(),
    )


# Deployable Damaged: group 3 = damage source type, group 4 = deployable name,
# group 5 = damage amount, group 6 = damage type, group 7 = direct hit (0 or 1)
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


def get_rules() -> list[Rule]:
    """Return ordered list of all log parsing rules."""
    return [
        Rule(_PLAYER_CONNECTED_RE, _on_player_connected),
        Rule(_JOIN_SUCCEEDED_RE, _on_join_succeeded),
        Rule(_PLAYER_ADDED_TO_TEAM_RE, _on_player_added_to_team),
        Rule(_SQUAD_CREATED_RE, _on_squad_created),
        Rule(_PLAYER_DISCONNECTED_RE, _on_player_disconnected),
        Rule(_PLAYER_DAMAGED_RE, _on_player_damaged),
        Rule(_PLAYER_WOUNDED_RE, _on_player_wounded),
        Rule(_PLAYER_DIED_RE, _on_player_died),
        Rule(_PLAYER_REVIVED_RE, _on_player_revived),
        Rule(_PLAYER_POSSESS_RE, _on_player_possess),
        Rule(_PLAYER_UNPOSSESS_VEHICLE_RE, _on_player_unpossess_vehicle),
        Rule(_PLAYER_UNPOSSESS_RE, _on_player_unpossess),
        Rule(_PLAYER_UNPOSSESS_BARE_RE, _on_player_unpossess_bare),
        Rule(_ADMIN_CAM_POSSESSED_RE, _on_admin_cam_possessed),
        Rule(_ROUND_DRAW_RE, _on_round_draw),
        Rule(_ROUND_WINNER_RE, _on_round_winner),
        Rule(_ROUND_TICKETS_RE, _on_round_tickets),
        Rule(_ROUND_ENDED_RE, _on_round_ended),
        Rule(_NEW_GAME_RE, _on_new_game),
        Rule(_SERVER_TICK_RATE_RE, _on_server_tick_rate),
        Rule(_ADMIN_BROADCAST_RE, _on_admin_broadcast),
        Rule(_PLAYER_WARNED_RE, _on_player_warned),
        Rule(_PLAYER_KICKED_RE, _on_player_kicked),
        Rule(_PLAYER_BAN_REQUEST_RE, _on_player_ban_request),
        Rule(_PLAYER_BAN_KICK_RE, _on_player_ban_kick),
        Rule(_PLAYER_BANNED_ADMIN_RE, _on_player_banned_admin),
        Rule(_PLAYER_BANNED_LEGACY_RE, _on_player_banned_legacy),
        Rule(_DEPLOYABLE_DAMAGED_RE, _on_deployable_damaged),
    ]
