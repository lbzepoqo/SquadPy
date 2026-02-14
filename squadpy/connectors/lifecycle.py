"""Connector registration and lifecycle orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from squadpy.connectors.base import Connector

logger = logging.getLogger("squadpy.connectors")


class ConnectorLifecycleError(RuntimeError):
    """Raised when connector startup fails."""


@dataclass(slots=True)
class ConnectorResult:
    name: str
    ok: bool
    detail: str


class ConnectorManager:
    """Start/stop connectors with deterministic ordering."""

    def __init__(self) -> None:
        self._connectors: list[Connector] = []
        self._by_name: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        if connector.name in self._by_name:
            raise ValueError(f"Connector '{connector.name}' is already registered")
        self._connectors.append(connector)
        self._by_name[connector.name] = connector

    def get(self, name: str) -> Connector | None:
        return self._by_name.get(name)

    def all(self) -> tuple[Connector, ...]:
        return tuple(self._connectors)

    async def start_all(self) -> list[ConnectorResult]:
        started: list[Connector] = []
        results: list[ConnectorResult] = []
        for connector in self._connectors:
            try:
                await connector.start()
                started.append(connector)
                results.append(ConnectorResult(name=connector.name, ok=True, detail="started"))
            except Exception as exc:
                results.append(ConnectorResult(name=connector.name, ok=False, detail=str(exc)))
                for started_connector in reversed(started):
                    try:
                        await started_connector.stop()
                    except Exception:
                        logger.exception("Failed to stop connector %s during rollback", started_connector.name)
                raise ConnectorLifecycleError(
                    f"Failed to start connector '{connector.name}'"
                ) from exc
        return results

    async def stop_all(self) -> list[ConnectorResult]:
        results: list[ConnectorResult] = []
        for connector in reversed(self._connectors):
            try:
                await connector.stop()
                results.append(ConnectorResult(name=connector.name, ok=True, detail="stopped"))
            except Exception as exc:
                results.append(ConnectorResult(name=connector.name, ok=False, detail=str(exc)))
        return results

