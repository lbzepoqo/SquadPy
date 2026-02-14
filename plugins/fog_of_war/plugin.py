"""FogOfWar - safe, audited, and reversible fog-of-war automation."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from squadpy.plugin import Plugin, on_event, periodic


class FogOfWar(Plugin):
    name = "Fog Of War"
    description = "Automates fog mode transitions with safety guards and audit"
    requires = ["rcon"]

    async def on_enable(self):
        self._current_mode: str | None = None
        self._last_applied_fog_mode: str | None = None
        self._last_change_at: float = 0.0
        self._dynamic_threshold: int | None = None
        self._audit_records: list[dict[str, str]] = []
        self._max_audit_records: int = 1000

    @periodic(seconds=15)
    async def evaluate_fog_mode(self):
        players = await self.rcon.list_players()
        player_count = len(players)
        threshold = self._seed_player_threshold()
        target_mode = self._target_mode(player_count, threshold)
        if target_mode is None:
            return

        await self._apply_mode(
            target_mode,
            reason=f"population={player_count} threshold={threshold}",
            force=False,
        )

    @on_event("seeding_threshold_up")
    async def handle_seeding_threshold_up(self, event):
        self._set_dynamic_threshold(getattr(event, "new_threshold", None))
        self._audit(
            action="threshold_update",
            outcome="accepted",
            detail=f"new_threshold={self._seed_player_threshold()} source=up",
        )

    @on_event("seeding_threshold_down")
    async def handle_seeding_threshold_down(self, event):
        self._set_dynamic_threshold(getattr(event, "new_threshold", None))
        self._audit(
            action="threshold_update",
            outcome="accepted",
            detail=f"new_threshold={self._seed_player_threshold()} source=down",
        )

    @on_event("new_game")
    async def handle_new_game(self, event):
        if bool(self.config.get("reset_on_new_game", True)):
            self._current_mode = None
            self._audit(
                action="new_game",
                outcome="reset",
                detail="mode reset; next tick will re-evaluate",
            )

    async def on_disable(self):
        if not bool(self.config.get("revert_on_disable", True)):
            return

        revert_mode = self._revert_mode()
        await self._apply_mode(
            revert_mode,
            reason="plugin_disable_revert",
            force=True,
        )

    def recent_audit_records(self) -> list[dict[str, str]]:
        return list(self._audit_records)

    async def _apply_mode(self, mode: str, *, reason: str, force: bool) -> None:
        if mode not in {"seed", "live"}:
            return

        fog_mode = self._fog_mode_for(mode)
        if fog_mode is None:
            self._audit(
                action="apply_mode",
                outcome="invalid_config",
                detail=f"mode={mode} reason={reason}",
            )
            return

        if not force and self._last_applied_fog_mode == fog_mode:
            self._current_mode = mode
            return

        now = self._now()
        cooldown = self._change_cooldown_seconds()
        if (
            not force
            and self._last_change_at > 0
            and cooldown > 0
            and (now - self._last_change_at) < cooldown
        ):
            self._audit(
                action="apply_mode",
                outcome="cooldown_blocked",
                detail=f"mode={mode} reason={reason}",
            )
            return

        try:
            await self.rcon.set_fog_of_war(fog_mode)
        except Exception as exc:
            self._audit(
                action="apply_mode",
                outcome="error",
                detail=f"mode={mode} reason={reason} error={exc}",
            )
            return

        self._current_mode = mode
        self._last_applied_fog_mode = fog_mode
        self._last_change_at = now
        self._audit(
            action="apply_mode",
            outcome="success",
            detail=f"mode={mode} fog={fog_mode} reason={reason}",
        )

    def _target_mode(self, player_count: int, threshold: int) -> str | None:
        hysteresis = self._hysteresis_players()
        promote_to_live_at = threshold + hysteresis
        demote_to_seed_at = max(0, threshold - hysteresis)

        if self._current_mode is None:
            return "seed" if player_count < threshold else "live"

        if self._current_mode == "seed" and player_count >= promote_to_live_at:
            return "live"
        if self._current_mode == "live" and player_count <= demote_to_seed_at:
            return "seed"
        return None

    def _fog_mode_for(self, mode: str) -> str | None:
        if mode == "seed":
            configured = self.config.get("seed_fog_mode", "1")
        else:
            configured = self.config.get("live_fog_mode", "0")
        value = str(configured).strip().lower()
        if value in {"0", "false"}:
            return "0"
        if value in {"1", "true"}:
            return "1"
        return None

    def _revert_mode(self) -> str:
        configured = str(self.config.get("revert_to_mode", "live")).strip().lower()
        if configured in {"seed", "live"}:
            return configured
        return "live"

    def _seed_player_threshold(self) -> int:
        if self._dynamic_threshold is not None and self._dynamic_threshold > 0:
            return self._dynamic_threshold
        try:
            value = int(self.config.get("seed_player_threshold", 50))
        except (TypeError, ValueError):
            return 50
        return value if value > 0 else 50

    def _set_dynamic_threshold(self, value) -> None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return
        if parsed > 0:
            self._dynamic_threshold = parsed

    def _hysteresis_players(self) -> int:
        try:
            value = int(self.config.get("hysteresis_players", 2))
        except (TypeError, ValueError):
            return 2
        return value if value >= 0 else 2

    def _change_cooldown_seconds(self) -> float:
        try:
            value = float(self.config.get("change_cooldown_seconds", 30))
        except (TypeError, ValueError):
            return 30.0
        return value if value >= 0 else 30.0

    def _now(self) -> float:
        return time.monotonic()

    def _audit(self, *, action: str, outcome: str, detail: str = "") -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "outcome": outcome,
        }
        if detail:
            record["detail"] = detail

        self._audit_records.append(record)
        if len(self._audit_records) > self._max_audit_records:
            self._audit_records = self._audit_records[-self._max_audit_records :]
