"""DiscordAdminBroadcast - privileged slash command to broadcast to game chat."""

from squadpy.plugin import Plugin, slash_command


class DiscordAdminBroadcast(Plugin):
    name = "Discord Admin Broadcast"
    description = "Runs privileged Discord -> in-game broadcast actions"
    requires = ["rcon", "discord"]

    @slash_command(name="broadcast", description="Broadcast a message to the game server")
    async def broadcast_cmd(self, interaction, message: str):
        if not message.strip():
            await interaction.response.send_message(
                "Message must not be empty.",
                ephemeral=True,
            )
            return
        message = message.strip()

        admin_role_id = self.config.get("admin_role_id", 0)
        if admin_role_id:
            roles = getattr(interaction.user, "roles", [])
            user_role_ids = {role.id for role in roles}
            if admin_role_id not in user_role_ids:
                await interaction.response.send_message(
                    "You do not have permission to broadcast.",
                    ephemeral=True,
                )
                return

        await self.rcon.broadcast(message)

        actor_name = getattr(interaction.user, "display_name", "unknown")
        audit_channel_id = self.config.get("audit_channel_id", 0)
        if audit_channel_id:
            await self.discord.send(
                audit_channel_id,
                content=f"[Broadcast] actor={actor_name} message={message}",
            )

        await interaction.response.send_message(
            "Broadcast sent.",
            ephemeral=True,
        )
