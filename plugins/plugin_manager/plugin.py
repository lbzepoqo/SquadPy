"""Built-in Plugin Manager — /status, /plugins, /reload slash commands."""

import datetime

from squadpy.plugin import Plugin, slash_command


class PluginManager(Plugin):
    name = "Plugin Manager"
    description = "Server management slash commands"
    requires = ["rcon", "discord"]

    async def on_enable(self):
        self._start_time = datetime.datetime.now()

    @slash_command(name="status", description="Show server status")
    async def status_cmd(self, interaction):
        uptime = datetime.datetime.now() - self._start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        lines = [
            f"**SquadPy v{self.server.version}**",
            f"Uptime: {hours}h {minutes}m {seconds}s",
        ]
        await interaction.response.send_message("\n".join(lines))

    @slash_command(name="plugins", description="List loaded plugins")
    async def plugins_cmd(self, interaction):
        plugins = self.server._loaded_plugins
        if not plugins:
            await interaction.response.send_message("No plugins loaded.")
            return

        lines = []
        for lp in plugins:
            status = lp.status.value
            lines.append(f"**{lp.name}** — {status}")
            if lp.error:
                lines.append(f"  Error: {lp.error}")

        await interaction.response.send_message("\n".join(lines))

    @slash_command(name="reload", description="Reload a plugin")
    async def reload_cmd(self, interaction, plugin_name: str):
        admin_role_id = self.config.get("admin_role_id", 0)
        user_role_ids = {role.id for role in interaction.user.roles}

        if admin_role_id and admin_role_id not in user_role_ids:
            await interaction.response.send_message(
                "You do not have permission to reload plugins.", ephemeral=True,
            )
            return

        success, error = await self.server.reload_plugin(plugin_name)
        if success:
            await interaction.response.send_message(f"Plugin `{plugin_name}` reloaded.")
        else:
            await interaction.response.send_message(f"Failed to reload `{plugin_name}`: {error}")
