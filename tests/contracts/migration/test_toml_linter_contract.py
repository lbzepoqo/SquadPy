"""Contract coverage for migrated TOML linter/report output."""

from __future__ import annotations

from pathlib import Path

import pytest

from squadpy.migration.toml_linter import lint_migrated_toml

pytestmark = [pytest.mark.contract, pytest.mark.migration, pytest.mark.p0]

SAMPLE_TOML = Path(__file__).parents[2] / "fixtures" / "migration" / "migrated_inventory.toml"


def test_migrated_toml_linter_contract_emits_categorized_fixups() -> None:
    """P0-MIG-003: linter output includes severities, fixups, and mapping categories."""
    report = lint_migrated_toml(SAMPLE_TOML)

    summary = report["summary"]
    assert summary["safe"] >= 1
    assert summary["review"] >= 1
    assert summary["unsupported"] >= 1

    for finding in report["findings"]:
        assert finding["category"] in {"safe", "review", "unsupported"}
        assert finding["severity"] in {"info", "warning", "error"}
        assert finding["fixup"]
