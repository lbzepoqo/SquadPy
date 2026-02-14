"""Contract tests for P1 admin-command source normalization metadata."""

from pathlib import Path

import pytest

from squadpy.events.types import (
    AdminBroadcast,
    NextLayerSet,
    PlayerBanned,
    PlayerKicked,
    PlayerWarned,
    SeedingThresholdUp,
)
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser]

ADMIN_COMMAND_NORMALIZATION_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "parser"
    / "admin_command_normalization_lines.txt"
)


def test_admin_command_origin_metadata_is_normalized_consistently() -> None:
    """P1-EVT-011: admin-command events emit consistent source/source_detail metadata."""
    lines = ADMIN_COMMAND_NORMALIZATION_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
    store = EventStore()
    emitted: list[object] = []

    for line in lines:
        parsed = match_line(line.strip(), store)
        if parsed is not None:
            emitted.append(parsed)
        emitted.extend(store.drain_pending_events())

    broadcast = next(event for event in emitted if isinstance(event, AdminBroadcast))
    warned = next(event for event in emitted if isinstance(event, PlayerWarned))
    kicked = next(event for event in emitted if isinstance(event, PlayerKicked))
    next_layer = next(event for event in emitted if isinstance(event, NextLayerSet))
    threshold_up = next(event for event in emitted if isinstance(event, SeedingThresholdUp))
    banned = next(event for event in emitted if isinstance(event, PlayerBanned))

    assert broadcast.source == "RCON"
    assert broadcast.source_detail == "RCON"

    assert warned.source == "IN_GAME"
    assert warned.source_detail.startswith("player 6.")

    assert kicked.source == "IN_GAME"
    assert kicked.source_detail.startswith("player 6.")

    assert next_layer.source == "IN_GAME"
    assert next_layer.source_detail.startswith("player 6.")

    assert threshold_up.source == "IN_GAME"
    assert threshold_up.source_detail.startswith("player 6.")

    assert banned.source == "IN_GAME"
    assert banned.source_detail.startswith("player 77.")
