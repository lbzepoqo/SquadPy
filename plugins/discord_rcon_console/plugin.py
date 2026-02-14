"""DiscordRconConsole - privileged, gated RCON command execution from Discord."""

from __future__ import annotations

from squadpy.plugin import Plugin, slash_command


class DiscordRconConsole(Plugin):
    name = "Discord RCON Console"
    description = "Runs gated privileged RCON console commands from Discord"
    requires = ["rcon", "discord"]

    _DEFAULT_ALLOWED_COMMAND_PREFIXES = [
        "ShowCurrentMap",
        "ShowNextMap",
        "ListPlayers",
        "ListSquads",
        "AdminBroadcast",
        "AdminWarn",
        "AdminKick",
        "AdminBan",
        "AdminForceTeamChange",
        "AdminDemoteCommander",
        "AdminSetFogOfWar",
        "AdminSetNextLayer",
    ]

    @slash_command(name="rcon", description="Execute a gated privileged RCON command")
    async def rcon_cmd(self, interaction, command: str) -> None:
        normalized_command = command.strip()
        if not normalized_command:
            await interaction.response.send_message(
                "Command must not be empty.",
                ephemeral=True,
            )
            return

        actor = self._actor_identity(interaction)
        origin = self._origin_identity(interaction)

        if not self._actor_has_permission(interaction):
            await self._send_audit(
                actor=actor,
                origin=origin,
                command=normalized_command,
                outcome="rejected_role",
                detail="missing required role",
            )
            await interaction.response.send_message(
                "You do not have permission to run console commands.",
                ephemeral=True,
            )
            return

        if not self._is_command_allowed(normalized_command):
            await self._send_audit(
                actor=actor,
                origin=origin,
                command=normalized_command,
                outcome="rejected_policy",
                detail="command is not allow-listed",
            )
            await interaction.response.send_message(
                "Command is not allowed by policy.",
                ephemeral=True,
            )
            return

        try:
            response = await self.rcon.execute_privileged(
                normalized_command,
                actor=actor,
                origin=origin,
                policy=self._is_command_allowed,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            await self._send_audit(
                actor=actor,
                origin=origin,
                command=normalized_command,
                outcome="error",
                detail=error_text,
            )
            await interaction.response.send_message(
                f"Command failed: {error_text}",
                ephemeral=True,
            )
            return

        response_line = "Command executed."
        if bool(self.config.get("include_response", True)):
            response_preview = self._truncate(
                self._compact_text(response) or "(empty)",
                self._max_response_chars(),
            )
            response_line = f"Command executed. Response: {response_preview}"

        await self._send_audit(
            actor=actor,
            origin=origin,
            command=normalized_command,
            outcome="success",
            detail=self._truncate(self._compact_text(response) or "(empty)", 240),
        )
        await interaction.response.send_message(response_line, ephemeral=True)

    async def _send_audit(
        self,
        *,
        actor: str,
        origin: str,
        command: str,
        outcome: str,
        detail: str = "",
    ) -> None:
        audit_channel_id = self._positive_int(self.config.get("audit_channel_id", 0), 0)
        if audit_channel_id <= 0:
            return

        command_text = self._quote(self._truncate(self._compact_text(command), 220))
        line = (
            f"[RconConsole] actor={actor} origin={origin} "
            f"outcome={outcome} command={command_text}"
        )
        compact_detail = self._compact_text(detail)
        if compact_detail:
            line = f"{line} detail={self._quote(self._truncate(compact_detail, 220))}"
        await self.discord.send(audit_channel_id, content=line)

    def _actor_has_permission(self, interaction) -> bool:
        admin_role_id = self._positive_int(self.config.get("admin_role_id", 0), 0)
        if admin_role_id <= 0:
            return True

        user = getattr(interaction, "user", None)
        roles = getattr(user, "roles", [])
        user_role_ids = {getattr(role, "id", None) for role in roles}
        return admin_role_id in user_role_ids

    def _is_command_allowed(self, command: str) -> bool:
        if bool(self.config.get("allow_all_commands", False)):
            return True

        command_head = command.strip().split(maxsplit=1)[0].casefold()
        allowed_heads = self._allowed_command_heads()
        return command_head in allowed_heads

    def _allowed_command_heads(self) -> set[str]:
        configured = self.config.get(
            "allowed_command_prefixes", self._DEFAULT_ALLOWED_COMMAND_PREFIXES
        )
        if isinstance(configured, str):
            values = [configured]
        elif isinstance(configured, list):
            values = configured
        else:
            values = self._DEFAULT_ALLOWED_COMMAND_PREFIXES

        heads = {str(item).strip().casefold() for item in values if str(item).strip()}
        if not heads:
            return {item.casefold() for item in self._DEFAULT_ALLOWED_COMMAND_PREFIXES}
        return heads

    def _max_response_chars(self) -> int:
        value = self._positive_int(self.config.get("max_response_chars", 500), 500)
        if value < 64:
            return 64
        if value > 1500:
            return 1500
        return value

    def _actor_identity(self, interaction) -> str:
        user = getattr(interaction, "user", None)
        display_name = str(getattr(user, "display_name", "unknown")).strip() or "unknown"
        user_id = self._positive_int(getattr(user, "id", 0), 0)
        return f"{display_name}:{user_id}" if user_id > 0 else display_name

    @staticmethod
    def _origin_identity(interaction) -> str:
        guild_id = getattr(interaction, "guild_id", 0) or 0
        channel_id = getattr(interaction, "channel_id", 0) or 0
        return f"discord:guild={guild_id}:channel={channel_id}"

    @staticmethod
    def _compact_text(value: object) -> str:
        text = str(value or "")
        return " ".join(text.split())

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        if limit <= 3:
            return value[:limit]
        return f"{value[: limit - 3]}..."

    @staticmethod
    def _quote(value: str) -> str:
        escaped = value.replace('"', "'")
        return f"\"{escaped}\""

    @staticmethod
    def _positive_int(value: object, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
