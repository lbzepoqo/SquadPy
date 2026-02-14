"""ChatCommands - in-game command parser with role gates and cooldowns."""

from __future__ import annotations

import math
import time

from squadpy.plugin import Plugin, on_event


class ChatCommands(Plugin):
    name = "Chat Commands"
    description = "Role-gated in-game chat commands for moderation actions"
    requires = ["rcon"]

    _DEFAULT_COMMANDS = {
        "broadcast": {"min_role": "mod", "cooldown_seconds": 5},
        "warn": {"min_role": "mod", "cooldown_seconds": 5},
        "kick": {"min_role": "admin", "cooldown_seconds": 10},
    }

    async def on_enable(self):
        self._last_used: dict[tuple[str, str], float] = {}

    @on_event("chat_message")
    async def handle_chat(self, event):
        prefix = str(self.config.get("command_prefix", "!")).strip()
        if not prefix:
            return
        if not event.message.startswith(prefix):
            return

        body = event.message[len(prefix):].strip()
        if not body:
            return

        parts = body.split()
        command = parts[0].lower()
        args = parts[1:]
        if command not in self._DEFAULT_COMMANDS:
            return

        actor_id = event.steam_id
        if not actor_id:
            return

        command_config = self._command_config(command)
        actor_role = self._role_for_player(actor_id)
        min_role = str(command_config.get("min_role", "admin"))
        if not self._role_at_least(actor_role, min_role):
            denied = self._format(
                str(
                    self.config.get(
                        "denied_message",
                        "You do not have permission for !{command}.",
                    )
                ),
                command=command,
                role=actor_role,
            )
            await self.rcon.warn(actor_id, denied)
            return

        cooldown_seconds = self._positive_float(command_config.get("cooldown_seconds", 0), 0.0)
        blocked, remaining = self._cooldown_blocked(actor_id, command, cooldown_seconds)
        if blocked:
            cooldown_msg = self._format(
                str(
                    self.config.get(
                        "cooldown_message",
                        "Command !{command} is on cooldown ({remaining}s).",
                    )
                ),
                command=command,
                remaining=str(max(1, math.ceil(remaining))),
            )
            await self.rcon.warn(actor_id, cooldown_msg)
            return

        ok = await self._execute_command(command, args)
        if ok:
            self._last_used[(actor_id, command)] = time.monotonic()
            return

        usage_msg = self._format(
            str(self.config.get("usage_message", "Usage: {usage}")),
            usage=self._usage_for(command),
        )
        await self.rcon.warn(actor_id, usage_msg)

    async def _execute_command(self, command: str, args: list[str]) -> bool:
        if command == "broadcast":
            message = " ".join(args).strip()
            if not message:
                return False
            await self.rcon.broadcast(message)
            return True

        if command == "warn":
            if len(args) < 2:
                return False
            target = args[0]
            reason = " ".join(args[1:]).strip()
            if not reason:
                return False
            await self.rcon.warn(target, reason)
            return True

        if command == "kick":
            if len(args) < 2:
                return False
            target = args[0]
            reason = " ".join(args[1:]).strip()
            if not reason:
                return False
            await self.rcon.kick(target, reason)
            return True

        return False

    def _usage_for(self, command: str) -> str:
        prefix = str(self.config.get("command_prefix", "!")).strip() or "!"
        if command == "broadcast":
            return f"{prefix}broadcast <message>"
        if command == "warn":
            return f"{prefix}warn <player_id> <reason>"
        if command == "kick":
            return f"{prefix}kick <player_id> <reason>"
        return f"{prefix}{command}"

    def _command_config(self, command: str) -> dict:
        config_commands = self.config.get("commands", {})
        configured = {}
        if isinstance(config_commands, dict):
            maybe_command_config = config_commands.get(command, {})
            if isinstance(maybe_command_config, dict):
                configured = maybe_command_config

        merged = dict(self._DEFAULT_COMMANDS.get(command, {}))
        merged.update(configured)
        return merged

    def _role_for_player(self, steam_id: str) -> str:
        role_map = self.config.get("user_roles", {})
        if not isinstance(role_map, dict):
            return str(self.config.get("default_role", "user"))
        role = role_map.get(steam_id, self.config.get("default_role", "user"))
        return str(role)

    def _role_at_least(self, role: str, required: str) -> bool:
        order = self.config.get("roles_order", ["user", "mod", "admin"])
        if not isinstance(order, list) or not order:
            order = ["user", "mod", "admin"]

        try:
            role_index = order.index(role)
        except ValueError:
            role_index = -1
        try:
            required_index = order.index(required)
        except ValueError:
            required_index = len(order)
        return role_index >= required_index and role_index >= 0

    def _cooldown_blocked(
        self, actor_id: str, command: str, cooldown_seconds: float
    ) -> tuple[bool, float]:
        if cooldown_seconds <= 0:
            return False, 0.0

        key = (actor_id, command)
        last_used = self._last_used.get(key)
        if last_used is None:
            return False, 0.0

        elapsed = time.monotonic() - last_used
        if elapsed >= cooldown_seconds:
            return False, 0.0
        return True, cooldown_seconds - elapsed

    def _positive_float(self, value, fallback: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed > 0 else 0.0

    def _format(self, template: str, **values: str) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template
