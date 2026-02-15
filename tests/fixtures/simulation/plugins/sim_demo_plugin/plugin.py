from squadpy.events.types import PlayerConnected
from squadpy.plugin import Plugin, on_event, periodic


class SimDemoPlugin(Plugin):
    name = "Sim Demo Plugin"
    description = "Simulation harness fixture plugin"
    requires = ["rcon"]

    async def on_enable(self):
        self.seen_players = []

    @on_event("player_connected")
    async def handle_player_connected(self, event: PlayerConnected):
        self.seen_players.append(event.player.eos_id)

    @periodic(seconds=1)
    async def periodic_poll(self):
        await self.rcon.list_players()
