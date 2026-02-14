"""Validate the parity fixture manifest structure and references."""

from pathlib import Path
import tomllib

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.parser, pytest.mark.p0]

MANIFEST_PATH = Path(__file__).parents[1] / "fixtures" / "manifest.toml"


def test_log_fixture_manifest_exists_and_is_well_formed() -> None:
    """Manifest includes at least one fixture pack and required metadata fields."""
    assert MANIFEST_PATH.exists()

    manifest = tomllib.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == 1
    assert isinstance(manifest.get("packs"), list)
    assert manifest["packs"], "Fixture manifest must declare at least one pack"

    required_fields = {"id", "kind", "source", "sha256", "line_count", "size_bytes", "notes"}
    for pack in manifest["packs"]:
        assert required_fields.issubset(pack)
        source_path = Path(pack["source"])
        assert source_path.exists(), f"Missing fixture source file: {source_path}"
