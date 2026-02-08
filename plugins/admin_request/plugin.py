"""AdminRequest — in-game !admin creates Discord ticket with claim button and thread."""

import datetime

import discord

from squadpy.plugin import Plugin, on_event, on_discord, periodic
from squadpy.rcon.types import RconPlayer


class AdminRequest(Plugin):
    name = "Admin Request"
    description = "In-game admin request system with Discord tickets"
    requires = ["rcon", "discord"]

    async def on_enable(self):
        self._tickets: dict[int, dict] = {}  # thread_id -> ticket info
        self._player_cache: dict[str, RconPlayer] = {}  # steam_id -> player

    @periodic(seconds=30)
    async def refresh_players(self):
        players = await self.rcon.list_players()
        self._player_cache = {p.steam_id: p for p in players}

    @on_event("chat_message")
    async def handle_chat(self, event):
        prefix = self.config.get("command_prefix", "!admin")
        if not event.message.startswith(prefix):
            return

        reason = event.message[len(prefix):].strip() or "No reason given"
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        embed = discord.Embed(
            title="Admin Request",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Player", value=event.player_name, inline=True)
        embed.add_field(name="Steam ID", value=event.steam_id, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        button = discord.ui.Button(
            label="Claim",
            style=discord.ButtonStyle.primary,
            custom_id=self.discord.namespace_custom_id("admin_request", "claim_ticket"),
        )
        view = discord.ui.View(timeout=None)
        view.add_item(button)

        ping_role_id = self.config.get("ping_role_id", 0)
        content = f"<@&{ping_role_id}>" if ping_role_id else None

        message = await self.discord.send(channel_id, content=content, embed=embed, view=view)
        if not message:
            return

        thread = await self.discord.create_thread(message, name=f"Ticket: {event.player_name}")
        self._tickets[thread.id] = {
            "steam_id": event.steam_id,
            "player_name": event.player_name,
            "claimed_by": None,
        }

        await self.rcon.warn(event.steam_id, "Your admin request has been submitted")

    @on_discord("button_click", custom_id="claim_ticket")
    async def handle_claim(self, interaction):
        # Find ticket by looking up the thread from the message
        message = interaction.message
        if not message:
            return

        embed = message.embeds[0] if message.embeds else None
        if not embed:
            return

        embed.add_field(name="Claimed by", value=interaction.user.display_name, inline=True)
        embed.color = discord.Color.blue()

        await interaction.response.edit_message(embed=embed, view=None)

        # Update ticket claimed_by
        for ticket in self._tickets.values():
            if ticket.get("claimed_by") is None:
                ticket["claimed_by"] = interaction.user.display_name
                break

    @on_discord("thread_message")
    async def handle_thread_msg(self, interaction):
        thread_id = interaction.channel.id if interaction.channel else None
        if not thread_id or thread_id not in self._tickets:
            return

        ticket = self._tickets[thread_id]
        steam_id = ticket["steam_id"]

        if steam_id not in self._player_cache:
            return

        author = interaction.author.display_name if hasattr(interaction, "author") else "Admin"
        content = interaction.content if hasattr(interaction, "content") else ""
        if content:
            await self.rcon.warn(steam_id, f"[Admin] {author}: {content}")
