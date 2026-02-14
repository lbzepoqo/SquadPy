"""AutoSeedLowPlayers - low-population automation for seeding windows."""

from __future__ import annotations

import time

from squadpy.plugin import Plugin, periodic


class AutoSeedLowPlayers(Plugin):
    name = "Auto Seed Low Players"
    description = "Automates low-population seeding actions"
    requires = ["rcon"]

    async def on_enable(self):
        self._is_low_population: bool | None = None
        self._last_announce_at: float = 0.0

    @periodic(seconds=30)
    async def check_low_population(self):
        players = await self.rcon.list_players()
        player_count = len(players)
        threshold = self._seed_player_threshold()
        is_low = player_count < threshold
        now = self._now()

        transitioned_to_low = (self._is_low_population is not True) and is_low
        transitioned_to_live = (self._is_low_population is True) and (not is_low)
        self._is_low_population = is_low

        if transitioned_to_low:
            self._last_announce_at = now
            await self._handle_enter_low_population(players, player_count, threshold)
            return

        if is_low:
            await self._handle_low_population_reminder(player_count, threshold, now)
            return

        if transitioned_to_live:
            await self._handle_exit_low_population(player_count, threshold)

    def _now(self) -> float:
        return time.monotonic()

    async def _handle_enter_low_population(
        self, players, player_count: int, threshold: int
    ) -> None:
        if bool(self.config.get("announce_transitions", True)):
            msg = self._format(
                str(
                    self.config.get(
                        "low_population_message",
                        "Low population mode active ({players}/{threshold}).",
                    )
                ),
                players=player_count,
                threshold=threshold,
            )
            await self.rcon.broadcast(msg)

        if bool(self.config.get("warn_unassigned_on_enter", False)):
            warning = str(
                self.config.get(
                    "unassigned_warning_message",
                    "Please join a squad while seeding.",
                )
            )
            for player in players:
                if player.squad_id == 0 and player.steam_id:
                    await self.rcon.warn(player.steam_id, warning)

        if bool(self.config.get("set_fog_on_transition", False)):
            seed_mode = self._fog_mode("seed_fog_mode", "1")
            if seed_mode is not None:
                await self.rcon.set_fog_of_war(seed_mode)

    async def _handle_low_population_reminder(
        self, player_count: int, threshold: int, now: float
    ) -> None:
        if not bool(self.config.get("announce_reminders", True)):
            return

        interval = self._positive_float(
            self.config.get("reminder_interval_seconds", 300), default=300.0
        )
        if interval <= 0:
            return
        if now - self._last_announce_at < interval:
            return

        self._last_announce_at = now
        msg = self._format(
            str(
                self.config.get(
                    "low_population_message",
                    "Low population mode active ({players}/{threshold}).",
                )
            ),
            players=player_count,
            threshold=threshold,
        )
        await self.rcon.broadcast(msg)

    async def _handle_exit_low_population(self, player_count: int, threshold: int) -> None:
        if bool(self.config.get("announce_transitions", True)):
            msg = self._format(
                str(
                    self.config.get(
                        "recovered_message",
                        "Population recovered ({players}/{threshold}).",
                    )
                ),
                players=player_count,
                threshold=threshold,
            )
            await self.rcon.broadcast(msg)

        if bool(self.config.get("set_fog_on_transition", False)):
            live_mode = self._fog_mode("live_fog_mode", "0")
            if live_mode is not None:
                await self.rcon.set_fog_of_war(live_mode)

    def _seed_player_threshold(self) -> int:
        try:
            value = int(self.config.get("seed_player_threshold", 50))
        except (TypeError, ValueError):
            return 50
        return value if value > 0 else 50

    def _positive_float(self, value, *, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else 0.0

    def _fog_mode(self, key: str, default: str) -> str | None:
        value = str(self.config.get(key, default)).strip().lower()
        if value in {"0", "1", "false", "true"}:
            return value
        return None

    def _format(self, template: str, **values: int) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template
