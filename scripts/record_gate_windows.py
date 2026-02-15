#!/usr/bin/env python3
"""Record daily tracking evidence for GATE-002, GATE-003, and GATE-004."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

STATUS_CHOICES = ("pass", "fail", "unknown")
SEV1_CHOICES = ("none", "yes", "unknown")

DEFAULT_TRACKING_FILE = Path("docs/plans/gates/gate-window-tracking.md")
DEFAULT_EVIDENCE_DIR = Path("tmp/gate-windows")

CONTRACT_COMMAND: list[str] = [".venv/bin/python", "-m", "pytest", "-m", "contract", "-q"]
INTEGRATION_COMMANDS: list[list[str]] = [
    [
        ".venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "tests/test_discord_integration.py",
        "tests/test_plugin_chat_bridge.py",
        "tests/test_plugin_admin_request.py",
    ],
    [
        ".venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "tests/test_rcon_client.py",
        "tests/test_rcon_helpers.py",
        "tests/test_rcon_protocol.py",
        "tests/test_server.py",
    ],
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record daily gate-window tracking status and evidence.",
    )
    parser.add_argument(
        "--date",
        dest="entry_date",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="UTC date for the entry (YYYY-MM-DD). Defaults to today's UTC date.",
    )
    parser.add_argument(
        "--tracking-file",
        type=Path,
        default=DEFAULT_TRACKING_FILE,
        help=f"Ledger markdown path (default: {DEFAULT_TRACKING_FILE}).",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=DEFAULT_EVIDENCE_DIR,
        help=f"Local evidence directory (default: {DEFAULT_EVIDENCE_DIR}).",
    )
    parser.add_argument(
        "--sev1",
        choices=SEV1_CHOICES,
        default="unknown",
        help="Whether a Sev-1 incident occurred for the day.",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional free-form notes for this day.",
    )
    parser.add_argument(
        "--skip-test-runs",
        action="store_true",
        help="Skip local pytest command runs and use explicit/manual statuses.",
    )
    parser.add_argument(
        "--contract-status",
        choices=STATUS_CHOICES,
        default=None,
        help="Optional override/manual value for contract status.",
    )
    parser.add_argument(
        "--integration-status",
        choices=STATUS_CHOICES,
        default=None,
        help="Optional override/manual value for integration status.",
    )
    return parser


def _run_command(command: list[str]) -> dict[str, object]:
    started = time.perf_counter()
    result = subprocess.run(command, text=True, capture_output=True)
    elapsed_seconds = round(time.perf_counter() - started, 3)
    return {
        "command": command,
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "elapsed_seconds": elapsed_seconds,
        "stdout_tail": (result.stdout or "").splitlines()[-20:],
        "stderr_tail": (result.stderr or "").splitlines()[-20:],
    }


def _derive_status(results: list[dict[str, object]]) -> str:
    if not results:
        return "unknown"
    return "pass" if all(bool(item["passed"]) for item in results) else "fail"


def _ensure_tracking_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "# GATE-002/003/004 Daily Tracking Ledger\n\n"
            "Date basis: UTC day boundaries.\n\n"
            "Use `scripts/record_gate_windows.py` to append/update daily entries and evidence refs.\n\n"
            "| Date (UTC) | Contract CI (`GATE-002`) | Integration CI (`GATE-003`) | "
            "Sev-1 (`GATE-004`) | Evidence | Notes |\n"
            "|---|---|---|---|---|---|\n"
        ),
        encoding="utf-8",
    )


def _upsert_tracking_row(
    path: Path,
    *,
    entry_date: str,
    contract_status: str,
    integration_status: str,
    sev1: str,
    evidence_ref: str,
    notes: str,
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    normalized_notes = notes.replace("|", "/").strip() or "-"
    row = (
        f"| {entry_date} | {contract_status} | {integration_status} | {sev1} | "
        f"`{evidence_ref}` | {normalized_notes} |"
    )
    prefix = f"| {entry_date} |"

    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = row
            break
    else:
        lines.append(row)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    command_results: dict[str, object] = {
        "contract": None,
        "integration_discord_matrix": None,
        "integration_rcon_matrix": None,
    }

    if args.skip_test_runs:
        contract_status = args.contract_status or "unknown"
        integration_status = args.integration_status or "unknown"
    else:
        contract_result = _run_command(CONTRACT_COMMAND)
        integration_discord = _run_command(INTEGRATION_COMMANDS[0])
        integration_rcon = _run_command(INTEGRATION_COMMANDS[1])

        command_results["contract"] = contract_result
        command_results["integration_discord_matrix"] = integration_discord
        command_results["integration_rcon_matrix"] = integration_rcon

        contract_status = _derive_status([contract_result])
        integration_status = _derive_status([integration_discord, integration_rcon])

    if args.contract_status is not None:
        contract_status = args.contract_status
    if args.integration_status is not None:
        integration_status = args.integration_status

    _ensure_tracking_file(args.tracking_file)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    evidence_path = args.evidence_dir / f"{args.entry_date}.json"
    evidence = {
        "date_utc": args.entry_date,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "gate_status": {
            "gate_002_contract_ci": contract_status,
            "gate_003_integration_ci": integration_status,
            "gate_004_sev1": args.sev1,
        },
        "notes": args.notes,
        "commands": command_results,
    }
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    _upsert_tracking_row(
        args.tracking_file,
        entry_date=args.entry_date,
        contract_status=contract_status,
        integration_status=integration_status,
        sev1=args.sev1,
        evidence_ref=evidence_path.as_posix(),
        notes=args.notes,
    )

    print(
        json.dumps(
            {
                "entry_date": args.entry_date,
                "contract_status": contract_status,
                "integration_status": integration_status,
                "sev1": args.sev1,
                "tracking_file": str(args.tracking_file),
                "evidence_path": str(evidence_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
