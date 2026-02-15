#!/usr/bin/env python3
"""Lint migrated TOML mappings and emit a categorized remediation report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from squadpy.migration.toml_linter import lint_migrated_toml


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lint migrated TOML mappings and emit safe/review/unsupported findings.",
    )
    parser.add_argument(
        "config_path",
        type=Path,
        help="Path to migrated TOML mapping file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON lint report. Omitted by default to avoid writes.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.config_path.exists():
        parser.error(f"Config file not found: {args.config_path}")

    report = lint_migrated_toml(args.config_path)
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["writes"] = [str(args.output)]

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
