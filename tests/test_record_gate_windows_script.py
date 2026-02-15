"""Tests for scripts/record_gate_windows.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [".venv/bin/python", "scripts/record_gate_windows.py", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_record_gate_windows_creates_ledger_and_evidence(tmp_path: Path) -> None:
    tracking_file = tmp_path / "gate-window-tracking.md"
    evidence_dir = tmp_path / "evidence"

    result = _run_script(
        "--date",
        "2026-02-16",
        "--skip-test-runs",
        "--contract-status",
        "pass",
        "--integration-status",
        "pass",
        "--sev1",
        "none",
        "--notes",
        "day-0 baseline",
        "--tracking-file",
        str(tracking_file),
        "--evidence-dir",
        str(evidence_dir),
    )
    assert result.returncode == 0, result.stderr

    tracking_text = tracking_file.read_text(encoding="utf-8")
    assert "| 2026-02-16 | pass | pass | none |" in tracking_text
    assert "day-0 baseline" in tracking_text

    evidence_path = evidence_dir / "2026-02-16.json"
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["gate_status"]["gate_002_contract_ci"] == "pass"
    assert evidence["gate_status"]["gate_003_integration_ci"] == "pass"
    assert evidence["gate_status"]["gate_004_sev1"] == "none"


def test_record_gate_windows_upserts_existing_date_row(tmp_path: Path) -> None:
    tracking_file = tmp_path / "gate-window-tracking.md"
    evidence_dir = tmp_path / "evidence"

    first = _run_script(
        "--date",
        "2026-02-16",
        "--skip-test-runs",
        "--contract-status",
        "pass",
        "--integration-status",
        "fail",
        "--sev1",
        "unknown",
        "--notes",
        "first pass",
        "--tracking-file",
        str(tracking_file),
        "--evidence-dir",
        str(evidence_dir),
    )
    assert first.returncode == 0, first.stderr

    second = _run_script(
        "--date",
        "2026-02-16",
        "--skip-test-runs",
        "--contract-status",
        "pass",
        "--integration-status",
        "pass",
        "--sev1",
        "none",
        "--notes",
        "updated",
        "--tracking-file",
        str(tracking_file),
        "--evidence-dir",
        str(evidence_dir),
    )
    assert second.returncode == 0, second.stderr

    rows = [
        line
        for line in tracking_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("| 2026-02-16 |")
    ]
    assert len(rows) == 1
    assert "| 2026-02-16 | pass | pass | none |" in rows[0]
    assert "updated" in rows[0]
