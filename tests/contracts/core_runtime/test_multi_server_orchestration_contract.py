"""Contract test for one-process multi-server context isolation."""

from pathlib import Path
from typing import cast

import pytest

from squadpy.config import LoggingConfig, ServerConfig
from squadpy.events.types import BaseEvent, PlayerConnected
from squadpy.multi_server import MultiServerRuntime, ServerRuntimeDefinition
from squadpy.server import SquadPyServer

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]


def _definition(name: str) -> ServerRuntimeDefinition:
    return ServerRuntimeDefinition(
        name=name,
        server_config=ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
        }),
        logging_config=LoggingConfig.model_validate(
            {"level": "INFO", "file": {"enabled": False}}
        ),
        base_dir=Path("/tmp/test"),
    )


async def test_multi_server_contexts_are_isolated() -> None:
    """P2-BEYOND-001: contexts run side-by-side without event cross-talk."""
    runtime = MultiServerRuntime.from_definitions(
        [_definition("alpha"), _definition("bravo")]
    )
    alpha = cast(SquadPyServer, runtime.get_server("alpha"))
    bravo = cast(SquadPyServer, runtime.get_server("bravo"))

    alpha_seen: list[str] = []
    bravo_seen: list[str] = []

    async def on_alpha(event: BaseEvent) -> None:
        alpha_seen.append(event.event_name)

    async def on_bravo(event: BaseEvent) -> None:
        bravo_seen.append(event.event_name)

    alpha.event_bus.subscribe("player_connected", on_alpha)
    bravo.event_bus.subscribe("player_connected", on_bravo)

    await alpha.event_bus.emit(PlayerConnected())
    await bravo.event_bus.emit(PlayerConnected())

    assert alpha_seen == ["player_connected"]
    assert bravo_seen == ["player_connected"]
