"""Contract checks for plugin behavior mapping matrix coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from squadpy.migration.squadjs import SQUADJS_PLUGIN_MAPPINGS
from squadpy.migration.squadts import SQUADTS_PLUGIN_MAPPINGS

pytestmark = [pytest.mark.contract, pytest.mark.migration, pytest.mark.p1]

MATRIX_PATH = Path(__file__).parents[3] / "docs" / "plugin-behavior-mapping-matrix.md"


def test_mapping_matrix_covers_known_source_plugin_inventory() -> None:
    """P1-MIG-005: every known source plugin has target/equivalent mapping strategy."""
    assert MATRIX_PATH.exists()
    matrix_sources, matrix_rows = _parse_matrix_rows(MATRIX_PATH)

    expected_sources = set(SQUADJS_PLUGIN_MAPPINGS) | set(SQUADTS_PLUGIN_MAPPINGS)
    missing = sorted(source for source in expected_sources if source not in matrix_sources)
    assert not missing, f"Missing mapping matrix rows for source plugins: {missing}"

    for source in expected_sources:
        row = matrix_rows[source]
        assert row["target"], f"Source plugin {source} must declare target/equivalent."
        assert row["strategy"], f"Source plugin {source} must declare migration strategy."


def _parse_matrix_rows(path: Path) -> tuple[set[str], dict[str, dict[str, str]]]:
    sources: set[str] = set()
    rows: dict[str, dict[str, str]] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) < 4:
            continue
        if cells[0] == "Source plugin":
            continue
        if set(cells[0]) <= {"-"}:
            continue

        source = cells[0].strip("`").lower()
        sources.add(source)
        rows[source] = {
            "target": cells[1].strip("`"),
            "category": cells[2].strip("`"),
            "strategy": cells[3],
        }

    return sources, rows
