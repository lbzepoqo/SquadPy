"""TKWarn — tracks teamkills per round, warns offenders, kicks after threshold."""

from __future__ import annotations

import time

from squadpy.events.types import PlayerID, Teamkill
from squadpy.plugin import Plugin, on_event, periodic
from squadpy.rcon.types import RconPlayer


class TKWarn(Plugin):
    name = "TK Warn"
    description = "Warns and kicks players for excessive teamkills"
    requires = ["rcon"]

    async def on_enable(self):
        self._tk_counts: dict[str, int] = {}
        self._player_cache: dict[str, RconPlayer] = {}
        self._last_warning_at: dict[str, float] = {}
        self._kicked: set[str] = set()

    @periodic(seconds=30)
    async def refresh_players(self):
        players = await self.rcon.list_players()
        self._player_cache = {p.name: p for p in players}

    @on_event("teamkill")
    async def handle_teamkill(self, event: Teamkill):
        event_source = self._event_source()
        if event_source not in {"teamkill", "auto"}:
            return

        attacker = event.attacker
        victim = event.victim
        if not attacker or not victim:
            return

        attacker_key = self._actor_key(attacker)
        if not attacker_key:
            return
        if attacker_key == self._actor_key(victim):
            return

        await self._record_teamkill(attacker=attacker, victim=victim)

    @on_event("player_wounded")
    async def handle_wound(self, event):
        event_source = self._event_source()
        if event_source not in {"player_wounded", "auto"}:
            return

        victim = self._player_cache.get(event.victim_name)
        attacker = self._player_cache.get(event.attacker.name)

        if not victim or not attacker:
            return
        if victim.steam_id == attacker.steam_id:
            return
        if victim.team_id != attacker.team_id:
            return

        await self._record_teamkill(
            attacker=PlayerID(
                steam_id=attacker.steam_id,
                eos_id=attacker.eos_id,
                name=attacker.name,
            ),
            victim=PlayerID(
                steam_id=victim.steam_id,
                eos_id=victim.eos_id,
                name=victim.name,
            ),
        )

    @on_event("new_game")
    async def reset_counts(self, event):
        if not bool(self.config.get("reset_on_new_game", True)):
            return
        self._tk_counts.clear()
        self._last_warning_at.clear()
        self._kicked.clear()

    def _event_source(self) -> str:
        source = str(self.config.get("event_source", "teamkill")).strip().lower()
        if source in {"teamkill", "player_wounded", "auto"}:
            return source
        return "teamkill"

    def _kick_threshold(self) -> int:
        try:
            threshold = int(self.config.get("kick_threshold", 5))
        except (TypeError, ValueError):
            return 5
        return threshold if threshold > 0 else 5

    def _warning_cooldown_seconds(self) -> float:
        try:
            cooldown = float(self.config.get("warning_cooldown_seconds", 0))
        except (TypeError, ValueError):
            return 0.0
        return max(cooldown, 0.0)

    def _actor_key(self, player: PlayerID) -> str:
        return player.steam_id or player.eos_id or player.name

    def _safe_format(
        self,
        template: str,
        *,
        count: int,
        threshold: int,
        attacker_name: str,
        victim_name: str,
    ) -> str:
        try:
            return template.format(
                count=count,
                threshold=threshold,
                attacker=attacker_name,
                victim=victim_name,
            )
        except (KeyError, ValueError):
            return template

    async def _record_teamkill(self, *, attacker: PlayerID, victim: PlayerID):
        attacker_key = self._actor_key(attacker)
        if not attacker_key:
            return
        if attacker_key in self._kicked:
            return

        kick_threshold = self._kick_threshold()
        warning_message = self.config.get(
            "warning_message", "Team kill #{count} recorded. {threshold} = kick."
        )
        kick_message = self.config.get(
            "kick_message", "Kicked for excessive teamkills ({count})"
        )

        self._tk_counts[attacker_key] = self._tk_counts.get(attacker_key, 0) + 1
        count = self._tk_counts[attacker_key]

        attacker_name = attacker.name or "UnknownAttacker"
        victim_name = victim.name or "UnknownVictim"

        if count >= kick_threshold:
            msg = self._safe_format(
                kick_message,
                count=count,
                threshold=kick_threshold,
                attacker_name=attacker_name,
                victim_name=victim_name,
            )
            await self.rcon.kick(attacker_key, msg)
            self._kicked.add(attacker_key)
            return

        cooldown = self._warning_cooldown_seconds()
        if cooldown > 0:
            now = time.monotonic()
            last_warn = self._last_warning_at.get(attacker_key, 0.0)
            if now - last_warn < cooldown:
                return
            self._last_warning_at[attacker_key] = now

        msg = self._safe_format(
            warning_message,
            count=count,
            threshold=kick_threshold,
            attacker_name=attacker_name,
            victim_name=victim_name,
        )
        await self.rcon.warn(attacker_key, msg)
