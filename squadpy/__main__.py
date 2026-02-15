"""SquadPy entry point: python -m squadpy"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RuntimeSelection:
    mode: RuntimeMode
    require_per_server_database: bool = False


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


def _parse_env_bool(value: str, *, source: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"Invalid boolean from {source}: {value!r}. Expected one of: "
        f"true/false, 1/0, yes/no, on/off.",
    )


def _resolve_runtime_selection(
    *,
    cli_mode: str | None,
    config_dir: Path,
    environ: dict[str, str] | None = None,
) -> RuntimeSelection:
    env = environ or dict(os.environ)

    if cli_mode:
        selected_mode = _normalize_runtime_mode(cli_mode, source="--mode")
    else:
        env_mode = env.get("SQUADPY_RUNTIME_MODE", "").strip()
        if env_mode:
            selected_mode = _normalize_runtime_mode(env_mode, source="SQUADPY_RUNTIME_MODE")
        else:
            try:
                runtime_config = load_config(RuntimeConfig, config_dir / "runtime.toml")
            except FileNotFoundError:
                runtime_config = RuntimeConfig()
            selected_mode = runtime_config.mode

    env_require_per_server_database = env.get(
        "SQUADPY_REQUIRE_PER_SERVER_DATABASE",
        "",
    ).strip()
    if env_require_per_server_database:
        require_per_server_database = _parse_env_bool(
            env_require_per_server_database,
            source="SQUADPY_REQUIRE_PER_SERVER_DATABASE",
        )
    else:
        try:
            runtime_config = load_config(RuntimeConfig, config_dir / "runtime.toml")
        except FileNotFoundError:
            runtime_config = RuntimeConfig()
        require_per_server_database = runtime_config.require_per_server_database

    return RuntimeSelection(
        mode=selected_mode,
        require_per_server_database=require_per_server_database,
    )


def _validate_multi_server_database_configuration(
    definitions: list[ServerRuntimeDefinition],
    *,
    base_dir: Path,
    require_per_server_database: bool,
) -> None:
    shared_database_path = base_dir / "config" / "database.toml"
    shared_database_exists = shared_database_path.exists()

    for definition in definitions:
        per_server_database_path = base_dir / "config" / "servers" / definition.name / "database.toml"
        per_server_database_exists = per_server_database_path.exists()

        if require_per_server_database and not per_server_database_exists:
            print(
                "Runtime is configured with require_per_server_database=true, "
                f"but {per_server_database_path} is missing.",
                file=sys.stderr,
            )
            sys.exit(1)

        if not per_server_database_exists and shared_database_exists:
            print(
                "Warning: multi-server database fallback active for "
                f"'{definition.name}': using shared config/database.toml. "
                f"Add {per_server_database_path} for per-server DB isolation.",
                file=sys.stderr,
            )


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
        selection = _resolve_runtime_selection(
            cli_mode=args.mode,
            config_dir=config_dir,
        )
    except Exception as e:
        print(f"Error resolving runtime mode: {e}", file=sys.stderr)
        sys.exit(1)

    if selection.mode in {"auto", "multi"}:
        try:
            multi_server_definitions = discover_server_runtime_definitions(base_dir)
        except Exception as e:
            print(f"Error loading multi-server definitions: {e}", file=sys.stderr)
            sys.exit(1)

        if multi_server_definitions:
            _validate_multi_server_database_configuration(
                multi_server_definitions,
                base_dir=base_dir,
                require_per_server_database=selection.require_per_server_database,
            )
            _run_multi_server(multi_server_definitions)
            return
        if selection.mode == "multi":
            print(
                "Runtime mode is 'multi' but no server definitions were found under config/servers/*/server.toml.",
                file=sys.stderr,
            )
            sys.exit(1)

    _run_single_server(base_dir, config_dir)


if __name__ == "__main__":
    main()
