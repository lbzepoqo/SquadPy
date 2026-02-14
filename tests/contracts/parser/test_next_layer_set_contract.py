"""Contract tests for the P1 NextLayerSet parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import NextLayerSet
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser]

NEXT_LAYER_SET_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "next_layer_set_lines.txt"
)


def test_next_layer_set_contract_fixture_parses_expected_fields() -> None:
    """P1-EVT-009: parser fixture emits NextLayerSet with normalized source."""
    lines = NEXT_LAYER_SET_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
    store = EventStore()

    emitted: list[object] = []
    for line in lines:
        parsed = match_line(line.strip(), store)
        if parsed is not None:
            emitted.append(parsed)
        emitted.extend(store.drain_pending_events())

    events = [event for event in emitted if isinstance(event, NextLayerSet)]
    assert len(events) == 2

    rcon_event = events[0]
    assert rcon_event.event_name == "next_layer_set"
    assert rcon_event.layer == "BlackCoast_RAAS_v1 AFU+Mechanized TLF+Mechanized"
    assert rcon_event.source == "RCON"
    assert rcon_event.source_detail == "RCON"

    ingame_event = events[1]
    assert ingame_event.layer == "Sumari_Seed_v1 MEI IMF"
    assert ingame_event.source == "IN_GAME"
    assert ingame_event.source_detail.startswith("player 6.")
