"""MaxPlayerInSquad - enforce per-squad size limits with exemptions."""

from __future__ import annotations

from collections import defaultdict

from squadpy.plugin import Plugin, on_event, periodic
from squadpy.rcon.types import RconPlayer


class MaxPlayerInSquad(Plugin):
    name = "Max Player In Squad"
    description = "Enforces a maximum number of players per squad"
    requires = ["rcon"]

    async def on_enable(self):
        self._warning_counts: dict[str, int] = {}

    @periodic(seconds=30)
    async def enforce_max_players(self):
        players = await self.rcon.list_players()
        if len(players) < self._min_players():
            self._warning_counts.clear()
            return

        squads: dict[tuple[int, int], list[RconPlayer]] = defaultdict(list)
        for player in players:
            if player.squad_id <= 0:
                continue
            squads[(player.team_id, player.squad_id)].append(player)

        max_players = self._max_players()
        active_offenders: set[str] = set()
        for (_, squad_id), squad_players in squads.items():
            if squad_id in self._exempt_squad_ids():
                continue
            if len(squad_players) <= max_players:
                continue

            enforceable = [
                player for player in squad_players if self._is_enforceable(player)
            ]
            overflow_count = len(squad_players) - max_players
            if overflow_count <= 0 or not enforceable:
                continue

            ordered = sorted(
                enforceable,
                key=lambda player: (
                    player.is_leader,
                    self._player_id(player),
                    player.name,
                ),
            )
            offenders = ordered[-min(overflow_count, len(ordered)) :]

            for offender in offenders:
                actor_id = self._player_id(offender)
                if not actor_id:
                    continue
                active_offenders.add(actor_id)
                await self._handle_offender(
                    actor_id=actor_id,
                    player_name=offender.name,
                    squad_id=squad_id,
                    squad_size=len(squad_players),
                    max_players=max_players,
                )

        for actor_id in list(self._warning_counts):
            if actor_id not in active_offenders:
                del self._warning_counts[actor_id]

    @on_event("new_game")
    async def reset_warnings(self, event):
        self._warning_counts.clear()

    async def _handle_offender(
        self,
        *,
        actor_id: str,
        player_name: str,
        squad_id: int,
        squad_size: int,
        max_players: int,
    ) -> None:
        threshold = self._warnings_before_kick()
        next_count = self._warning_counts.get(actor_id, 0) + 1

        if next_count >= threshold:
            kick_reason = self._format(
                str(
                    self.config.get(
                        "kick_reason",
                        "Squad {squad_id} exceeds {max_players} players.",
                    )
                ),
                player=player_name,
                squad_id=str(squad_id),
                squad_size=str(squad_size),
                max_players=str(max_players),
                warning_count=str(next_count),
                warnings_remaining="0",
            )
            await self.rcon.kick(actor_id, kick_reason)
            self._warning_counts.pop(actor_id, None)
            return

        self._warning_counts[actor_id] = next_count
        warning_message = self._format(
            str(
                self.config.get(
                    "warning_message",
                    "Squad {squad_id} is over {max_players}. Please leave or be kicked ({warnings_remaining} warning left).",
                )
            ),
            player=player_name,
            squad_id=str(squad_id),
            squad_size=str(squad_size),
            max_players=str(max_players),
            warning_count=str(next_count),
            warnings_remaining=str(max(0, threshold - next_count)),
        )
        await self.rcon.warn(actor_id, warning_message)

    def _is_enforceable(self, player: RconPlayer) -> bool:
        actor_id = self._player_id(player)
        if not actor_id:
            return False
        if actor_id in self._exempt_player_ids():
            return False
        if bool(self.config.get("exempt_leaders", True)) and player.is_leader:
            return False
        return True

    @staticmethod
    def _player_id(player: RconPlayer) -> str:
        return player.steam_id or player.eos_id

    def _max_players(self) -> int:
        try:
            value = int(self.config.get("max_players", 9))
        except (TypeError, ValueError):
            return 9
        return value if value > 0 else 9

    def _min_players(self) -> int:
        try:
            value = int(self.config.get("min_players", 0))
        except (TypeError, ValueError):
            return 0
        return value if value > 0 else 0

    def _warnings_before_kick(self) -> int:
        try:
            value = int(self.config.get("warnings_before_kick", 2))
        except (TypeError, ValueError):
            return 2
        return value if value > 0 else 1

    def _exempt_player_ids(self) -> set[str]:
        raw = self.config.get("exempt_steam_ids", [])
        if not isinstance(raw, list):
            return set()
        return {str(item).strip() for item in raw if str(item).strip()}

    def _exempt_squad_ids(self) -> set[int]:
        raw = self.config.get("exempt_squad_ids", [])
        if not isinstance(raw, list):
            return set()

        parsed: set[int] = set()
        for item in raw:
            try:
                squad_id = int(item)
            except (TypeError, ValueError):
                continue
            if squad_id > 0:
                parsed.add(squad_id)
        return parsed

    def _format(self, template: str, **values: str) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template
