"""Unit tests for migrated TOML lint/report tooling."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from squadpy.migration.toml_linter import lint_migrated_toml

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_TOML = Path(__file__).parent / "fixtures" / "migration" / "migrated_inventory.toml"


def test_linter_emits_fixups_severity_and_mapping_categories() -> None:
    report = lint_migrated_toml(SAMPLE_TOML)
    summary = report["summary"]

    assert report["source"] == "migrated_toml_linter"
    assert summary["safe"] == 1
    assert summary["review"] == 1
    assert summary["unsupported"] == 1
    assert summary["info"] == 1
    assert summary["warning"] == 1
    assert summary["error"] == 1

    findings = report["findings"]
    assert len(findings) == 3
    assert {finding["category"] for finding in findings} == {"safe", "review", "unsupported"}
    assert all(finding["fixup"] for finding in findings)


def test_cli_default_mode_does_not_write_report_file(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "lint_migrated_toml.py"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, str(script_path), str(SAMPLE_TOML)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    report = json.loads(result.stdout)
    assert report["writes"] == []
    assert list(tmp_path.iterdir()) == []
