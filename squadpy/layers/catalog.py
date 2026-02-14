"""Layer metadata catalog loading and normalization."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

DEFAULT_LAYER_SOURCE_URL = (
    "https://raw.githubusercontent.com/fantinodavide/SquadLayerList/refs/heads/main/layers.json"
)

_LAYER_VALUE_KEYS = {
    "layer",
    "layer_classname",
    "layer_name",
    "layerid",
    "layer_id",
    "name",
}
_FACTION_VALUE_KEYS = {"faction", "faction_name", "subfaction", "subfaction_name"}
_VEHICLE_CLASS_KEYS = {"type", "vehicle_type", "category", "classification"}
_VEHICLE_NAME_KEYS = {
    "name",
    "display_name",
    "class",
    "classname",
    "class_name",
    "vehicle",
    "vehicle_name",
    "asset",
    "template",
    "blueprint",
    "id",
}
_MELEE_VALUE_KEYS = {"meleeweapons", "melee_weapons", "melee_weapon"}


@dataclass
class LayerCatalog:
    """Normalized layer metadata catalog."""

    layers: frozenset[str] = field(default_factory=frozenset)
    factions: frozenset[str] = field(default_factory=frozenset)
    vehicles_by_class: dict[str, frozenset[str]] = field(default_factory=dict)
    melee_weapons: frozenset[str] = field(default_factory=frozenset)
    source_url: str = ""
    fetched_at_monotonic: float = 0.0

    @classmethod
    def empty(cls) -> "LayerCatalog":
        return cls()

    def has_layer(self, layer_name: str) -> bool:
        target = _norm(layer_name)
        if not target:
            return False
        return any(_norm(name) == target for name in self.layers)

    def has_faction(self, faction_name: str) -> bool:
        target = _norm(faction_name)
        if not target:
            return False
        return any(_norm(name) == target for name in self.factions)

    def vehicle_names(self, vehicle_class: str) -> set[str]:
        key = _vehicle_class_key(vehicle_class)
        if not key:
            return set()
        values = self.vehicles_by_class.get(key, frozenset())
        return set(values)

    @property
    def helicopter_names(self) -> set[str]:
        return self.vehicle_names("HELICOPTER")

    def helicopter_tokens(self, *, min_length: int = 3) -> set[str]:
        return _tokenize_names(self.helicopter_names, min_length=min_length)

    def melee_weapon_tokens(self, *, min_length: int = 3) -> set[str]:
        return _tokenize_names(set(self.melee_weapons), min_length=min_length)


class LayerCatalogService:
    """Loads and normalizes layer metadata from a remote source."""

    def __init__(
        self,
        *,
        source_url: str = DEFAULT_LAYER_SOURCE_URL,
        timeout_seconds: float = 8.0,
    ):
        self.source_url = source_url.strip() or DEFAULT_LAYER_SOURCE_URL
        self.timeout_seconds = timeout_seconds if timeout_seconds > 0 else 8.0

    async def fetch(self) -> LayerCatalog:
        payload = await self._fetch_json()
        catalog = normalize_layers_payload(payload)
        catalog.source_url = self.source_url
        catalog.fetched_at_monotonic = time.monotonic()
        return catalog

    async def _fetch_json(self) -> Any:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.source_url) as response:
                response.raise_for_status()
                text = await response.text()
        return json.loads(text)


def normalize_layers_payload(payload: Any) -> LayerCatalog:
    layers: set[str] = set()
    factions: set[str] = set()
    vehicles_by_class: dict[str, set[str]] = {}
    melee_weapons: set[str] = set()

    def add_layer(value: Any) -> None:
        text = _clean_name(value)
        if not text:
            return
        lowered = _norm(text)
        if lowered in {"layers", "layer"}:
            return
        layers.add(text)

    def add_faction(value: Any) -> None:
        text = _clean_name(value)
        if text:
            factions.add(text)

    def add_vehicle(vehicle_class: str, value: Any) -> None:
        key = _vehicle_class_key(vehicle_class)
        text = _clean_name(value)
        if not key or not text:
            return
        if key == "HELICOPTER" and _norm(text) in {"helicopter", "helicopters"}:
            return
        vehicles_by_class.setdefault(key, set()).add(text)

    def add_melee_weapon(value: Any) -> None:
        text = _clean_name(value)
        if not text:
            return
        lowered = _norm(text)
        if lowered in {"meleeweapon", "meleeweapons", "knife", "knives"}:
            return
        melee_weapons.add(text)

    def collect_vehicle_names(node: Any, inferred_class: str | None = None) -> None:
        if isinstance(node, str):
            if inferred_class:
                add_vehicle(inferred_class, node)
            return

        if isinstance(node, list):
            for item in node:
                collect_vehicle_names(item, inferred_class)
            return

        if not isinstance(node, dict):
            return

        local_class = inferred_class
        for key in _VEHICLE_CLASS_KEYS:
            class_value = node.get(key)
            if isinstance(class_value, str):
                local_class = class_value
                break

        for key in _VEHICLE_NAME_KEYS:
            value = node.get(key)
            if isinstance(value, str) and local_class:
                add_vehicle(local_class, value)

        for key, value in node.items():
            key_norm = _norm(key)
            if key_norm in {"vehicle", "vehicles"}:
                collect_vehicle_names(value, local_class)
                continue
            if isinstance(value, (dict, list)):
                collect_vehicle_names(value, local_class)

    def collect_name_strings(node: Any, *, add_value) -> None:
        if isinstance(node, str):
            add_value(node)
            return
        if isinstance(node, list):
            for item in node:
                collect_name_strings(item, add_value=add_value)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            key_norm = _norm(key)
            if key_norm in _VEHICLE_NAME_KEYS and isinstance(value, str):
                add_value(value)
            elif isinstance(value, (dict, list)):
                collect_name_strings(value, add_value=add_value)

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return

        if not isinstance(node, dict):
            return

        for key, value in node.items():
            key_norm = _norm(key)

            if key_norm in _LAYER_VALUE_KEYS and isinstance(value, str):
                add_layer(value)

            if key_norm in _FACTION_VALUE_KEYS and isinstance(value, str):
                add_faction(value)

            if key_norm in {"factions", "teams"}:
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            add_faction(item)
                        elif isinstance(item, dict):
                            for faction_key in _FACTION_VALUE_KEYS | {"name"}:
                                faction_value = item.get(faction_key)
                                if isinstance(faction_value, str):
                                    add_faction(faction_value)
                            walk(item)
                elif isinstance(value, dict):
                    walk(value)

            if key_norm == "vehicles":
                if isinstance(value, dict):
                    for vehicle_class, vehicle_values in value.items():
                        collect_vehicle_names(vehicle_values, inferred_class=str(vehicle_class))
                else:
                    collect_vehicle_names(value)
            elif key_norm in _MELEE_VALUE_KEYS:
                collect_name_strings(value, add_value=add_melee_weapon)
            elif key_norm in _VEHICLE_CLASS_KEYS:
                if isinstance(value, str):
                    collect_vehicle_names(node, inferred_class=value)
            elif isinstance(value, (dict, list)):
                walk(value)

    walk(payload)

    normalized_vehicles = {
        vehicle_class: frozenset(sorted(names))
        for vehicle_class, names in vehicles_by_class.items()
        if names
    }
    return LayerCatalog(
        layers=frozenset(sorted(layers)),
        factions=frozenset(sorted(factions)),
        vehicles_by_class=normalized_vehicles,
        melee_weapons=frozenset(sorted(melee_weapons)),
    )


def _tokenize_names(names: set[str], *, min_length: int) -> set[str]:
    tokens: set[str] = set()
    for name in names:
        normalized = "".join(ch if ch.isalnum() else " " for ch in _norm(name))
        for token in normalized.split():
            if len(token) >= min_length:
                tokens.add(token)
    return tokens


def _vehicle_class_key(vehicle_class: str | None) -> str:
    if not vehicle_class:
        return ""
    return (
        str(vehicle_class)
        .strip()
        .replace("-", "_")
        .replace(" ", "_")
        .upper()
    )


def _clean_name(value: Any) -> str:
    text = str(value).strip()
    if len(text) < 2:
        return ""
    return text


def _norm(value: Any) -> str:
    return str(value).strip().casefold()
