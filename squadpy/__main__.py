"""SquadPy entry point: python -m squadpy"""

import asyncio
import sys
from pathlib import Path

from squadpy.config import ServerConfig, LoggingConfig, DatabaseConfig, load_config
from squadpy.multi_server import MultiServerRuntime, discover_server_runtime_definitions
from squadpy.server import SquadPyServer


async def _run_multi_server_runtime(runtime: MultiServerRuntime) -> None:
    await runtime.start()
    await runtime.wait()


def main():
    base_dir = Path.cwd()
    config_dir = base_dir / "config"

    try:
        multi_server_definitions = discover_server_runtime_definitions(base_dir)
    except Exception as e:
        print(f"Error loading multi-server definitions: {e}", file=sys.stderr)
        sys.exit(1)

    if multi_server_definitions:
        runtime = MultiServerRuntime.from_definitions(multi_server_definitions)
        asyncio.run(_run_multi_server_runtime(runtime))
        return

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


if __name__ == "__main__":
    main()
