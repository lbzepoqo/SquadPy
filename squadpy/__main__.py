"""SquadPy entry point: python -m squadpy"""

import asyncio
import sys
from pathlib import Path

from squadpy.config import ServerConfig, LoggingConfig, load_config
from squadpy.server import SquadPyServer


def main():
    base_dir = Path.cwd()
    config_dir = base_dir / "config"

    # Load configs
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

    server = SquadPyServer(
        server_config=server_config,
        logging_config=logging_config,
        base_dir=base_dir,
    )

    asyncio.run(server.start())


if __name__ == "__main__":
    main()
