"""EndMatchVote - vote-driven end match control for players."""

from __future__ import annotations

import math
import time

from squadpy.plugin import Plugin, on_event


class EndMatchVote(Plugin):
    name = "End Match Vote"
    description = "Ends the current match when player vote quorum is reached"
    requires = ["rcon"]

    async def on_enable(self):
        self._votes: set[str] = set()
        self._window_started_at: float | None = None
        self._last_success_at: float = 0.0

    @on_event("chat_message")
    async def handle_chat(self, event):
        if not self._matches_command(str(getattr(event, "message", ""))):
            return

        channel = str(getattr(event, "channel", "")).strip()
        if not self._channel_allowed(channel):
            return

        actor_id = self._actor_id(event)
        if not actor_id:
            return

        now = self._now()
        blocked, remaining = self._cooldown_blocked(now)
        if blocked:
            await self.rcon.warn(
                actor_id,
                self._format(
                    str(
                        self.config.get(
                            "cooldown_message",
                            "End match vote is on cooldown for {remaining}s.",
                        )
                    ),
                    remaining=str(max(1, math.ceil(remaining))),
                    cooldown=str(math.ceil(self._cooldown_seconds())),
                ),
            )
            return

        players = await self.rcon.list_players()
        player_count = len(players)
        min_players = self._min_players()
        if player_count < min_players:
            await self.rcon.warn(
                actor_id,
                self._format(
                    str(
                        self.config.get(
                            "not_enough_players_message",
                            "End match vote needs at least {min_players} players online.",
                        )
                    ),
                    min_players=str(min_players),
                    players=str(player_count),
                ),
            )
            return

        self._ensure_vote_window(now)
        if actor_id in self._votes:
            await self.rcon.warn(
                actor_id,
                str(
                    self.config.get(
                        "already_voted_message",
                        "You already voted to end the match.",
                    )
                ),
            )
            return

        self._votes.add(actor_id)
        required_votes = self._required_votes(player_count)
        current_votes = len(self._votes)

        await self.rcon.warn(
            actor_id,
            self._format(
                str(
                    self.config.get(
                        "vote_recorded_message",
                        "End match vote recorded ({votes}/{required}).",
                    )
                ),
                votes=str(current_votes),
                required=str(required_votes),
                players=str(player_count),
            ),
        )

        if current_votes >= required_votes:
            await self.rcon.broadcast(
                self._format(
                    str(
                        self.config.get(
                            "success_message",
                            "Vote passed ({votes}/{required}). Ending match.",
                        )
                    ),
                    votes=str(current_votes),
                    required=str(required_votes),
                    players=str(player_count),
                )
            )
            await self.rcon.execute("AdminEndMatch")
            self._last_success_at = now
            self._reset_votes()
            return

        if bool(self.config.get("announce_progress", True)):
            await self.rcon.broadcast(
                self._format(
                    str(
                        self.config.get(
                            "progress_message",
                            "End match vote: {votes}/{required} ({players} players online).",
                        )
                    ),
                    votes=str(current_votes),
                    required=str(required_votes),
                    players=str(player_count),
                )
            )

    @on_event("new_game")
    async def handle_new_game(self, event):
        self._reset_votes()

    def _actor_id(self, event) -> str:
        steam_id = str(getattr(event, "steam_id", "")).strip()
        if steam_id:
            return steam_id
        return str(getattr(event, "eos_id", "")).strip()

    def _matches_command(self, message: str) -> bool:
        return message.strip().lower() == self._command_token()

    def _command_token(self) -> str:
        configured = str(self.config.get("command", "!endmatch")).strip().lower()
        return configured or "!endmatch"

    def _channel_allowed(self, channel: str) -> bool:
        raw = self.config.get("allowed_channels", [])
        if not isinstance(raw, list) or not raw:
            return True

        allowed = {str(item).strip().lower() for item in raw if str(item).strip()}
        if not allowed:
            return True
        return channel.lower() in allowed

    def _ensure_vote_window(self, now: float) -> None:
        if self._window_started_at is None:
            self._window_started_at = now
            return

        window_seconds = self._vote_window_seconds()
        if window_seconds <= 0:
            return

        if now - self._window_started_at >= window_seconds:
            self._reset_votes()
            self._window_started_at = now

    def _reset_votes(self) -> None:
        self._votes.clear()
        self._window_started_at = None

    def _required_votes(self, player_count: int) -> int:
        threshold_votes = max(1, math.ceil(player_count * self._vote_threshold_ratio()))
        return max(self._min_votes(), threshold_votes)

    def _min_players(self) -> int:
        try:
            value = int(self.config.get("min_players", 1))
        except (TypeError, ValueError):
            return 1
        return value if value > 0 else 1

    def _min_votes(self) -> int:
        try:
            value = int(self.config.get("min_votes", 8))
        except (TypeError, ValueError):
            return 8
        return value if value > 0 else 1

    def _vote_threshold_ratio(self) -> float:
        try:
            value = float(self.config.get("vote_threshold_ratio", 0.6))
        except (TypeError, ValueError):
            return 0.6
        if value <= 0:
            return 0.6
        if value > 1:
            return 1.0
        return value

    def _vote_window_seconds(self) -> float:
        try:
            value = float(self.config.get("vote_window_seconds", 120))
        except (TypeError, ValueError):
            return 120.0
        return value if value > 0 else 0.0

    def _cooldown_seconds(self) -> float:
        try:
            value = float(self.config.get("cooldown_seconds", 600))
        except (TypeError, ValueError):
            return 600.0
        return value if value > 0 else 0.0

    def _cooldown_blocked(self, now: float) -> tuple[bool, float]:
        cooldown = self._cooldown_seconds()
        if cooldown <= 0:
            return False, 0.0
        if self._last_success_at <= 0:
            return False, 0.0

        remaining = cooldown - (now - self._last_success_at)
        if remaining <= 0:
            return False, 0.0
        return True, remaining

    def _now(self) -> float:
        return time.monotonic()

    def _format(self, template: str, **values: str) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template
