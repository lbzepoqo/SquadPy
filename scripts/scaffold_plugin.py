#!/usr/bin/env python3
"""Generate a plugin skeleton with typed hooks and starter tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from squadpy.plugin_scaffolder import scaffold_plugin


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold a SquadPy plugin skeleton under plugins/, tests/, and config/plugins/.",
    )
    parser.add_argument(
        "plugin_name",
        help="Plugin slug/name (for example: my_plugin or 'My Plugin').",
    )
    parser.add_argument(
        "--display-name",
        help="Optional display name for the generated plugin class metadata.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Repository root where files should be generated (default: current directory).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated files when they already exist.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = scaffold_plugin(
            args.plugin_name,
            base_dir=args.base_dir,
            display_name=args.display_name,
            force=args.force,
        )
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))

    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
