"""Connector abstractions and lifecycle helpers."""

from squadpy.connectors.base import Connector, ConnectorState
from squadpy.connectors.battlemetrics import BattleMetricsConnector, BattleMetricsPlayer
from squadpy.connectors.community_ban_list import (
    CommunityBan,
    CommunityBanListConnector,
    CommunityBanListPlayer,
)
from squadpy.connectors.lifecycle import ConnectorLifecycleError, ConnectorManager, ConnectorResult

__all__ = [
    "BattleMetricsConnector",
    "BattleMetricsPlayer",
    "CommunityBan",
    "CommunityBanListConnector",
    "CommunityBanListPlayer",
    "Connector",
    "ConnectorLifecycleError",
    "ConnectorManager",
    "ConnectorResult",
    "ConnectorState",
]
