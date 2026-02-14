"""AutoRejoinTeam - keeps returning players on their prior side."""

from __future__ import annotations

from squadpy.plugin import Plugin, on_event, periodic


class AutoRejoinTeam(Plugin):
    name = "Auto Rejoin Team"
    description = "Restores player team assignment for reconnects"
    requires = ["rcon"]

    async def on_enable(self):
        self._last_team_by_id: dict[str, int] = {}
        self._pending: set[str] = set()
        self._attempts: dict[str, int] = {}

    @periodic(seconds=30)
    async def refresh_players(self):
        players = await self.rcon.list_players()
        for player in players:
            if not player.steam_id:
                continue
            if player.team_id not in (1, 2):
                continue
            if player.steam_id in self._pending:
                continue
            self._last_team_by_id[player.steam_id] = player.team_id

    @periodic(seconds=15)
    async def enforce_rejoin(self):
        if not self._pending:
            return

        players = await self.rcon.list_players()
        if len(players) > self._max_players_for_rejoin():
            return

        by_steam = {p.steam_id: p for p in players if p.steam_id}
        max_attempts = self._max_attempts()

        for steam_id in list(self._pending):
            player = by_steam.get(steam_id)
            desired_team = self._last_team_by_id.get(steam_id)

            if player is None:
                continue
            if desired_team not in (1, 2):
                self._pending.discard(steam_id)
                self._attempts.pop(steam_id, None)
                continue
            if player.team_id == desired_team:
                self._pending.discard(steam_id)
                self._attempts.pop(steam_id, None)
                continue
            if player.team_id not in (1, 2):
                continue

            attempts = self._attempts.get(steam_id, 0)
            if attempts >= max_attempts:
                self._pending.discard(steam_id)
                self._attempts.pop(steam_id, None)
                continue

            await self.rcon.switch_team(steam_id)
            self._attempts[steam_id] = attempts + 1

    @on_event("join_succeeded")
    async def handle_join_succeeded(self, event):
        self._queue_player(event.player.steam_id)

    @on_event("player_connected")
    async def handle_player_connected(self, event):
        self._queue_player(event.player.steam_id)

    def _queue_player(self, steam_id: str) -> None:
        if not steam_id:
            return
        if steam_id not in self._last_team_by_id:
            return
        self._pending.add(steam_id)
        self._attempts[steam_id] = 0

    def _max_players_for_rejoin(self) -> int:
        try:
            value = int(self.config.get("max_players_for_rejoin", 80))
        except (TypeError, ValueError):
            return 80
        return value if value > 0 else 80

    def _max_attempts(self) -> int:
        try:
            value = int(self.config.get("max_attempts", 3))
        except (TypeError, ValueError):
            return 3
        return value if value > 0 else 3
