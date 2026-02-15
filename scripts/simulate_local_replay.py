#!/usr/bin/env python3
"""Run a local plugin replay using log and RCON fixtures."""

from __future__ import annotations

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from squadpy.simulation import LocalSimulationHarness


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay log and RCON fixtures through plugins for local development loops.",
    )
    parser.add_argument(
        "log_fixture",
        type=Path,
        help="Path to a log fixture file (line-by-line replay).",
    )
    parser.add_argument(
        "--rcon-fixture",
        type=Path,
        help="Optional JSON fixture for deterministic RCON command responses.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Repository root for default plugins/config paths (default: current directory).",
    )
    parser.add_argument(
        "--plugins-dir",
        type=Path,
        help="Override plugin directory (default: <base-dir>/plugins).",
    )
    parser.add_argument(
        "--plugin-config-dir",
        type=Path,
        help="Override plugin config directory (default: <base-dir>/config/plugins).",
    )
    parser.add_argument(
        "--plugin",
        action="append",
        dest="plugins",
        default=[],
        help="Plugin dir name to include; repeat to include more. Defaults to all discovered.",
    )
    parser.add_argument(
        "--skip-periodic-once",
        action="store_true",
        help="Skip one-shot periodic method execution after log replay.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path for JSON simulation summary.",
    )
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    plugins_dir = args.plugins_dir or (args.base_dir / "plugins")
    plugin_config_dir = args.plugin_config_dir or (args.base_dir / "config" / "plugins")

    harness = LocalSimulationHarness.from_fixture_files(
        log_fixture=args.log_fixture,
        rcon_fixture=args.rcon_fixture,
        plugins_dir=plugins_dir,
        plugin_config_dir=plugin_config_dir,
        plugin_names=args.plugins,
        run_periodic_once=not args.skip_periodic_once,
    )
    result = await harness.run()
    return result.as_dict()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        payload = asyncio.run(_run(args))
    except FileNotFoundError as exc:
        parser.error(str(exc))
    except ValueError as exc:
        parser.error(str(exc))

    rendered = json.dumps(payload, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
