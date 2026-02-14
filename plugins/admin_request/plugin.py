"""AdminRequest - in-game !admin creates Discord tickets with claim/close lifecycle."""

import datetime

import discord

from squadpy.plugin import Plugin, on_discord, on_event, periodic
from squadpy.rcon.types import RconPlayer


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


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

    @periodic(seconds=30)
    async def expire_tickets(self):
        timeout_minutes = int(self.config.get("ticket_timeout_minutes", 60))
        if timeout_minutes <= 0:
            return

        cutoff = _utcnow() - datetime.timedelta(minutes=timeout_minutes)
        stale_ticket_ids: list[int] = []
        for thread_id, ticket in self._tickets.items():
            created_at = ticket.get("created_at")
            if isinstance(created_at, datetime.datetime) and created_at <= cutoff:
                stale_ticket_ids.append(thread_id)

        for thread_id in stale_ticket_ids:
            await self._close_ticket(
                thread_id,
                closed_by="system",
                reason="timeout",
                notify_thread=True,
                notify_player=True,
            )

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
            timestamp=_utcnow(),
        )
        embed.add_field(name="Player", value=event.player_name, inline=True)
        embed.add_field(name="Steam ID", value=event.steam_id, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        view = self._ticket_controls(include_claim=True, include_close=True)

        ping_role_id = self.config.get("ping_role_id", 0)
        content = f"<@&{ping_role_id}>" if ping_role_id else None

        message = await self.discord.send(channel_id, content=content, embed=embed, view=view)
        if not message:
            return

        thread = await self.discord.create_thread(message, name=f"Ticket: {event.player_name}")
        self._tickets[thread.id] = {
            "steam_id": event.steam_id,
            "player_name": event.player_name,
            "message_id": message.id,
            "claimed_by": None,
            "created_at": _utcnow(),
        }

        submitted_warning = self.config.get(
            "submitted_warning_message",
            "Your admin request has been submitted",
        )
        await self.rcon.warn(event.steam_id, submitted_warning)

    @on_discord("button_click", custom_id="claim_ticket")
    async def handle_claim(self, interaction):
        resolved = self._find_ticket(interaction)
        if resolved is None:
            return

        thread_id, ticket = resolved
        claimed_by = ticket.get("claimed_by")
        if claimed_by:
            await interaction.response.send_message(
                f"Ticket is already claimed by {claimed_by}.",
                ephemeral=True,
            )
            return

        admin_name = self._display_name(getattr(interaction, "user", None), fallback="Admin")
        ticket["claimed_by"] = admin_name
        ticket["claimed_at"] = _utcnow()

        message = getattr(interaction, "message", None)
        embed = message.embeds[0] if message and message.embeds else None
        if embed:
            embed.add_field(name="Claimed by", value=admin_name, inline=True)
            embed.color = discord.Color.blue()
            await interaction.response.edit_message(
                embed=embed,
                view=self._ticket_controls(include_claim=False, include_close=True),
            )
            return

        await interaction.response.send_message("Ticket claimed.", ephemeral=True)

    @on_discord("button_click", custom_id="close_ticket")
    async def handle_close(self, interaction):
        resolved = self._find_ticket(interaction)
        if resolved is None:
            return

        thread_id, _ticket = resolved
        closed_by = self._display_name(getattr(interaction, "user", None), fallback="Admin")
        await self._close_ticket(
            thread_id,
            closed_by=closed_by,
            reason="manual",
            notify_thread=False,
            notify_player=False,
        )

        message = getattr(interaction, "message", None)
        embed = message.embeds[0] if message and message.embeds else None
        if embed:
            embed.add_field(name="Closed by", value=closed_by, inline=True)
            embed.color = discord.Color.green()
            await interaction.response.edit_message(embed=embed, view=None)
            return

        await interaction.response.send_message("Ticket closed.", ephemeral=True)

    @on_discord("thread_message")
    async def handle_thread_msg(self, interaction):
        thread_id = interaction.channel.id if interaction.channel else None
        if not thread_id or thread_id not in self._tickets:
            return

        author = self._display_name(getattr(interaction, "author", None), fallback="Admin")
        content = interaction.content if hasattr(interaction, "content") else ""
        content = content.strip()
        if not content:
            return

        close_command = self.config.get("close_command", "!close")
        if content == close_command:
            await self._close_ticket(
                thread_id,
                closed_by=author,
                reason="manual",
                notify_thread=True,
                notify_player=False,
            )
            return

        ticket = self._tickets[thread_id]
        steam_id = ticket.get("steam_id", "")
        if steam_id not in self._player_cache:
            return

        relay_format = self.config.get("relay_format", "[Admin] {author}: {content}")
        await self.rcon.warn(steam_id, relay_format.format(author=author, content=content))

    def _ticket_controls(self, *, include_claim: bool, include_close: bool) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        if include_claim:
            view.add_item(
                discord.ui.Button(
                    label="Claim",
                    style=discord.ButtonStyle.primary,
                    custom_id=self.discord.namespace_custom_id("admin_request", "claim_ticket"),
                )
            )
        if include_close:
            view.add_item(
                discord.ui.Button(
                    label="Close",
                    style=discord.ButtonStyle.danger,
                    custom_id=self.discord.namespace_custom_id("admin_request", "close_ticket"),
                )
            )
        return view

    def _find_ticket(self, interaction) -> tuple[int, dict] | None:
        message = getattr(interaction, "message", None)
        message_id = getattr(message, "id", None)
        if message_id is not None:
            for thread_id, candidate in self._tickets.items():
                if candidate.get("message_id") == message_id:
                    return thread_id, candidate

        channel = getattr(interaction, "channel", None)
        channel_id = getattr(channel, "id", None)
        if channel_id and channel_id in self._tickets:
            return channel_id, self._tickets[channel_id]
        return None

    def _display_name(self, actor, fallback: str) -> str:
        if actor is None:
            return fallback
        return getattr(actor, "display_name", fallback)

    async def _close_ticket(
        self,
        thread_id: int,
        *,
        closed_by: str,
        reason: str,
        notify_thread: bool,
        notify_player: bool,
    ) -> dict | None:
        ticket = self._tickets.pop(thread_id, None)
        if ticket is None:
            return None

        if notify_thread:
            await self.discord.send(
                thread_id,
                content=f"Ticket closed by {closed_by} ({reason}).",
            )

        if notify_player and reason == "timeout":
            steam_id = ticket.get("steam_id", "")
            if steam_id in self._player_cache:
                timeout_warning = self.config.get(
                    "timeout_warning_message",
                    "Your admin request timed out. Please submit a new one if you still need help.",
                )
                await self.rcon.warn(steam_id, timeout_warning)

        return ticket
