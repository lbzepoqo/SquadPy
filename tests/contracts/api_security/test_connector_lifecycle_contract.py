"""Contract tests for connector abstraction lifecycle semantics."""

from collections.abc import MutableSequence

import pytest

from squadpy.connectors import Connector, ConnectorManager, ConnectorState

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p0]


class ContractConnector(Connector):
    def __init__(self, name: str, calls: MutableSequence[str]) -> None:
        super().__init__(name=name)
        self._calls = calls

    async def _start(self) -> None:
        self._calls.append(f"{self.name}:start")

    async def _stop(self) -> None:
        self._calls.append(f"{self.name}:stop")


async def test_connector_lifecycle_order_contract() -> None:
    """P0-CONN-001: connectors start in registration order and stop in reverse."""
    calls: list[str] = []
    discord = ContractConnector("discord", calls)
    moderation = ContractConnector("moderation_api", calls)

    manager = ConnectorManager()
    manager.register(discord)
    manager.register(moderation)

    start_results = await manager.start_all()
    stop_results = await manager.stop_all()

    assert [result.name for result in start_results] == ["discord", "moderation_api"]
    assert [result.name for result in stop_results] == ["moderation_api", "discord"]
    assert calls == [
        "discord:start",
        "moderation_api:start",
        "moderation_api:stop",
        "discord:stop",
    ]
    assert discord.state == ConnectorState.STOPPED
    assert moderation.state == ConnectorState.STOPPED

