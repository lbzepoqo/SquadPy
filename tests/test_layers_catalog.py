"""Tests for shared layer catalog normalization and loading."""

from squadpy.layers import LayerCatalogService, normalize_layers_payload


def test_normalize_layers_payload_extracts_layer_faction_and_vehicle_classes():
    payload = {
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
