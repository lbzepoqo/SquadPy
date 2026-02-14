"""Contract tests for P1 seeding threshold transition parser events."""

from pathlib import Path

import pytest

from squadpy.events.types import SeedingThresholdUp, SeedingThresholdDown
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser]

SEEDING_THRESHOLD_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "parser"
    / "seeding_threshold_transition_lines.txt"
)


def test_seeding_threshold_transition_contract_fixture_parses_expected_fields() -> None:
    """P1-EVT-010: parser fixture emits seeding-threshold up/down transitions."""
    lines = SEEDING_THRESHOLD_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
    store = EventStore()

    emitted: list[object] = []
    for line in lines:
        parsed = match_line(line.strip(), store)
        if parsed is not None:
            emitted.append(parsed)
        emitted.extend(store.drain_pending_events())

    ups = [event for event in emitted if isinstance(event, SeedingThresholdUp)]
    downs = [event for event in emitted if isinstance(event, SeedingThresholdDown)]
    assert len(ups) == 1
    assert len(downs) == 1

    up = ups[0]
    assert up.event_name == "seeding_threshold_up"
    assert up.old_threshold == 15
    assert up.new_threshold == 20
    assert up.source == "RCON"

    down = downs[0]
    assert down.event_name == "seeding_threshold_down"
    assert down.old_threshold == 20
    assert down.new_threshold == 15
    assert down.source == "RCON"
