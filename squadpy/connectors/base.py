"""Connector abstraction and lifecycle state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class ConnectorState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


class Connector(ABC):
    """Base class for connectors managed by the runtime."""

    def __init__(self, *, name: str):
        self._name = name
        self._state = ConnectorState.STOPPED

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> ConnectorState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state == ConnectorState.RUNNING

    async def start(self) -> None:
        if self._state == ConnectorState.RUNNING:
            return
        self._state = ConnectorState.STARTING
        try:
            await self._start()
        except Exception:
            self._state = ConnectorState.FAILED
            raise
        self._state = ConnectorState.RUNNING

    async def stop(self) -> None:
        if self._state == ConnectorState.STOPPED:
            return
        self._state = ConnectorState.STOPPING
        try:
            await self._stop()
        except Exception:
            self._state = ConnectorState.FAILED
            raise
        self._state = ConnectorState.STOPPED

    async def close(self) -> None:
        """Alias used by existing call sites."""
        await self.stop()

    @abstractmethod
    async def _start(self) -> None:
        """Connector-specific start hook."""

    @abstractmethod
    async def _stop(self) -> None:
        """Connector-specific shutdown hook."""

