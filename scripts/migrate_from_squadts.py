#!/usr/bin/env python3
"""Report-first SquadTS migration analyzer (default: dry-run, no writes)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from squadpy.migration.squadts import analyze_squadts_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze a SquadTS JSON config and print a migration inventory report.",
    )
    parser.add_argument(
        "config_path",
        type=Path,
        help="Path to SquadTS config JSON to analyze.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON report. Omitted by default to preserve dry-run/no-write mode.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        report = analyze_squadts_file(args.config_path)
    except FileNotFoundError:
        parser.error(f"Config file not found: {args.config_path}")
    except ValueError as exc:
        parser.error(str(exc))

    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["dry_run"] = False
        report["writes"] = [str(args.output)]

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
