"""Contract coverage for the SquadJS migration analyzer."""

from __future__ import annotations

from pathlib import Path

import pytest

from squadpy.migration.squadjs import analyze_squadjs_file

pytestmark = [pytest.mark.contract, pytest.mark.migration, pytest.mark.p0]

SAMPLE_CONFIG = Path(__file__).parents[2] / "fixtures" / "migration" / "squadjs.config.json"


def test_squadjs_sample_config_generates_inventory_in_dry_run_mode() -> None:
    """P0-MIG-001: default report mode should produce inventory with no writes."""
    report = analyze_squadjs_file(SAMPLE_CONFIG)

    assert report["source"] == "squadjs"
    assert report["dry_run"] is True
    assert report["writes"] == []
    assert report["summary"]["total"] >= 1
    assert report["summary"]["unsupported"] >= 1
