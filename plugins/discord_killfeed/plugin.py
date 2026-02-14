"""DiscordKillfeed - posts kill events to Discord."""

from squadpy.events.types import PlayerDied
from squadpy.plugin import Plugin, on_event


class DiscordKillfeed(Plugin):
    name = "Discord Killfeed"
    description = "Posts kill events to a Discord channel"
    requires = ["discord"]

    @on_event("player_died")
    async def handle_player_died(self, event: PlayerDied):
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        attacker_name = event.attacker.name or "UnknownAttacker"
        victim_name = event.victim_name or "UnknownVictim"

        include_weapon = self.config.get("include_weapon", True)
        weapon_text = f" weapon={event.weapon}" if include_weapon and event.weapon else ""

        content = f"[Killfeed] {attacker_name} -> {victim_name}{weapon_text}"
        await self.discord.send(channel_id, content=content)
