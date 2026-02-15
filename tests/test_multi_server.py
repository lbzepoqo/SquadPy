"""Tests for one-process multi-server orchestration."""

import asyncio
from pathlib import Path
from typing import cast

import pytest

from squadpy.config import LoggingConfig, ServerConfig
from squadpy.events.types import BaseEvent, PlayerConnected
from squadpy.multi_server import MultiServerRuntime, ServerRuntimeDefinition
from squadpy.server import SquadPyServer


class _FakeServer:
    def __init__(self):
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def start(self) -> None:
        self.started.set()
        await self.stopped.wait()

    async def stop(self) -> None:
        self.stopped.set()


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


class TestMultiServerRuntime:
    def test_requires_at_least_one_server(self) -> None:
        with pytest.raises(ValueError, match="at least one server"):
            MultiServerRuntime({})

    async def test_start_and_stop_manages_all_servers(self) -> None:
        alpha = _FakeServer()
        bravo = _FakeServer()
        runtime = MultiServerRuntime({"alpha": alpha, "bravo": bravo})

        await runtime.start()
        await asyncio.wait_for(alpha.started.wait(), timeout=1.0)
        await asyncio.wait_for(bravo.started.wait(), timeout=1.0)
        assert runtime.running is True

        await runtime.stop()
        assert runtime.running is False

    async def test_wait_without_start_raises(self) -> None:
        runtime = MultiServerRuntime({"alpha": _FakeServer()})
        with pytest.raises(RuntimeError, match="has not been started"):
            await runtime.wait()

    def test_from_definitions_rejects_duplicate_names(self) -> None:
        definitions = [_definition("alpha"), _definition("alpha")]
        with pytest.raises(ValueError, match="duplicate server definition name"):
            MultiServerRuntime.from_definitions(definitions)

    async def test_isolated_contexts_prevent_cross_talk(self) -> None:
        runtime = MultiServerRuntime.from_definitions(
            [_definition("alpha"), _definition("bravo")]
        )

        alpha = cast(SquadPyServer, runtime.get_server("alpha"))
        bravo = cast(SquadPyServer, runtime.get_server("bravo"))

        seen: list[str] = []

        async def handler(event: BaseEvent) -> None:
            seen.append(event.event_name)

        alpha.event_bus.subscribe("player_connected", handler)

        await bravo.event_bus.emit(PlayerConnected())
        assert seen == []

        await alpha.event_bus.emit(PlayerConnected())
        assert seen == ["player_connected"]
