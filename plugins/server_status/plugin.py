"""ServerStatus — persistent Discord embed showing live server info."""

import datetime

import discord

from squadpy.plugin import Plugin, on_event, periodic


class ServerStatus(Plugin):
    name = "Server Status"
    description = "Live server status embed in Discord"
    requires = ["rcon", "discord"]

    async def on_enable(self):
        self._message = None
        self._tick_rate = 0.0
        self._current_map = None
        self._current_layer = None
        self._factions = None

        channel_id = self.config.get("channel_id", 0)
        if channel_id:
            embed = self._build_embed(0, 0, "Loading...", "Loading...", "", None, self._tick_rate)
            self._message = await self.discord.send(channel_id, embed=embed)

    @periodic(seconds=60)
    async def update_status(self):
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        players = await self.rcon.list_players()
        current_map = await self.rcon.show_current_map()
        next_map = await self.rcon.show_next_map()

        level = current_map.level if current_map else (self._current_map or "Unknown")
        layer = current_map.layer if current_map else (self._current_layer or "Unknown")
        factions = current_map.factions if current_map else (self._factions or "")
        squads_in = {p.squad_id for p in players if p.squad_id != 0}

        embed = self._build_embed(
            len(players), len(squads_in), level, layer, factions, next_map, self._tick_rate,
        )

        if self._message:
            try:
                self._message = await self.discord.edit_message(self._message, embed=embed)
                return
            except Exception:
                self.logger.warning("Failed to edit status message, posting new one")
                self._message = None

        self._message = await self.discord.send(channel_id, embed=embed)

    @on_event("server_tick_rate")
    async def cache_tick_rate(self, event):
        self._tick_rate = event.tick_rate

    @on_event("new_game")
    async def cache_map(self, event):
        self._current_map = getattr(event, "map_classname", None)
        self._current_layer = getattr(event, "layer_classname", None)

    async def on_disable(self):
        if self._message:
            try:
                embed = discord.Embed(
                    title="Server Status",
                    description="Offline",
                    color=discord.Color.dark_grey(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                await self.discord.edit_message(self._message, embed=embed)
            except Exception:
                pass

    def _build_embed(self, player_count, squad_count, level, layer, factions, next_map, tick_rate):
        embed = discord.Embed(
            title="Server Status",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Map", value=level, inline=True)
        embed.add_field(name="Layer", value=layer, inline=True)
        if factions:
            embed.add_field(name="Factions", value=factions, inline=True)
        embed.add_field(name="Players", value=str(player_count), inline=True)
        embed.add_field(name="Squads", value=str(squad_count), inline=True)
        embed.add_field(name="Tick Rate", value=f"{tick_rate:.1f}", inline=True)
        if next_map:
            embed.add_field(name="Next Map", value=f"{next_map.level} / {next_map.layer}", inline=False)
        else:
            embed.add_field(name="Next Map", value="Not set (voting)", inline=False)
        return embed
