"""TeamRandomizer - nudges teams back toward fair balance."""

from __future__ import annotations

import math
import random
import time

from squadpy.plugin import Plugin, periodic
from squadpy.rcon.types import RconPlayer


class TeamRandomizer(Plugin):
    name = "Team Randomizer"
    description = "Randomly moves players to reduce team imbalance"
    requires = ["rcon"]

    async def on_enable(self):
        seed = self.config.get("random_seed")
        self._rng = random.Random(seed)
        self._last_randomize_at: float = 0.0

    @periodic(seconds=30)
    async def randomize_teams(self):
        players = await self.rcon.list_players()
        if len(players) < self._min_players():
            return

        now = self._now()
        if now - self._last_randomize_at < self._cycle_cooldown_seconds():
            return

        team1 = [p for p in players if p.team_id == 1]
        team2 = [p for p in players if p.team_id == 2]
        diff = len(team1) - len(team2)
        if abs(diff) <= self._max_team_difference():
            return

        bigger = team1 if diff > 0 else team2
        movable = [p for p in bigger if self._is_movable(p)]
        if not movable:
            return

        moves_needed = math.ceil((abs(diff) - self._max_team_difference()) / 2)
        move_count = min(moves_needed, self._max_moves_per_cycle(), len(movable))
        if move_count <= 0:
            return

        selected = self._rng.sample(movable, move_count)
        for player in selected:
            await self.rcon.switch_team(player.steam_id)

        self._last_randomize_at = now
        if bool(self.config.get("announce_moves", True)):
            msg = self._format(
                str(
                    self.config.get(
                        "announce_message",
                        "Team randomizer moved {count} player(s) ({team1}/{team2}).",
                    )
                ),
                count=move_count,
                team1=len(team1),
                team2=len(team2),
            )
            await self.rcon.broadcast(msg)

    def _now(self) -> float:
        return time.monotonic()

    def _is_movable(self, player: RconPlayer) -> bool:
        if not player.steam_id:
            return False
        if player.steam_id in self._exempt_ids():
            return False
        if not bool(self.config.get("allow_leaders", False)) and player.is_leader:
            return False
        return True

    def _min_players(self) -> int:
        try:
            value = int(self.config.get("min_players", 20))
        except (TypeError, ValueError):
            return 20
        return value if value > 0 else 20

    def _max_team_difference(self) -> int:
        try:
            value = int(self.config.get("max_team_difference", 1))
        except (TypeError, ValueError):
            return 1
        return value if value >= 0 else 1

    def _max_moves_per_cycle(self) -> int:
        try:
            value = int(self.config.get("max_moves_per_cycle", 2))
        except (TypeError, ValueError):
            return 2
        return value if value > 0 else 2

    def _cycle_cooldown_seconds(self) -> float:
        try:
            value = float(self.config.get("cycle_cooldown_seconds", 60))
        except (TypeError, ValueError):
            return 60.0
        return value if value > 0 else 0.0

    def _exempt_ids(self) -> set[str]:
        raw = self.config.get("exempt_steam_ids", [])
        if not isinstance(raw, list):
            return set()
        return {str(item) for item in raw if str(item).strip()}

    def _format(self, template: str, **values: int) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template
