"""EventStore for cross-line correlation state during log parsing."""

from typing import Any


class EventStore:
    """Mutable state for correlating events across multiple log lines.

    Mirrors the SquadJS eventStore pattern:
    - session: damage/wound correlation by player name
    - players: player info by EOS ID
    - join_requests: pending joins by chain ID (consumed by JoinSucceeded)
    - disconnected: recently disconnected EOS IDs
    - pending_bans: temporary ban context by chain ID
    - round_winner/round_loser: held until RoundEnded emits them
    """

    def __init__(self):
        self.session: dict[str, Any] = {}
        self.players: dict[str, Any] = {}
        self.join_requests: dict[int, Any] = {}
        self.disconnected: dict[str, bool] = {}
        self.pending_bans: dict[int, Any] = {}
        self.round_winner: dict[str, Any] | None = None
        self.round_loser: dict[str, Any] | None = None

    def clear(self) -> None:
        """Reset all state. Called on NEW_GAME."""
        self.session.clear()
        self.players.clear()
        self.join_requests.clear()
        self.disconnected.clear()
        self.pending_bans.clear()
        self.round_winner = None
        self.round_loser = None
