"""SquadPy entry point: python -m squadpy"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Literal, Sequence, cast

from squadpy.config import (
    DatabaseConfig,
    LoggingConfig,
    RuntimeConfig,
    ServerConfig,
    load_config,
)
from squadpy.multi_server import (
    MultiServerRuntime,
    ServerRuntimeDefinition,
    discover_server_runtime_definitions,
)
from squadpy.server import SquadPyServer

RuntimeMode = Literal["auto", "single", "multi"]


async def _run_multi_server_runtime(runtime: MultiServerRuntime) -> None:
    await runtime.start()
    await runtime.wait()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SquadPy runtime.")
    parser.add_argument(
        "--mode",
        choices=["auto", "single", "multi"],
        help="Runtime mode override. Defaults to auto (or env/config selection).",
    )
    return parser


def _normalize_runtime_mode(value: str, *, source: str) -> RuntimeMode:
    normalized = value.strip().lower()
    if normalized not in {"auto", "single", "multi"}:
        raise ValueError(
            f"Invalid runtime mode from {source}: {value!r}. Expected one of: auto, single, multi.",
        )
    return cast(RuntimeMode, normalized)


def _resolve_runtime_mode(
    *,
    cli_mode: str | None,
    config_dir: Path,
    environ: dict[str, str] | None = None,
) -> RuntimeMode:
    if cli_mode:
        return _normalize_runtime_mode(cli_mode, source="--mode")

    env = environ or dict(os.environ)
    env_mode = env.get("SQUADPY_RUNTIME_MODE", "").strip()
    if env_mode:
        return _normalize_runtime_mode(env_mode, source="SQUADPY_RUNTIME_MODE")

    try:
        runtime_config = load_config(RuntimeConfig, config_dir / "runtime.toml")
    except FileNotFoundError:
        return "auto"
    return runtime_config.mode


def _run_multi_server(definitions: list[ServerRuntimeDefinition]) -> None:
    runtime = MultiServerRuntime.from_definitions(definitions)
    asyncio.run(_run_multi_server_runtime(runtime))


def _run_single_server(base_dir: Path, config_dir: Path) -> None:
    try:
        server_config = load_config(ServerConfig, config_dir / "server.toml")
    except Exception as e:
        print(f"Error loading server.toml: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        logging_config = load_config(LoggingConfig, config_dir / "logging.toml")
    except FileNotFoundError:
        logging_config = LoggingConfig()
    except Exception as e:
        print(f"Error loading logging.toml: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        db_config = load_config(DatabaseConfig, config_dir / "database.toml")
    except FileNotFoundError:
        db_config = None
    except Exception as e:
        print(f"Error loading database.toml: {e}", file=sys.stderr)
        sys.exit(1)

    server = SquadPyServer(
        server_config=server_config,
        logging_config=logging_config,
        base_dir=base_dir,
        db_config=db_config,
    )

    asyncio.run(server.start())


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    base_dir = Path.cwd()
    config_dir = base_dir / "config"

    try:
        mode = _resolve_runtime_mode(cli_mode=args.mode, config_dir=config_dir)
    except Exception as e:
        print(f"Error resolving runtime mode: {e}", file=sys.stderr)
        sys.exit(1)

    if mode in {"auto", "multi"}:
        try:
            multi_server_definitions = discover_server_runtime_definitions(base_dir)
        except Exception as e:
            print(f"Error loading multi-server definitions: {e}", file=sys.stderr)
            sys.exit(1)

        if multi_server_definitions:
            _run_multi_server(multi_server_definitions)
            return
        if mode == "multi":
            print(
                "Runtime mode is 'multi' but no server definitions were found under config/servers/*/server.toml.",
                file=sys.stderr,
            )
            sys.exit(1)

    _run_single_server(base_dir, config_dir)


if __name__ == "__main__":
    main()
