"""DiscordSquadCreated - posts squad creation events to Discord."""

from squadpy.events.types import SquadCreated
from squadpy.plugin import Plugin, on_event


class DiscordSquadCreated(Plugin):
    name = "Discord Squad Created"
    description = "Posts squad creation events to a Discord channel"
    requires = ["discord"]

    @on_event("squad_created")
    async def handle_squad_created(self, event: SquadCreated) -> None:
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        team_id = str(event.team_id) if event.team_id > 0 else "unknown"
        team_name = event.team_name or "UnknownTeam"
        squad_id = str(event.squad_id) if event.squad_id > 0 else "unknown"
        squad_name = event.squad_name or "UnknownSquad"
        creator_name = event.creator.name or "UnknownCreator"

        include_creator_ids = self.config.get("include_creator_ids", True)
        creator_metadata = ""
        if include_creator_ids:
            creator_ids: list[str] = []
            if event.creator.steam_id:
                creator_ids.append(f"steam={event.creator.steam_id}")
            if event.creator.eos_id:
                creator_ids.append(f"eos={event.creator.eos_id}")
            if not creator_ids:
                creator_ids.append("ids=unknown")
            creator_metadata = f" ({', '.join(creator_ids)})"

        content = (
            f"[SquadCreated] team={team_id} ({team_name}) "
            f"squad={squad_id} name={squad_name} "
            f"creator={creator_name}{creator_metadata}"
        )
        await self.discord.send(channel_id, content=content)
