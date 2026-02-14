"""HeliCrashBroadcast - detect likely helicopter crash kill clusters."""

from __future__ import annotations

import time
from collections import deque

from squadpy.layers import DEFAULT_LAYER_SOURCE_URL, LayerCatalog, LayerCatalogService
from squadpy.plugin import Plugin, on_event


class HeliCrashBroadcast(Plugin):
    name = "Heli Crash Broadcast"
    description = "Broadcasts likely helicopter crash incidents from death clusters"
    requires = ["rcon"]

    async def on_enable(self):
        self._recent_deaths: deque[tuple[float, str, str]] = deque()
        self._last_broadcast_at: float = 0.0
        self._layer_catalog = LayerCatalog.empty()

        if bool(self.config.get("fetch_helicopters_from_layer_source", True)):
            try:
                service = LayerCatalogService(
                    source_url=self._layer_source_url(),
                    timeout_seconds=self._http_timeout_seconds(),
                )
                self._layer_catalog = await service.fetch()
            except Exception as exc:
                self.logger.warning("Failed to load layer catalog from source: %s", exc)
                self._layer_catalog = LayerCatalog.empty()

    @on_event("player_died")
    async def handle_player_died(self, event):
        weapon = str(getattr(event, "weapon", "")).strip()
        if not self._is_heli_weapon(weapon):
            return

        now = self._now()
        victim_name = str(getattr(event, "victim_name", "")).strip() or "UnknownVictim"
        self._recent_deaths.append((now, weapon, victim_name))
        self._prune_recent(now)

        window = self._window_seconds()
        cutoff = now - window
        incident = [
            (timestamp, wpn, victim)
            for (timestamp, wpn, victim) in self._recent_deaths
            if timestamp >= cutoff and wpn == weapon
        ]

        min_victims = self._min_victims()
        if len(incident) < min_victims:
            return

        cooldown = self._cooldown_seconds()
        if cooldown > 0 and (now - self._last_broadcast_at) < cooldown:
            return

        victims = [victim for _, _, victim in incident]
        summary = self._format_broadcast(
            weapon=weapon,
            victim_count=len(victims),
            victims=victims,
            window_seconds=window,
        )
        await self.rcon.broadcast(summary)
        self._last_broadcast_at = now

    @on_event("new_game")
    async def handle_new_game(self, event):
        if bool(self.config.get("reset_on_new_game", True)):
            self._recent_deaths.clear()
            self._last_broadcast_at = 0.0

    def _is_heli_weapon(self, weapon: str) -> bool:
        normalized = weapon.casefold()
        if not normalized:
            return False
        if any(token in normalized for token in self._heli_tokens()):
            return True

        known_name_tokens = self._known_heli_name_tokens()
        return any(token in normalized for token in known_name_tokens)

    def _known_heli_name_tokens(self) -> set[str]:
        names = self._layer_catalog.helicopter_names | self._configured_heli_names()
        tokens: set[str] = set()
        for name in names:
            normalized = "".join(ch if ch.isalnum() else " " for ch in name.casefold())
            for token in normalized.split():
                if len(token) >= 3:
                    tokens.add(token)
        return tokens

    def _heli_tokens(self) -> list[str]:
        raw = self.config.get(
            "heli_weapon_tokens",
            ["loach", "heli", "helicopter", "mi8", "uh60", "littlebird", "blackhawk", "chopper"],
        )
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = raw
        else:
            values = []

        tokens = [str(item).strip().casefold() for item in values if str(item).strip()]
        if tokens:
            return tokens
        return ["loach", "heli", "helicopter", "mi8", "uh60", "littlebird", "blackhawk", "chopper"]

    def _configured_heli_names(self) -> set[str]:
        raw = self.config.get("helicopter_names", [])
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = raw
        else:
            values = []

        return {str(item).strip() for item in values if str(item).strip()}

    def _window_seconds(self) -> float:
        try:
            value = float(self.config.get("incident_window_seconds", 15))
        except (TypeError, ValueError):
            return 15.0
        return value if value > 0 else 15.0

    def _min_victims(self) -> int:
        try:
            value = int(self.config.get("min_victims", 3))
        except (TypeError, ValueError):
            return 3
        return value if value > 0 else 3

    def _cooldown_seconds(self) -> float:
        try:
            value = float(self.config.get("cooldown_seconds", 60))
        except (TypeError, ValueError):
            return 60.0
        return value if value >= 0 else 60.0

    def _max_recent_deaths(self) -> int:
        try:
            value = int(self.config.get("max_recent_deaths", 200))
        except (TypeError, ValueError):
            return 200
        return value if value > 0 else 200

    def _http_timeout_seconds(self) -> float:
        try:
            value = float(self.config.get("layer_source_timeout_seconds", 8))
        except (TypeError, ValueError):
            return 8.0
        return value if value > 0 else 8.0

    def _layer_source_url(self) -> str:
        value = str(self.config.get("layer_source_url", DEFAULT_LAYER_SOURCE_URL)).strip()
        return value or DEFAULT_LAYER_SOURCE_URL

    def _format_broadcast(
        self,
        *,
        weapon: str,
        victim_count: int,
        victims: list[str],
        window_seconds: float,
    ) -> str:
        if bool(self.config.get("include_victim_names", False)):
            victim_text = ", ".join(victims[: self._max_victim_names()])
        else:
            victim_text = str(victim_count)

        template = str(
            self.config.get(
                "broadcast_message",
                "Potential heli crash: {victim_count} death(s) in {window_seconds}s via {weapon}.",
            )
        )
        return self._format(
            template,
            weapon=weapon,
            victim_count=str(victim_count),
            victims=victim_text,
            window_seconds=str(int(window_seconds)),
        )

    def _max_victim_names(self) -> int:
        try:
            value = int(self.config.get("max_victim_names", 6))
        except (TypeError, ValueError):
            return 6
        return value if value > 0 else 6

    def _prune_recent(self, now: float) -> None:
        max_age = self._window_seconds() * 2
        while self._recent_deaths and (now - self._recent_deaths[0][0]) > max_age:
            self._recent_deaths.popleft()
        max_count = self._max_recent_deaths()
        while len(self._recent_deaths) > max_count:
            self._recent_deaths.popleft()

    @staticmethod
    def _format(template: str, **values: str) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template

    def _now(self) -> float:
        return time.monotonic()
