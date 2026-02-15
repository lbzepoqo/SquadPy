"""Tests for shared layer catalog normalization and loading."""

import json

from squadpy.layers import LayerCatalogService, normalize_layers_payload


def test_normalize_layers_payload_extracts_layer_faction_and_vehicle_classes():
    payload = {
        "MeleeWeapons": [
            "BP_Knife_Combat_C",
            {"name": "BP_Melee_Dagger_C"},
        ],
        "layers": [
            {
                "name": "Narva_RAAS_v1",
                "factions": ["USA", "RGF"],
                "vehicles": {
                    "HELICOPTER": [
                        {"name": "BP_Loach_CAS_Small_C"},
                        "MI8 Transport",
                    ],
                    "IFV": [{"name": "BTR-82A"}],
                },
            }
        ]
    }
    catalog = normalize_layers_payload(payload)

    assert catalog.has_layer("narva_raas_v1")
    assert catalog.has_faction("usa")
    assert catalog.vehicle_names("ifv") == {"BTR-82A"}
    assert catalog.helicopter_names == {"BP_Loach_CAS_Small_C", "MI8 Transport"}
    assert catalog.melee_weapons == {"BP_Knife_Combat_C", "BP_Melee_Dagger_C"}
    assert "knife" in catalog.melee_weapon_tokens()


def test_normalize_layers_payload_extracts_typed_vehicle_entries():
    payload = {
        "layers": [
            {
                "layer": "Yehorivka_AAS_v2",
                "teams": [
                    {"faction": "BAF"},
                    {"faction": "PLA"},
                ],
                "vehicles": [
                    {"type": "HELICOPTER", "name": "UH60 Blackhawk"},
                    {"type": "TRANSPORT", "name": "M939"},
                ],
            }
        ]
    }
    catalog = normalize_layers_payload(payload)

    assert catalog.has_layer("YEHORIVKA_AAS_V2")
    assert catalog.has_faction("plA")
    assert catalog.vehicle_names("transport") == {"M939"}
    assert catalog.helicopter_names == {"UH60 Blackhawk"}
    assert "blackhawk" in catalog.helicopter_tokens()


async def test_layer_catalog_service_fetch_sets_source_metadata():
    service = LayerCatalogService(source_url="https://example.test/layers.json", timeout_seconds=2.5)

    async def fake_fetch_json():
        return {
            "layers": [
                {
                    "name": "Gorodok_RAAS_v1",
                    "vehicles": {"HELICOPTER": [{"name": "MI8 Transport"}]},
                }
            ]
        }

    service._fetch_json = fake_fetch_json
    catalog = await service.fetch()

    assert catalog.source_url == "https://example.test/layers.json"
    assert catalog.fetched_at_monotonic > 0
    assert catalog.has_layer("gorodok_raas_v1")
    assert catalog.helicopter_names == {"MI8 Transport"}


async def test_layer_catalog_service_sync_uses_conditional_fetch_headers():
    service = LayerCatalogService(
        source_url="https://example.test/layers.json",
        backoff_jitter_ratio=0,
    )
    request_headers: list[dict[str, str]] = []

    async def fake_fetch_json_with_metadata(*, headers=None):
        request_headers.append(dict(headers or {}))
        if len(request_headers) == 1:
            return (
                200,
                {"layers": [{"name": "Narva_RAAS_v1"}]},
                {
                    "etag": "etag-v1",
                    "last_modified": "Fri, 13 Feb 2026 00:00:00 GMT",
                },
            )
        return (
            304,
            None,
            {
                "etag": "etag-v1",
                "last_modified": "Fri, 13 Feb 2026 00:00:00 GMT",
            },
        )

    service._fetch_json_with_metadata = fake_fetch_json_with_metadata

    first = await service.sync_once()
    second = await service.sync_once()

    assert first.has_layer("narva_raas_v1")
    assert second.has_layer("narva_raas_v1")
    assert request_headers[0] == {}
    assert request_headers[1] == {
        "If-None-Match": "etag-v1",
        "If-Modified-Since": "Fri, 13 Feb 2026 00:00:00 GMT",
    }


async def test_layer_catalog_service_health_reports_stale_and_fetch_failure():
    now = 100.0
    service = LayerCatalogService(
        source_url="https://example.test/layers.json",
        stale_after_seconds=5,
        backoff_jitter_ratio=0,
        clock=lambda: now,
    )

    async def fake_success(*, headers=None):
        return (200, {"layers": [{"name": "Gorodok_RAAS_v1"}]}, {})

    service._fetch_json_with_metadata = fake_success
    await service.sync_once()
    health = service.health()
    assert health.status == "healthy"
    assert health.stale is False
    assert health.fetch_failed is False

    now = 107.0
    stale_health = service.health()
    assert stale_health.status == "stale"
    assert stale_health.stale is True

    async def fake_failure(*, headers=None):
        raise RuntimeError("layer source unavailable")

    service._fetch_json_with_metadata = fake_failure
    await service.sync_once()

    failed_health = service.health()
    assert failed_health.stale is True
    assert failed_health.fetch_failed is True
    assert failed_health.consecutive_failures == 1
    assert "layer source unavailable" in failed_health.last_error


async def test_layer_catalog_service_scheduler_uses_backoff_then_interval():
    service = LayerCatalogService(
        source_url="https://example.test/layers.json",
        sync_interval_seconds=60,
        backoff_initial_seconds=10,
        backoff_max_seconds=120,
        backoff_multiplier=2,
        backoff_jitter_ratio=0,
    )
    attempts = 0

    async def fake_fetch_json_with_metadata(*, headers=None):
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise RuntimeError("transient fetch error")
        return (200, {"layers": [{"name": "AlBasrah_AAS_v1"}]}, {})

    delays: list[float] = []

    async def fake_sleep(delay: float):
        delays.append(delay)

    service._fetch_json_with_metadata = fake_fetch_json_with_metadata
    await service.run_scheduled_sync(iterations=4, sleep=fake_sleep)

    assert delays == [10.0, 20.0, 60]


async def test_layer_catalog_service_sync_persists_snapshot(tmp_path):
    snapshot_path = tmp_path / "layers.snapshot.json"
    service = LayerCatalogService(
        source_url="https://example.test/layers.json",
        snapshot_path=snapshot_path,
    )

    async def fake_fetch_json_with_metadata(*, headers=None):
        return (
            200,
            {
                "layers": [
                    {
                        "name": "Narva_RAAS_v1",
                        "factions": ["USA"],
                    }
                ]
            },
            {
                "etag": "etag-v2",
                "last_modified": "Sat, 14 Feb 2026 00:00:00 GMT",
            },
        )

    service._fetch_json_with_metadata = fake_fetch_json_with_metadata
    await service.sync_once()

    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["source_url"] == "https://example.test/layers.json"
    assert snapshot["etag"] == "etag-v2"
    assert snapshot["catalog"]["layers"] == ["Narva_RAAS_v1"]
    assert snapshot["catalog"]["factions"] == ["USA"]


async def test_layer_catalog_service_initialize_restores_snapshot_when_remote_unavailable(tmp_path):
    snapshot_path = tmp_path / "layers.snapshot.json"

    seeded = LayerCatalogService(
        source_url="https://example.test/layers.json",
        snapshot_path=snapshot_path,
    )

    async def fake_seed_fetch(*, headers=None):
        return (
            200,
            {
                "layers": [
                    {
                        "name": "Yehorivka_AAS_v2",
                        "factions": ["PLA"],
                    }
                ]
            },
            {},
        )

    seeded._fetch_json_with_metadata = fake_seed_fetch
    await seeded.sync_once()
    assert snapshot_path.exists()

    restored = LayerCatalogService(
        source_url="https://example.test/layers.json",
        snapshot_path=snapshot_path,
    )

    async def fake_failure(*, headers=None):
        raise RuntimeError("remote source unavailable")

    restored._fetch_json_with_metadata = fake_failure
    catalog = await restored.initialize()

    assert catalog.has_layer("yehorivka_aas_v2")
    assert catalog.has_faction("pla")
    health = restored.health()
    assert health.has_catalog is True
    assert health.fetch_failed is True
    assert health.status == "degraded"
    assert "remote source unavailable" in health.last_error
