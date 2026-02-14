"""SwitchCommand - allows players to request team switches via chat."""

from __future__ import annotations

import math
import time

from squadpy.plugin import Plugin, on_event


class SwitchCommand(Plugin):
    name = "Switch Command"
    description = "User-triggered team switch command with cooldown checks"
    requires = ["rcon"]

    async def on_enable(self):
        self._last_used: dict[str, float] = {}

    @on_event("chat_message")
    async def handle_chat(self, event):
        command = self._command_token()
        if not command:
            return

        message = str(getattr(event, "message", "")).strip()
        if message.lower() != command:
            return

        channel = str(getattr(event, "channel", "")).strip()
        if not self._channel_allowed(channel):
            return

        actor_id = self._actor_id(event)
        if not actor_id:
            return

        blocked, remaining = self._cooldown_blocked(actor_id)
        if blocked:
            cooldown_msg = self._format(
                str(
                    self.config.get(
                        "cooldown_message",
                        "You can use {command} again in {remaining}s.",
                    )
                ),
                command=command,
                remaining=str(max(1, math.ceil(remaining))),
                cooldown=str(math.ceil(self._cooldown_seconds())),
            )
            await self.rcon.warn(actor_id, cooldown_msg)
            return

        await self.rcon.switch_team(actor_id)
        self._last_used[actor_id] = self._now()

        if bool(self.config.get("notify_on_success", True)):
            success_msg = self._format(
                str(
                    self.config.get(
                        "success_message",
                        "Team switch requested. Please wait before requesting again.",
                    )
                ),
                command=command,
                cooldown=str(math.ceil(self._cooldown_seconds())),
            )
            await self.rcon.warn(actor_id, success_msg)

    def _actor_id(self, event) -> str:
        steam_id = str(getattr(event, "steam_id", "")).strip()
        if steam_id:
            return steam_id
        return str(getattr(event, "eos_id", "")).strip()

    def _command_token(self) -> str:
        configured = str(self.config.get("command", "!switch")).strip().lower()
        return configured or "!switch"

    def _channel_allowed(self, channel: str) -> bool:
        raw = self.config.get("allowed_channels", [])
        if not isinstance(raw, list) or not raw:
            return True

        allowed = {
            str(item).strip().lower()
            for item in raw
            if str(item).strip()
        }
        if not allowed:
            return True
        return channel.lower() in allowed

    def _cooldown_seconds(self) -> float:
        try:
            value = float(self.config.get("cooldown_seconds", 300))
        except (TypeError, ValueError):
            return 300.0
        return value if value > 0 else 0.0

    def _cooldown_blocked(self, actor_id: str) -> tuple[bool, float]:
        cooldown = self._cooldown_seconds()
        if cooldown <= 0:
            return False, 0.0

        last_used = self._last_used.get(actor_id)
        if last_used is None:
            return False, 0.0

        elapsed = self._now() - last_used
        if elapsed >= cooldown:
            return False, 0.0
        return True, cooldown - elapsed

    def _now(self) -> float:
        return time.monotonic()

    def _format(self, template: str, **values: str) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template
