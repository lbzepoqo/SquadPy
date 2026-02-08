"""AutoKickUnassigned — kicks players not in any squad after warnings."""

from squadpy.plugin import Plugin, on_event, periodic


class AutoKickUnassigned(Plugin):
    name = "Auto Kick Unassigned"
    description = "Kicks players not in a squad after warning them"
    requires = ["rcon"]

    async def on_enable(self):
        self._warnings: dict[str, int] = {}

    @periodic(seconds=30)
    async def check_unassigned(self):
        min_players = self.config.get("min_players", 20)
        warnings_before_kick = self.config.get("warnings_before_kick", 3)
        warning_message = self.config.get("warning_message", "Please join a squad or you will be kicked")
        kick_message = self.config.get("kick_message", "Kicked for not joining a squad")

        players = await self.rcon.list_players()

        if len(players) < min_players:
            self._warnings.clear()
            return

        assigned = {p.steam_id for p in players if p.squad_id != 0}

        # Clear warnings for players who joined a squad
        for steam_id in list(self._warnings):
            if steam_id in assigned:
                del self._warnings[steam_id]

        for player in players:
            if player.squad_id != 0:
                continue
            self._warnings[player.steam_id] = self._warnings.get(player.steam_id, 0) + 1
            count = self._warnings[player.steam_id]

            if count >= warnings_before_kick:
                await self.rcon.kick(player.steam_id, kick_message)
                del self._warnings[player.steam_id]
            else:
                await self.rcon.warn(player.steam_id, warning_message)

    @on_event("new_game")
    async def reset_warnings(self, event):
        self._warnings.clear()
