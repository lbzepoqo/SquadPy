"""Connector abstractions and lifecycle helpers."""

from squadpy.connectors.base import Connector, ConnectorState
from squadpy.connectors.battlemetrics import BattleMetricsConnector, BattleMetricsPlayer
from squadpy.connectors.lifecycle import ConnectorLifecycleError, ConnectorManager, ConnectorResult

__all__ = [
    "BattleMetricsConnector",
    "BattleMetricsPlayer",
    "Connector",
    "ConnectorLifecycleError",
    "ConnectorManager",
    "ConnectorResult",
    "ConnectorState",
]
