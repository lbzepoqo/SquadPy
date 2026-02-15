"""Layer metadata catalog loading and normalization."""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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


@dataclass
class LayerCatalogHealth:
    status: str
    stale: bool
    has_catalog: bool
    fetch_failed: bool
    consecutive_failures: int
    last_error: str
    last_sync_monotonic: float
    last_success_monotonic: float
    age_seconds: float
    source_url: str
    etag: str
    last_modified: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "stale": self.stale,
            "has_catalog": self.has_catalog,
            "fetch_failed": self.fetch_failed,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "last_sync_monotonic": self.last_sync_monotonic,
            "last_success_monotonic": self.last_success_monotonic,
            "age_seconds": self.age_seconds,
            "source_url": self.source_url,
            "etag": self.etag,
            "last_modified": self.last_modified,
        }


class LayerCatalogService:
    """Loads and normalizes layer metadata from a remote source."""

    def __init__(
        self,
        *,
        source_url: str = DEFAULT_LAYER_SOURCE_URL,
        timeout_seconds: float = 8.0,
        sync_interval_seconds: float = 3600.0,
        stale_after_seconds: float = 21600.0,
        backoff_initial_seconds: float = 30.0,
        backoff_max_seconds: float = 900.0,
        backoff_multiplier: float = 2.0,
        backoff_jitter_ratio: float = 0.1,
        snapshot_path: str | Path = "",
        clock: Callable[[], float] | None = None,
    ):
        self.source_url = source_url.strip() or DEFAULT_LAYER_SOURCE_URL
        self.timeout_seconds = timeout_seconds if timeout_seconds > 0 else 8.0
        self.sync_interval_seconds = sync_interval_seconds if sync_interval_seconds > 0 else 3600.0
        self.stale_after_seconds = stale_after_seconds if stale_after_seconds > 0 else 21600.0
        self.backoff_initial_seconds = (
            backoff_initial_seconds if backoff_initial_seconds > 0 else 30.0
        )
        self.backoff_max_seconds = backoff_max_seconds if backoff_max_seconds > 0 else 900.0
        self.backoff_multiplier = backoff_multiplier if backoff_multiplier > 1.0 else 2.0
        self.backoff_jitter_ratio = (
            backoff_jitter_ratio if backoff_jitter_ratio >= 0 else 0.0
        )
        raw_snapshot_path = str(snapshot_path).strip()
        self.snapshot_path = Path(raw_snapshot_path) if raw_snapshot_path else None
        self._clock = clock or time.monotonic

        self._catalog = LayerCatalog.empty()
        self._etag = ""
        self._last_modified = ""
        self._last_error = ""
        self._consecutive_failures = 0
        self._last_sync_monotonic = 0.0
        self._last_success_monotonic = 0.0

    async def fetch(self) -> LayerCatalog:
        payload = await self._fetch_json()
        catalog = normalize_layers_payload(payload)
        catalog.source_url = self.source_url
        catalog.fetched_at_monotonic = self._clock()
        self._catalog = catalog
        self._last_success_monotonic = catalog.fetched_at_monotonic
        self._last_sync_monotonic = catalog.fetched_at_monotonic
        self._last_error = ""
        self._consecutive_failures = 0
        self._persist_snapshot_if_configured()
        return catalog

    async def sync_once(self) -> LayerCatalog:
        headers = self._conditional_request_headers()
        self._last_sync_monotonic = self._clock()
        try:
            status, payload, metadata = await self._fetch_json_with_metadata(headers=headers)
        except Exception as exc:
            self._consecutive_failures += 1
            self._last_error = str(exc)
            return self._catalog

        self._etag = metadata.get("etag", "").strip()
        self._last_modified = metadata.get("last_modified", "").strip()

        if status == 304:
            self._consecutive_failures = 0
            self._last_error = ""
            self._last_success_monotonic = self._clock()
            return self._catalog

        try:
            if payload is None:
                raise ValueError("Layer catalog payload missing for non-304 response")

            catalog = normalize_layers_payload(payload)
            catalog.source_url = self.source_url
            catalog.fetched_at_monotonic = self._clock()
        except Exception as exc:
            self._consecutive_failures += 1
            self._last_error = str(exc)
            return self._catalog

        self._catalog = catalog
        self._consecutive_failures = 0
        self._last_error = ""
        self._last_success_monotonic = catalog.fetched_at_monotonic
        self._persist_snapshot_if_configured()
        return self._catalog

    async def run_scheduled_sync(
        self,
        *,
        iterations: int | None = None,
        sleep: Callable[[float], Any] | None = None,
    ) -> None:
        if iterations is not None and iterations <= 0:
            return
        sleep_fn = sleep or _sleep
        completed = 0
        while iterations is None or completed < iterations:
            await self.sync_once()
            completed += 1
            if iterations is not None and completed >= iterations:
                break
            delay = self.next_sync_delay_seconds()
            await sleep_fn(delay)

    async def initialize(self) -> LayerCatalog:
        await self.sync_once()
        if self.health().has_catalog:
            return self._catalog

        self.load_snapshot()
        return self._catalog

    @property
    def catalog(self) -> LayerCatalog:
        return self._catalog

    def health(self) -> LayerCatalogHealth:
        has_catalog = bool(
            self._catalog.layers
            or self._catalog.factions
            or self._catalog.vehicles_by_class
            or self._catalog.melee_weapons
        )
        age_seconds = 0.0
        if self._last_success_monotonic > 0:
            age_seconds = max(0.0, self._clock() - self._last_success_monotonic)
        stale = has_catalog and age_seconds > self.stale_after_seconds
        fetch_failed = self._consecutive_failures > 0
        if not has_catalog and fetch_failed:
            status = "unhealthy"
        elif stale:
            status = "stale"
        elif fetch_failed:
            status = "degraded"
        else:
            status = "healthy"

        return LayerCatalogHealth(
            status=status,
            stale=stale,
            has_catalog=has_catalog,
            fetch_failed=fetch_failed,
            consecutive_failures=self._consecutive_failures,
            last_error=self._last_error,
            last_sync_monotonic=self._last_sync_monotonic,
            last_success_monotonic=self._last_success_monotonic,
            age_seconds=age_seconds,
            source_url=self.source_url,
            etag=self._etag,
            last_modified=self._last_modified,
        )

    def next_sync_delay_seconds(self) -> float:
        if self._consecutive_failures <= 0:
            return self.sync_interval_seconds

        exponent = self._consecutive_failures - 1
        delay = self.backoff_initial_seconds * (self.backoff_multiplier ** exponent)
        delay = min(delay, self.backoff_max_seconds)
        if self.backoff_jitter_ratio <= 0:
            return delay

        jitter_window = delay * self.backoff_jitter_ratio
        jitter = random.uniform(-jitter_window, jitter_window)
        return max(0.0, delay + jitter)

    def load_snapshot(self) -> bool:
        if self.snapshot_path is None or not self.snapshot_path.exists():
            return False

        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            catalog_payload = payload.get("catalog", {})
            catalog = _catalog_from_snapshot(catalog_payload)
            source_url = str(payload.get("source_url", "")).strip()
            if source_url:
                catalog.source_url = source_url
            elif not catalog.source_url:
                catalog.source_url = self.source_url
            catalog.fetched_at_monotonic = self._clock()
        except Exception:
            return False

        self._catalog = catalog
        self._etag = str(payload.get("etag", "")).strip()
        self._last_modified = str(payload.get("last_modified", "")).strip()
        self._last_success_monotonic = catalog.fetched_at_monotonic
        return True

    def _persist_snapshot_if_configured(self) -> None:
        if self.snapshot_path is None or not self.health().has_catalog:
            return

        payload = {
            "version": 1,
            "source_url": self.source_url,
            "etag": self._etag,
            "last_modified": self._last_modified,
            "saved_at_monotonic": self._clock(),
            "catalog": _catalog_to_snapshot(self._catalog),
        }
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.snapshot_path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception:
            return

    async def _fetch_json(self) -> Any:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.source_url) as response:
                response.raise_for_status()
                text = await response.text()
        return json.loads(text)

    async def _fetch_json_with_metadata(
        self,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any | None, dict[str, str]]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.source_url, headers=headers) as response:
                metadata = {
                    "etag": str(response.headers.get("ETag", "")),
                    "last_modified": str(response.headers.get("Last-Modified", "")),
                }
                if response.status == 304:
                    return response.status, None, metadata
                response.raise_for_status()
                text = await response.text()
        return response.status, json.loads(text), metadata

    def _conditional_request_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified
        return headers


async def _sleep(delay: float) -> None:
    await asyncio.sleep(delay)


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


def _catalog_to_snapshot(catalog: LayerCatalog) -> dict[str, Any]:
    vehicles_by_class = {
        vehicle_class: sorted(names)
        for vehicle_class, names in catalog.vehicles_by_class.items()
        if names
    }
    return {
        "layers": sorted(catalog.layers),
        "factions": sorted(catalog.factions),
        "vehicles_by_class": vehicles_by_class,
        "melee_weapons": sorted(catalog.melee_weapons),
        "source_url": catalog.source_url,
    }


def _catalog_from_snapshot(payload: Any) -> LayerCatalog:
    if not isinstance(payload, dict):
        return LayerCatalog.empty()

    raw_layers = payload.get("layers", [])
    layers = _string_list(raw_layers)

    raw_factions = payload.get("factions", [])
    factions = _string_list(raw_factions)

    raw_melee_weapons = payload.get("melee_weapons", [])
    melee_weapons = _string_list(raw_melee_weapons)

    vehicles_by_class: dict[str, frozenset[str]] = {}
    raw_vehicles = payload.get("vehicles_by_class", {})
    if isinstance(raw_vehicles, dict):
        for vehicle_class, names in raw_vehicles.items():
            class_key = _vehicle_class_key(vehicle_class)
            if not class_key:
                continue
            values = _string_list(names)
            if values:
                vehicles_by_class[class_key] = frozenset(values)

    source_url = str(payload.get("source_url", "")).strip()
    return LayerCatalog(
        layers=frozenset(layers),
        factions=frozenset(factions),
        vehicles_by_class=vehicles_by_class,
        melee_weapons=frozenset(melee_weapons),
        source_url=source_url,
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
