"""Typed dataclasses for parsed RCON responses."""

from dataclasses import dataclass


@dataclass
class RconPlayer:
    """A player from ListPlayers RCON response."""
    id: int
    steam_id: str
    eos_id: str
    name: str
    team_id: int
    squad_id: int
    is_leader: bool
    role: str


@dataclass
class RconSquad:
    """A squad from ListSquads RCON response."""
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
    """Parsed map information from ShowCurrentMap/ShowNextMap."""
    level: str
    layer: str
    factions: str
