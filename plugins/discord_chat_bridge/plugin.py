"""DiscordChatBridge — two-way bridge between in-game chat and a Discord channel."""

from squadpy.plugin import Plugin, on_event


class DiscordChatBridge(Plugin):
    name = "Discord Chat Bridge"
    description = "Bridges in-game chat to a Discord channel and vice versa"
    requires = ["rcon", "discord"]

    async def on_enable(self):
        self._listener = self._on_discord_message
        self.discord.bot.add_listener(self._listener, "on_message")

    async def on_disable(self):
        self.discord.bot.remove_listener(self._listener, "on_message")

    @on_event("chat_message")
    async def relay_to_discord(self, event):
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        chat_channels = self.config.get("chat_channels", ["ChatAll"])
        if event.channel not in chat_channels:
            return

        show_prefix = self.config.get("show_channel_prefix", True)
        if show_prefix:
            prefix_map = {
                "ChatAll": "[All]",
                "ChatTeam": "[Team]",
                "ChatSquad": "[Squad]",
                "ChatAdmin": "[Admin]",
            }
            prefix = prefix_map.get(event.channel, f"[{event.channel}]")
            text = f"{prefix} **{event.player_name}**: {event.message}"
        else:
            text = f"**{event.player_name}**: {event.message}"

        await self.discord.send(channel_id, content=text)

    async def _on_discord_message(self, message):
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return
        if message.channel.id != channel_id:
            return
        if message.author.bot:
            return

        fmt = self.config.get("discord_to_game_format", "[Discord] {author}: {message}")
        text = fmt.format(author=message.author.display_name, message=message.content)
        await self.rcon.broadcast(text)
