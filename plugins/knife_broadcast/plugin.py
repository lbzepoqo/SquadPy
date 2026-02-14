"""KnifeBroadcast - announce knife/melee kills."""

from __future__ import annotations

import time

from squadpy.layers import DEFAULT_LAYER_SOURCE_URL, LayerCatalog, LayerCatalogService
from squadpy.plugin import Plugin, on_event


class KnifeBroadcast(Plugin):
    name = "Knife Broadcast"
    description = "Broadcasts knife/melee kills to the server"
    requires = ["rcon"]

    async def on_enable(self):
        self._last_broadcast_at = 0.0
        self._layer_catalog = LayerCatalog.empty()

        if bool(self.config.get("fetch_melee_weapons_from_layer_source", True)):
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
        if not self._is_knife_weapon(weapon):
            return

        now = self._now()
        cooldown = self._cooldown_seconds()
        if cooldown > 0 and (now - self._last_broadcast_at) < cooldown:
            return

        attacker = str(getattr(getattr(event, "attacker", None), "name", "")).strip()
        victim = str(getattr(event, "victim_name", "")).strip()
        message = self._format_broadcast(
            attacker=attacker or "UnknownAttacker",
            victim=victim or "UnknownVictim",
            weapon=weapon or "UnknownWeapon",
        )
        await self.rcon.broadcast(message)
        self._last_broadcast_at = now

    @on_event("new_game")
    async def handle_new_game(self, event):
        if bool(self.config.get("reset_on_new_game", True)):
            self._last_broadcast_at = 0.0

    def _is_knife_weapon(self, weapon: str) -> bool:
        normalized = weapon.casefold()
        if not normalized:
            return False

        if any(token in normalized for token in self._knife_tokens()):
            return True

        known_tokens = self._known_melee_tokens()
        return any(token in normalized for token in known_tokens)

    def _known_melee_tokens(self) -> set[str]:
        names = set(self._layer_catalog.melee_weapons) | self._configured_melee_weapon_names()
        tokens: set[str] = set()
        for name in names:
            normalized = "".join(ch if ch.isalnum() else " " for ch in name.casefold())
            for token in normalized.split():
                if len(token) >= 3:
                    tokens.add(token)
        return tokens

    def _knife_tokens(self) -> list[str]:
        raw = self.config.get(
            "knife_weapon_tokens",
            ["knife", "bayonet", "combatknife", "melee"],
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
        return ["knife", "bayonet", "combatknife", "melee"]

    def _configured_melee_weapon_names(self) -> set[str]:
        raw = self.config.get("melee_weapon_names", [])
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = raw
        else:
            values = []

        return {str(item).strip() for item in values if str(item).strip()}

    def _cooldown_seconds(self) -> float:
        try:
            value = float(self.config.get("cooldown_seconds", 5))
        except (TypeError, ValueError):
            return 5.0
        return value if value >= 0 else 5.0

    def _http_timeout_seconds(self) -> float:
        try:
            value = float(self.config.get("layer_source_timeout_seconds", 8))
        except (TypeError, ValueError):
            return 8.0
        return value if value > 0 else 8.0

    def _layer_source_url(self) -> str:
        value = str(self.config.get("layer_source_url", DEFAULT_LAYER_SOURCE_URL)).strip()
        return value or DEFAULT_LAYER_SOURCE_URL

    def _format_broadcast(self, *, attacker: str, victim: str, weapon: str) -> str:
        show_weapon = bool(self.config.get("include_weapon_name", True))
        default_template = (
            "{attacker} knifed {victim} with {weapon}!"
            if show_weapon
            else "{attacker} knifed {victim}!"
        )
        template = str(
            self.config.get(
                "broadcast_message",
                default_template,
            )
        )
        return self._format(
            template,
            attacker=attacker,
            victim=victim,
            weapon=weapon if show_weapon else "",
        )

    @staticmethod
    def _format(template: str, **values: str) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template

    def _now(self) -> float:
        return time.monotonic()
