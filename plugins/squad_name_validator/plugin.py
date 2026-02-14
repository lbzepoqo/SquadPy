"""SquadNameValidator - validates squad names and applies policy actions."""

from __future__ import annotations

import re

from squadpy.events.types import SquadCreated
from squadpy.plugin import Plugin, on_event, periodic


class SquadNameValidator(Plugin):
    name = "Squad Name Validator"
    description = "Validates squad names and warns/kicks on invalid names"
    requires = ["rcon"]

    async def on_enable(self):
        self._violation_counts: dict[str, int] = {}

    @periodic(seconds=30)
    async def validate_squads(self):
        squads = await self.rcon.list_squads()
        active_violators: set[str] = set()

        for squad in squads:
            leader_id = self._leader_id_from_squad(squad)
            if not leader_id:
                continue
            if not self._should_enforce(leader_id, squad.id):
                continue
            if self._name_is_valid(squad.name):
                continue

            active_violators.add(leader_id)
            await self._handle_violation(
                leader_id=leader_id,
                leader_name=squad.creator_name,
                squad_id=squad.id,
                squad_name=squad.name,
            )

        for leader_id in list(self._violation_counts):
            if leader_id not in active_violators:
                del self._violation_counts[leader_id]

    @on_event("squad_created")
    async def handle_squad_created(self, event: SquadCreated):
        if not bool(self.config.get("validate_on_create", True)):
            return

        leader_id = self._leader_id_from_event(event)
        squad_id = int(getattr(event, "squad_id", 0) or 0)
        squad_name = str(getattr(event, "squad_name", "")).strip()
        leader_name = getattr(getattr(event, "creator", None), "name", "")

        if not leader_id:
            return
        if not self._should_enforce(leader_id, squad_id):
            return
        if self._name_is_valid(squad_name):
            self._violation_counts.pop(leader_id, None)
            return

        await self._handle_violation(
            leader_id=leader_id,
            leader_name=leader_name,
            squad_id=squad_id,
            squad_name=squad_name,
        )

    @on_event("new_game")
    async def reset_state(self, event):
        self._violation_counts.clear()

    async def _handle_violation(
        self,
        *,
        leader_id: str,
        leader_name: str,
        squad_id: int,
        squad_name: str,
    ) -> None:
        action = self._action_mode()
        next_count = self._violation_counts.get(leader_id, 0) + 1
        threshold = self._warnings_before_kick()

        if action == "kick":
            await self.rcon.kick(leader_id, self._kick_reason(leader_name, squad_id, squad_name))
            self._violation_counts.pop(leader_id, None)
            return

        if action == "warn_then_kick" and next_count >= threshold:
            await self.rcon.kick(leader_id, self._kick_reason(leader_name, squad_id, squad_name))
            self._violation_counts.pop(leader_id, None)
            return

        self._violation_counts[leader_id] = next_count
        await self.rcon.warn(
            leader_id,
            self._warning_message(
                leader_name=leader_name,
                squad_id=squad_id,
                squad_name=squad_name,
                warning_count=next_count,
                warnings_remaining=max(0, threshold - next_count),
            ),
        )

    def _should_enforce(self, leader_id: str, squad_id: int) -> bool:
        if leader_id in self._exempt_player_ids():
            return False
        if squad_id in self._exempt_squad_ids():
            return False
        return True

    def _name_is_valid(self, squad_name: str) -> bool:
        normalized_name = " ".join(str(squad_name).split()).strip()
        if not normalized_name:
            return False

        if len(normalized_name) < self._min_length():
            return False
        if len(normalized_name) > self._max_length():
            return False

        candidate = normalized_name.casefold() if self._ignore_case() else normalized_name

        if candidate in self._blocked_exact_names():
            return False
        for token in self._blocked_terms():
            if token in candidate:
                return False
        for pattern in self._invalid_patterns():
            if pattern.search(normalized_name):
                return False

        required_pattern = self._required_pattern()
        if required_pattern is not None and not required_pattern.search(normalized_name):
            return False

        return True

    @staticmethod
    def _leader_id_from_squad(squad) -> str:
        return str(getattr(squad, "creator_steam_id", "")).strip() or str(
            getattr(squad, "creator_eos_id", "")
        ).strip()

    @staticmethod
    def _leader_id_from_event(event: SquadCreated) -> str:
        creator = getattr(event, "creator", None)
        if creator is None:
            return ""
        return str(getattr(creator, "steam_id", "")).strip() or str(
            getattr(creator, "eos_id", "")
        ).strip()

    def _action_mode(self) -> str:
        configured = str(self.config.get("enforcement_action", "warn_then_kick")).strip().lower()
        if configured in {"warn", "warn_then_kick", "kick"}:
            return configured
        return "warn_then_kick"

    def _warnings_before_kick(self) -> int:
        try:
            value = int(self.config.get("warnings_before_kick", 2))
        except (TypeError, ValueError):
            return 2
        return value if value > 0 else 1

    def _min_length(self) -> int:
        try:
            value = int(self.config.get("min_length", 3))
        except (TypeError, ValueError):
            return 3
        return value if value > 0 else 1

    def _max_length(self) -> int:
        try:
            value = int(self.config.get("max_length", 24))
        except (TypeError, ValueError):
            return 24
        return value if value > 0 else 24

    def _ignore_case(self) -> bool:
        return bool(self.config.get("ignore_case", True))

    def _blocked_exact_names(self) -> set[str]:
        raw = self.config.get("blocked_exact_names", [])
        if not isinstance(raw, list):
            return set()
        values = []
        for item in raw:
            token = " ".join(str(item).split()).strip()
            if token:
                values.append(token.casefold() if self._ignore_case() else token)
        return set(values)

    def _blocked_terms(self) -> set[str]:
        raw = self.config.get("blocked_terms", [])
        if not isinstance(raw, list):
            return set()
        values = []
        for item in raw:
            token = str(item).strip()
            if token:
                values.append(token.casefold() if self._ignore_case() else token)
        return set(values)

    def _invalid_patterns(self) -> list[re.Pattern]:
        raw = self.config.get("invalid_patterns", [])
        if not isinstance(raw, list):
            return []
        flags = re.IGNORECASE if self._ignore_case() else 0
        patterns: list[re.Pattern] = []
        for item in raw:
            source = str(item).strip()
            if not source:
                continue
            try:
                patterns.append(re.compile(source, flags))
            except re.error:
                continue
        return patterns

    def _required_pattern(self) -> re.Pattern | None:
        source = str(self.config.get("required_pattern", "")).strip()
        if not source:
            return None
        flags = re.IGNORECASE if self._ignore_case() else 0
        try:
            return re.compile(source, flags)
        except re.error:
            return None

    def _exempt_player_ids(self) -> set[str]:
        raw = self.config.get("exempt_steam_ids", [])
        if not isinstance(raw, list):
            return set()
        return {str(item).strip() for item in raw if str(item).strip()}

    def _exempt_squad_ids(self) -> set[int]:
        raw = self.config.get("exempt_squad_ids", [])
        if not isinstance(raw, list):
            return set()

        values: set[int] = set()
        for item in raw:
            try:
                squad_id = int(item)
            except (TypeError, ValueError):
                continue
            if squad_id > 0:
                values.add(squad_id)
        return values

    def _warning_message(
        self,
        *,
        leader_name: str,
        squad_id: int,
        squad_name: str,
        warning_count: int,
        warnings_remaining: int,
    ) -> str:
        template = str(
            self.config.get(
                "warning_message",
                "Squad name '{squad_name}' is invalid. Rename squad {squad_id} to comply ({warnings_remaining} warning left).",
            )
        )
        return self._format(
            template,
            leader=leader_name,
            squad_id=str(squad_id),
            squad_name=squad_name,
            warning_count=str(warning_count),
            warnings_remaining=str(warnings_remaining),
            min_length=str(self._min_length()),
            max_length=str(self._max_length()),
        )

    def _kick_reason(self, leader_name: str, squad_id: int, squad_name: str) -> str:
        template = str(
            self.config.get(
                "kick_reason",
                "Kicked for invalid squad name policy violation in squad {squad_id}.",
            )
        )
        return self._format(
            template,
            leader=leader_name,
            squad_id=str(squad_id),
            squad_name=squad_name,
            min_length=str(self._min_length()),
            max_length=str(self._max_length()),
        )

    def _format(self, template: str, **values: str) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template
