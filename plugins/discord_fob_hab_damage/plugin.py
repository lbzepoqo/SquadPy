"""DiscordFobHabDamage - summarizes FOB/HAB deployable damage at thresholds."""

from __future__ import annotations

from squadpy.events.types import DeployableDamaged
from squadpy.plugin import Plugin, on_event


class DiscordFobHabDamage(Plugin):
    name = "Discord FOB/HAB Damage"
    description = "Summarizes FOB/HAB deployable damage in a Discord channel"
    requires = ["discord"]

    async def on_enable(self) -> None:
        self._damage_totals: dict[str, float] = {}
        self._threshold_indices: dict[str, int] = {}

    @on_event("deployable_damaged")
    async def handle_deployable_damaged(self, event: DeployableDamaged) -> None:
        channel_id = self.config.get("channel_id", 0)
        if not channel_id:
            return

        damage = self._positive_damage(event.damage)
        if damage <= 0:
            return

        deployable_name = event.deployable.strip() or "UnknownDeployable"
        category = self._category_for_deployable(deployable_name)
        if category is None:
            return

        aggregation_key = f"{category}:{deployable_name.casefold()}"
        previous_total = self._damage_totals.get(aggregation_key, 0.0)
        cumulative_total = previous_total + damage
        self._damage_totals[aggregation_key] = cumulative_total

        thresholds = self._summary_thresholds()
        previous_index = self._threshold_indices.get(aggregation_key, -1)
        crossed_index = previous_index
        for index, threshold in enumerate(thresholds):
            if index <= previous_index:
                continue
            if cumulative_total >= threshold:
                crossed_index = index

        if crossed_index == previous_index:
            return

        self._threshold_indices[aggregation_key] = crossed_index
        crossed_threshold = thresholds[crossed_index]

        metadata_parts: list[str] = []
        if bool(self.config.get("include_damage_metadata", True)):
            metadata_parts.append(f"source={event.damage_source or 'unknown'}")
            metadata_parts.append(f"type={event.damage_type or 'unknown'}")
            metadata_parts.append(f"direct_hit={str(bool(event.direct_hit)).lower()}")
        metadata_text = f" {' '.join(metadata_parts)}" if metadata_parts else ""

        content = (
            f"[FOB/HAB Damage] category={category} deployable={deployable_name} "
            f"hit={damage:.1f} cumulative={cumulative_total:.1f} "
            f"threshold={crossed_threshold:.1f}{metadata_text}"
        )
        await self.discord.send(channel_id, content=content)

    @on_event("new_game")
    async def handle_new_game(self, event) -> None:
        if bool(self.config.get("reset_on_new_game", True)):
            self._damage_totals.clear()
            self._threshold_indices.clear()

    def _summary_thresholds(self) -> list[float]:
        configured = self.config.get("summary_thresholds", [250, 500, 1000])
        if isinstance(configured, list):
            raw_values = configured
        else:
            raw_values = [configured]

        parsed_thresholds: list[float] = []
        for value in raw_values:
            try:
                threshold = float(value)
            except (TypeError, ValueError):
                continue
            if threshold > 0:
                parsed_thresholds.append(threshold)

        if not parsed_thresholds:
            return [250.0, 500.0, 1000.0]
        return sorted(set(parsed_thresholds))

    def _category_for_deployable(self, deployable_name: str) -> str | None:
        normalized = deployable_name.casefold()
        if self._contains_keyword(
            normalized, self._keywords("hab_keywords", ["hab", "bunker", "spawn"])
        ):
            return "HAB"
        if self._contains_keyword(
            normalized, self._keywords("fob_keywords", ["fob", "radio"])
        ):
            return "FOB"
        if bool(self.config.get("include_other_deployables", False)):
            return "OTHER"
        return None

    def _keywords(self, key: str, default: list[str]) -> list[str]:
        configured = self.config.get(key, default)
        if isinstance(configured, str):
            configured_values = [configured]
        elif isinstance(configured, list):
            configured_values = configured
        else:
            configured_values = default

        parsed_keywords: list[str] = []
        for value in configured_values:
            token = str(value).strip().casefold()
            if token:
                parsed_keywords.append(token)
        if parsed_keywords:
            return parsed_keywords
        return [item.casefold() for item in default]

    @staticmethod
    def _contains_keyword(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _positive_damage(value: object) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return parsed if parsed > 0 else 0.0
