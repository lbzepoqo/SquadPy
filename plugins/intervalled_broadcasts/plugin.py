"""IntervalledBroadcasts - scheduled periodic broadcasts with dedupe controls."""

from __future__ import annotations

import random
import time

from squadpy.plugin import Plugin, on_event, periodic


class IntervalledBroadcasts(Plugin):
    name = "Intervalled Broadcasts"
    description = "Sends scheduled broadcasts with optional message dedupe"
    requires = ["rcon"]

    async def on_enable(self):
        seed = self.config.get("random_seed")
        self._rng = random.Random(seed)
        self._next_run_at: float = 0.0
        self._message_index: int = 0
        self._last_message: str | None = None
        self._schedule_initial_run()

    @periodic(seconds=5)
    async def broadcast_tick(self):
        if not self._messages():
            return

        now = self._now()
        if now < self._next_run_at:
            return

        min_players = self._min_players()
        if min_players > 0:
            players = await self.rcon.list_players()
            if len(players) < min_players:
                self._next_run_at = now + self._interval_seconds()
                return

        message = self._next_message()
        if not message:
            self._next_run_at = now + self._interval_seconds()
            return

        await self.rcon.broadcast(message)
        self._last_message = message
        self._next_run_at = now + self._interval_seconds()

    @on_event("new_game")
    async def handle_new_game(self, event):
        if bool(self.config.get("reset_on_new_game", False)):
            self._message_index = 0
            self._last_message = None
            self._schedule_initial_run()

    def _schedule_initial_run(self) -> None:
        now = self._now()
        if bool(self.config.get("broadcast_on_start", False)):
            self._next_run_at = now
            return
        self._next_run_at = now + self._interval_seconds()

    def _next_message(self) -> str:
        messages = self._messages()
        if not messages:
            return ""

        mode = self._mode()
        dedupe = bool(self.config.get("dedupe_consecutive", True))

        if mode == "random":
            return self._next_random_message(messages, dedupe)
        return self._next_sequential_message(messages, dedupe)

    def _next_sequential_message(self, messages: list[str], dedupe: bool) -> str:
        size = len(messages)
        if size == 0:
            return ""

        for _ in range(size):
            candidate = messages[self._message_index % size]
            self._message_index = (self._message_index + 1) % size
            if not dedupe or candidate != self._last_message or size == 1:
                return candidate
        return messages[self._message_index % size]

    def _next_random_message(self, messages: list[str], dedupe: bool) -> str:
        if len(messages) == 1:
            return messages[0]
        if not dedupe:
            return self._rng.choice(messages)

        options = [message for message in messages if message != self._last_message]
        if not options:
            options = messages
        return self._rng.choice(options)

    def _messages(self) -> list[str]:
        raw = self.config.get("messages", [])
        if not isinstance(raw, list):
            return []

        messages: list[str] = []
        for item in raw:
            message = str(item).strip()
            if message:
                messages.append(message)
        return messages

    def _interval_seconds(self) -> float:
        try:
            value = float(self.config.get("interval_seconds", 300))
        except (TypeError, ValueError):
            return 300.0
        return value if value > 0 else 300.0

    def _min_players(self) -> int:
        try:
            value = int(self.config.get("min_players", 0))
        except (TypeError, ValueError):
            return 0
        return value if value > 0 else 0

    def _mode(self) -> str:
        configured = str(self.config.get("mode", "sequential")).strip().lower()
        if configured in {"sequential", "random"}:
            return configured
        return "sequential"

    def _now(self) -> float:
        return time.monotonic()
