"""TKWarn — tracks teamkills per round, warns offenders, kicks after threshold."""

from squadpy.plugin import Plugin, on_event, periodic
from squadpy.rcon.types import RconPlayer


class TKWarn(Plugin):
    name = "TK Warn"
    description = "Warns and kicks players for excessive teamkills"
    requires = ["rcon"]

    async def on_enable(self):
        self._tk_counts: dict[str, int] = {}
        self._player_cache: dict[str, RconPlayer] = {}

    @periodic(seconds=30)
    async def refresh_players(self):
        players = await self.rcon.list_players()
        self._player_cache = {p.name: p for p in players}

    @on_event("player_wounded")
    async def handle_wound(self, event):
        kick_threshold = self.config.get("kick_threshold", 5)
        warning_message = self.config.get(
            "warning_message", "Team kill #{count} recorded. {threshold} = kick."
        )
        kick_message = self.config.get(
            "kick_message", "Kicked for excessive teamkills ({count})"
        )

        victim = self._player_cache.get(event.victim_name)
        attacker = self._player_cache.get(event.attacker.name)

        if not victim or not attacker:
            return
        if victim.steam_id == attacker.steam_id:
            return
        if victim.team_id != attacker.team_id:
            return

        # Same team, different players — teamkill
        self._tk_counts[attacker.steam_id] = self._tk_counts.get(attacker.steam_id, 0) + 1
        count = self._tk_counts[attacker.steam_id]

        if count >= kick_threshold:
            msg = kick_message.format(count=count, threshold=kick_threshold)
            await self.rcon.kick(attacker.steam_id, msg)
        else:
            msg = warning_message.format(count=count, threshold=kick_threshold)
            await self.rcon.warn(attacker.steam_id, msg)

    @on_event("new_game")
    async def reset_counts(self, event):
        self._tk_counts.clear()
