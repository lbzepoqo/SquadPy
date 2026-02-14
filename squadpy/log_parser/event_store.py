"""EventStore for cross-line correlation state during log parsing."""

from typing import Any


class EventStore:
    """Mutable state for correlating events across multiple log lines.

    Mirrors the SquadJS eventStore pattern:
    - session: damage/wound correlation by player name
    - players: player info by EOS ID
    - player_teams_by_name: team assignment by in-log player name
    - join_requests: pending joins by chain ID (consumed by JoinSucceeded)
    - disconnected: recently disconnected EOS IDs
    - pending_events: secondary events queued by match handlers
    - pending_bans: temporary ban context by chain ID
    - pending_admin_cam_possess: temporary possess context by chain ID
    - active_admin_cam_sessions: open admin-cam sessions by admin identity
    - round_winner/round_loser: held until RoundEnded emits them
    """

    def __init__(self):
        self.session: dict[str, Any] = {}
        self.players: dict[str, Any] = {}
        self.player_teams_by_name: dict[str, int] = {}
        self.join_requests: dict[int, Any] = {}
        self.disconnected: dict[str, bool] = {}
        self.pending_events: list[Any] = []
        self.pending_bans: dict[int, Any] = {}
        self.pending_admin_cam_possess: dict[int, Any] = {}
        self.active_admin_cam_sessions: dict[str, Any] = {}
        self.round_winner: dict[str, Any] | None = None
        self.round_loser: dict[str, Any] | None = None

    def clear(self) -> None:
        """Reset all state. Called on NEW_GAME."""
        self.session.clear()
        self.players.clear()
        self.player_teams_by_name.clear()
        self.join_requests.clear()
        self.disconnected.clear()
        self.pending_events.clear()
        self.pending_bans.clear()
        self.pending_admin_cam_possess.clear()
        self.active_admin_cam_sessions.clear()
        self.round_winner = None
        self.round_loser = None

    def drain_pending_events(self) -> list[Any]:
        """Return and clear any queued secondary events."""
        queued = self.pending_events.copy()
        self.pending_events.clear()
        return queued
