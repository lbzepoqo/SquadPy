"""DiscordRoundEvents - posts round lifecycle events to Discord."""

from squadpy.events.types import NewGame, RoundEnded
from squadpy.plugin import Plugin, on_event


class DiscordRoundEvents(Plugin):
    name = "Discord Round Events"
    description = "Posts round start/end events to a Discord channel"
    requires = ["discord"]

    @on_event("new_game")
    async def handle_new_game(self, event: NewGame):
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        include_previous_winner = self.config.get("include_previous_winner", True)
        previous_winner_text = ""
        if include_previous_winner and event.winner:
            winner_label = event.winner.get("winner")
            winner_text = winner_label if winner_label else "Draw"
            previous_winner_text = f" | previous_winner={winner_text}"

        content = (
            f"[RoundStart] map={event.map_classname} layer={event.layer_classname} "
            f"dlc={event.dlc}{previous_winner_text}"
        )
        await self.discord.send(channel_id, content=content)

    @on_event("round_ended")
    async def handle_round_ended(self, event: RoundEnded):
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        winner_text = self._format_outcome(event.winner)

        include_loser = self.config.get("include_loser", True)
        loser_text = ""
        if include_loser:
            loser_text = f" loser={self._format_outcome(event.loser)}"

        content = f"[RoundEnd] winner={winner_text}{loser_text}"
        await self.discord.send(channel_id, content=content)

    def _format_outcome(self, value: dict | None) -> str:
        if not value:
            return "unknown"
        winner_label = value.get("winner")
        if winner_label is not None:
            return str(winner_label) if winner_label else "draw"

        team = value.get("team", "?")
        faction = value.get("faction", "?")
        subfaction = value.get("subfaction", "?")
        tickets = value.get("tickets", "?")
        return f"team={team} faction={faction} subfaction={subfaction} tickets={tickets}"
