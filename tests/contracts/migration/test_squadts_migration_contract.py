"""Contract coverage for the SquadTS migration analyzer."""

from __future__ import annotations

from pathlib import Path

import pytest

from squadpy.migration.squadts import analyze_squadts_file

pytestmark = [pytest.mark.contract, pytest.mark.migration, pytest.mark.p0]

SAMPLE_CONFIG = Path(__file__).parents[2] / "fixtures" / "migration" / "squadts.config.json"


def test_squadts_sample_config_generates_inventory_in_dry_run_mode() -> None:
    """P0-MIG-002: default report mode should produce inventory with no writes."""
    report = analyze_squadts_file(SAMPLE_CONFIG)

    assert report["source"] == "squadts"
    assert report["dry_run"] is True
    assert report["writes"] == []
    assert report["summary"]["total"] >= 1
    assert report["summary"]["unsupported"] >= 1
