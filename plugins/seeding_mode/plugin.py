"""SeedingMode - manages seed/live mode transitions from player count."""

from __future__ import annotations

from squadpy.plugin import Plugin, on_event, periodic


class SeedingMode(Plugin):
    name = "Seeding Mode"
    description = "Tracks seed/live mode from player thresholds"
    requires = ["rcon"]

    async def on_enable(self):
        self._mode: str | None = None

    @property
    def mode(self) -> str | None:
        return self._mode

    @periodic(seconds=30)
    async def evaluate_mode(self):
        players = await self.rcon.list_players()
        player_count = len(players)
        threshold = self._seed_player_threshold()
        next_mode = "seed" if player_count < threshold else "live"

        previous_mode = self._mode
        changed = previous_mode is not None and previous_mode != next_mode
        initial = previous_mode is None
        self._mode = next_mode

        if not changed and not (initial and self._announce_initial_mode()):
            return

        if bool(self.config.get("announce_transitions", True)):
            await self.rcon.broadcast(
                self._transition_message(next_mode, player_count, threshold)
            )

        if bool(self.config.get("set_fog_of_war_on_transition", False)):
            fog_mode = self._transition_fog_mode(next_mode)
            if fog_mode is not None:
                await self.rcon.set_fog_of_war(fog_mode)

    @on_event("new_game")
    async def handle_new_game(self, event):
        if bool(self.config.get("reset_on_new_game", True)):
            self._mode = None

    def _seed_player_threshold(self) -> int:
        try:
            threshold = int(self.config.get("seed_player_threshold", 50))
        except (TypeError, ValueError):
            return 50
        return threshold if threshold > 0 else 50

    def _announce_initial_mode(self) -> bool:
        return bool(self.config.get("announce_initial_mode", False))

    def _transition_message(self, mode: str, player_count: int, threshold: int) -> str:
        if mode == "seed":
            template = str(
                self.config.get(
                    "seed_mode_message",
                    "Seeding mode active ({players}/{threshold})",
                )
            )
        else:
            template = str(
                self.config.get(
                    "live_mode_message",
                    "Live mode active ({players}/{threshold})",
                )
            )
        try:
            return template.format(players=player_count, threshold=threshold, mode=mode)
        except (KeyError, ValueError):
            return template

    def _transition_fog_mode(self, mode: str) -> str | bool | None:
        if mode == "seed":
            configured = self.config.get("seed_fog_mode", "1")
        else:
            configured = self.config.get("live_fog_mode", "0")

        value = str(configured).strip().lower()
        if value in {"0", "1", "false", "true"}:
            return value
        return None
