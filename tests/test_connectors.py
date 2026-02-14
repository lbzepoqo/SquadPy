"""Tests for connector abstraction and lifecycle manager."""

from __future__ import annotations

from collections.abc import MutableSequence

import pytest

from squadpy.connectors import (
    Connector,
    ConnectorLifecycleError,
    ConnectorManager,
    ConnectorState,
)


class RecordingConnector(Connector):
    def __init__(
        self,
        name: str,
        calls: MutableSequence[str],
        *,
        fail_start: bool = False,
        fail_stop: bool = False,
    ) -> None:
        super().__init__(name=name)
        self._calls = calls
        self._fail_start = fail_start
        self._fail_stop = fail_stop

    async def _start(self) -> None:
        self._calls.append(f"{self.name}:start")
        if self._fail_start:
            raise RuntimeError(f"{self.name} failed to start")

    async def _stop(self) -> None:
        self._calls.append(f"{self.name}:stop")
        if self._fail_stop:
            raise RuntimeError(f"{self.name} failed to stop")


class TestConnectorInterface:
    async def test_state_transitions_for_successful_lifecycle(self) -> None:
        calls: list[str] = []
        connector = RecordingConnector("alpha", calls)

        assert connector.state == ConnectorState.STOPPED
        assert connector.running is False

        await connector.start()
        assert connector.state == ConnectorState.RUNNING
        assert connector.running is True

        await connector.stop()
        assert connector.state == ConnectorState.STOPPED
        assert connector.running is False
        assert calls == ["alpha:start", "alpha:stop"]

    async def test_start_failure_moves_connector_to_failed_state(self) -> None:
        connector = RecordingConnector("alpha", [], fail_start=True)

        with pytest.raises(RuntimeError, match="failed to start"):
            await connector.start()

        assert connector.state == ConnectorState.FAILED

    async def test_stop_failure_moves_connector_to_failed_state(self) -> None:
        connector = RecordingConnector("alpha", [], fail_stop=True)
        await connector.start()

        with pytest.raises(RuntimeError, match="failed to stop"):
            await connector.stop()

        assert connector.state == ConnectorState.FAILED


class TestConnectorManager:
    async def test_duplicate_registration_raises(self) -> None:
        manager = ConnectorManager()
        manager.register(RecordingConnector("alpha", []))

        with pytest.raises(ValueError, match="already registered"):
            manager.register(RecordingConnector("alpha", []))

    async def test_start_all_rolls_back_started_connectors_on_failure(self) -> None:
        calls: list[str] = []
        first = RecordingConnector("alpha", calls)
        second = RecordingConnector("beta", calls, fail_start=True)
        third = RecordingConnector("gamma", calls)

        manager = ConnectorManager()
        manager.register(first)
        manager.register(second)
        manager.register(third)

        with pytest.raises(ConnectorLifecycleError, match="Failed to start connector 'beta'"):
            await manager.start_all()

        assert calls == [
            "alpha:start",
            "beta:start",
            "alpha:stop",
        ]
        assert first.state == ConnectorState.STOPPED
        assert second.state == ConnectorState.FAILED
        assert third.state == ConnectorState.STOPPED

    async def test_stop_all_runs_reverse_registration_order(self) -> None:
        calls: list[str] = []
        first = RecordingConnector("alpha", calls)
        second = RecordingConnector("beta", calls)
        third = RecordingConnector("gamma", calls)

        manager = ConnectorManager()
        manager.register(first)
        manager.register(second)
        manager.register(third)

        await manager.start_all()
        results = await manager.stop_all()

        assert calls == [
            "alpha:start",
            "beta:start",
            "gamma:start",
            "gamma:stop",
            "beta:stop",
            "alpha:stop",
        ]
        assert [result.name for result in results] == ["gamma", "beta", "alpha"]
        assert all(result.ok for result in results)

