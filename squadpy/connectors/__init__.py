"""Connector abstractions and lifecycle helpers."""

from squadpy.connectors.base import Connector, ConnectorState
from squadpy.connectors.lifecycle import ConnectorLifecycleError, ConnectorManager, ConnectorResult

__all__ = [
    "Connector",
    "ConnectorLifecycleError",
    "ConnectorManager",
    "ConnectorResult",
    "ConnectorState",
]

