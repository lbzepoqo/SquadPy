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
class Teamkill(BaseEvent):
    event_name: str = "teamkill"
    attacker: PlayerID = field(default_factory=PlayerID)
    victim: PlayerID = field(default_factory=PlayerID)
    weapon: str = ""


@dataclass
class SquadCreated(BaseEvent):
    event_name: str = "squad_created"
    team_id: int = 0
    team_name: str = ""
    squad_id: int = 0
    squad_name: str = ""
    creator: PlayerID = field(default_factory=PlayerID)


@dataclass
class PlayerSwitchedTeam(BaseEvent):
    event_name: str = "player_switched_team"
    player: PlayerID = field(default_factory=PlayerID)
    old_team: int = 0
    new_team: int = 0


@dataclass
class NextLayerSet(BaseEvent):
    event_name: str = "next_layer_set"
    layer: str = ""
    source: str = ""
    source_detail: str = ""


@dataclass
class SeedingThresholdUp(BaseEvent):
    event_name: str = "seeding_threshold_up"
    old_threshold: int = 0
    new_threshold: int = 0
    source: str = ""
    source_detail: str = ""


@dataclass
class SeedingThresholdDown(BaseEvent):
    event_name: str = "seeding_threshold_down"
    old_threshold: int = 0
    new_threshold: int = 0
    source: str = ""
    source_detail: str = ""


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
    source: str = ""
    source_detail: str = ""


@dataclass
class PlayerWarned(BaseEvent):
    event_name: str = "player_warned"
    admin: str = ""
    player: PlayerID = field(default_factory=PlayerID)
    reason: str = ""
    source: str = ""
    source_detail: str = ""


@dataclass
class PlayerKicked(BaseEvent):
    event_name: str = "player_kicked"
    admin: str = ""
    player: PlayerID = field(default_factory=PlayerID)
    reason: str = ""
    source: str = ""
    source_detail: str = ""


@dataclass
class PlayerBanned(BaseEvent):
    event_name: str = "player_banned"
    admin: str = ""
    player: PlayerID = field(default_factory=PlayerID)
    duration: str = ""
    reason: str = ""
    source: str = ""
    source_detail: str = ""


@dataclass
class AdminCamPossess(BaseEvent):
    event_name: str = "admin_cam_possess"
    admin: PlayerID = field(default_factory=PlayerID)
    target: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdminCamUnpossess(BaseEvent):
    event_name: str = "admin_cam_unpossess"
    admin: PlayerID = field(default_factory=PlayerID)
    target: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeployableDamaged(BaseEvent):
    event_name: str = "deployable_damaged"
    deployable: str = ""
    damage: float = 0.0
    damage_source: str = ""
    damage_type: str = ""
    direct_hit: bool = False


@dataclass
class ChatMessage(BaseEvent):
    event_name: str = "chat_message"
    player_name: str = ""
    steam_id: str = ""
    eos_id: str = ""
    channel: str = ""
    message: str = ""
