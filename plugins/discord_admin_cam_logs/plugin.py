"""DiscordAdminCamLogs - posts admin camera possession lifecycle events to Discord."""

from squadpy.events.types import AdminCamPossess, AdminCamUnpossess
from squadpy.plugin import Plugin, on_event


class DiscordAdminCamLogs(Plugin):
    name = "Discord Admin Cam Logs"
    description = "Posts admin cam possess/unpossess events to a Discord channel"
    requires = ["discord"]

    @on_event("admin_cam_possess")
    async def handle_admin_cam_possess(self, event: AdminCamPossess):
        await self._send_log("possess", event)

    @on_event("admin_cam_unpossess")
    async def handle_admin_cam_unpossess(self, event: AdminCamUnpossess):
        await self._send_log("unpossess", event)

    async def _send_log(self, action: str, event: AdminCamPossess | AdminCamUnpossess) -> None:
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        admin_name = event.admin.name or "UnknownAdmin"
        admin_steam_id = event.admin.steam_id or "unknown"
        target = event.target or "unknown"

        include_context = self.config.get("include_context", True)
        context_text = ""
        if include_context and event.context:
            context_parts = [f"{key}={value}" for key, value in sorted(event.context.items())]
            context_text = f" | context: {', '.join(context_parts)}"

        content = (
            f"[AdminCam] {admin_name} ({admin_steam_id}) {action} target={target}{context_text}"
        )
        await self.discord.send(channel_id, content=content)
