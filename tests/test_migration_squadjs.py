"""Unit tests for the SquadJS migration analyzer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from squadpy.migration.squadjs import analyze_squadjs_file

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_CONFIG = Path(__file__).parent / "fixtures" / "migration" / "squadjs.config.json"


def test_analyze_squadjs_file_builds_inventory_summary() -> None:
    report = analyze_squadjs_file(SAMPLE_CONFIG)

    assert report["source"] == "squadjs"
    assert report["dry_run"] is True
    assert report["summary"] == {
        "total": 8,
        "safe": 6,
        "review": 1,
        "unsupported": 1,
    }

    plugin_rows = [item for item in report["inventory"] if item["source_key"].startswith("plugins[")]
    assert plugin_rows == [
        {
            "source_key": "plugins[0]",
            "source_value": "AdminRequest",
            "target": "admin_request",
            "category": "safe",
            "note": "Direct SquadPy plugin equivalent is available.",
        },
        {
            "source_key": "plugins[1]",
            "source_value": "public-commands",
            "target": "chat_commands",
            "category": "review",
            "note": "Command names and permission rules should be reviewed before cutover.",
        },
        {
            "source_key": "plugins[2]",
            "source_value": "legacy-custom-plugin",
            "target": None,
            "category": "unsupported",
            "note": "No SquadPy equivalent is currently mapped.",
        },
    ]


def test_cli_default_mode_is_dry_run_and_no_write(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "migrate_from_squadjs.py"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, str(script_path), str(SAMPLE_CONFIG)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    report = json.loads(result.stdout)
    assert report["dry_run"] is True
    assert report["writes"] == []
    assert list(tmp_path.iterdir()) == []
