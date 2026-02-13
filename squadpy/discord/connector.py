"""Discord connector — wraps discord.py bot as a core service."""

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from squadpy.config import DiscordConfig

logger = logging.getLogger("squadpy.discord")


class DiscordConnector:
    """Core Discord service wrapping a discord.py Bot."""

    def __init__(self, config: DiscordConfig):
        self._config = config
        self.guild_id = config.guild_id

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        self.bot = commands.Bot(
            command_prefix=config.command_prefix,
            intents=intents,
        )
        self._ready = asyncio.Event()
        self._bot_task: asyncio.Task | None = None
        self._interaction_handlers: dict[str, Any] = {}
        self._slash_commands: dict[str, app_commands.Command] = {}
        self.guild: discord.Guild | None = None

        @self.bot.event
        async def on_ready():
            self.guild = self.bot.get_guild(self.guild_id)
            if self.guild:
                logger.info("Discord connected: %s (guild: %s)", self.bot.user, self.guild.name)
            else:
                logger.warning("Discord connected but guild %s not found", self.guild_id)
            self._ready.set()

        @self.bot.event
        async def on_interaction(interaction: discord.Interaction):
            if interaction.type == discord.InteractionType.component:
                custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
                handler = self._interaction_handlers.get(custom_id)
                if handler:
                    try:
                        await handler(interaction)
                    except Exception:
                        logger.exception("Error in interaction handler for %s", custom_id)
            elif interaction.type == discord.InteractionType.modal_submit:
                custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
                handler = self._interaction_handlers.get(custom_id)
                if handler:
                    try:
                        await handler(interaction)
                    except Exception:
                        logger.exception("Error in modal handler for %s", custom_id)

    async def start(self, token: str) -> None:
        """Start the Discord bot as an asyncio task."""
        self._bot_task = asyncio.create_task(self.bot.start(token))
        logger.info("Discord bot starting...")

    async def wait_until_ready(self) -> None:
        """Wait until the bot is connected and ready."""
        await self._ready.wait()

    async def close(self) -> None:
        """Shut down the Discord bot."""
        await self.bot.close()
        if self._bot_task:
            self._bot_task.cancel()
        logger.info("Discord bot closed")

    # --- Convenience methods ---

    async def send(
        self,
        channel_id: int,
        content: str | None = None,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> discord.Message | None:
        """Send a message to a channel."""
        channel = self.bot.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            logger.warning("Channel %s not found or not messageable", channel_id)
            return None
        kwargs: dict[str, Any] = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view
        return await channel.send(**kwargs)

    async def edit_message(self, message: discord.Message, **kwargs) -> discord.Message:
        """Edit an existing message."""
        return await message.edit(**kwargs)

    async def create_thread(
        self, message: discord.Message, name: str
    ) -> discord.Thread:
        """Create a thread from a message."""
        return await message.create_thread(name=name)

    def get_channel(self, channel_id: int):
        """Get a channel by ID."""
        return self.bot.get_channel(channel_id)

    # --- Interaction routing ---

    def register_slash_command(
        self, plugin_name: str, func, *, name: str, description: str = ""
    ) -> None:
        """Register a slash command for a plugin."""
        guild = discord.Object(id=self.guild_id)
        if self.bot.tree.get_command(name, guild=guild) is not None:
            logger.warning(
                "Skipped slash command /%s for %s: name already registered",
                name,
                plugin_name,
            )
            return

        cmd = app_commands.Command(
            name=name,
            description=description or name,
            callback=func,
        )
        try:
            self.bot.tree.add_command(cmd, guild=guild)
        except app_commands.CommandAlreadyRegistered:
            logger.warning(
                "Skipped slash command /%s for %s: command already registered",
                name,
                plugin_name,
            )
            return

        key = f"{plugin_name}:{name}"
        self._slash_commands[key] = cmd
        logger.debug("Registered slash command /%s for %s", name, plugin_name)

    def register_interaction_handler(
        self,
        plugin_name: str,
        event_type: str,
        custom_id: str | None,
        func,
    ) -> None:
        """Register a Discord interaction handler with namespaced custom_id."""
        if custom_id:
            namespaced_id = f"{plugin_name}:{custom_id}"
        else:
            namespaced_id = f"{plugin_name}:__{event_type}"
        self._interaction_handlers[namespaced_id] = func
        logger.debug("Registered %s handler %s for %s", event_type, namespaced_id, plugin_name)

    def unregister_plugin(self, plugin_name: str) -> None:
        """Remove all handlers for a plugin (used during hot-reload)."""
        prefix = f"{plugin_name}:"
        to_remove = [k for k in self._interaction_handlers if k.startswith(prefix)]
        for k in to_remove:
            del self._interaction_handlers[k]
        cmd_keys = [k for k in self._slash_commands if k.startswith(prefix)]
        for k in cmd_keys:
            cmd = self._slash_commands.pop(k)
            self.bot.tree.remove_command(cmd.name, guild=discord.Object(id=self.guild_id))
        logger.debug("Unregistered all handlers for %s", plugin_name)

    async def sync_commands(self) -> None:
        """Sync slash commands to the guild."""
        await self.bot.tree.sync(guild=discord.Object(id=self.guild_id))
        logger.info("Synced %d slash commands to guild", len(self._slash_commands))

    def namespace_custom_id(self, plugin_name: str, custom_id: str) -> str:
        """Generate a namespaced custom_id for a plugin's UI component."""
        return f"{plugin_name}:{custom_id}"
