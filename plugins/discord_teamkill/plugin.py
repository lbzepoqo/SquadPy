"""DiscordTeamkill - posts teamkill events to Discord."""

from squadpy.events.types import Teamkill
from squadpy.plugin import Plugin, on_event


class DiscordTeamkill(Plugin):
    name = "Discord Teamkill"
    description = "Posts teamkill events to a Discord channel"
    requires = ["discord"]

    @on_event("teamkill")
    async def handle_teamkill(self, event: Teamkill):
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        attacker_name = event.attacker.name or "UnknownAttacker"
        attacker_steam_id = event.attacker.steam_id or "unknown"
        victim_name = event.victim.name or "UnknownVictim"
        victim_steam_id = event.victim.steam_id or "unknown"

        include_weapon = self.config.get("include_weapon", True)
        weapon_text = f" weapon={event.weapon}" if include_weapon and event.weapon else ""

        content = (
            f"[Teamkill] {attacker_name} ({attacker_steam_id}) -> "
            f"{victim_name} ({victim_steam_id}){weapon_text}"
        )
        await self.discord.send(channel_id, content=content)
