"""Contract tests for the P0 SquadCreated parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import SquadCreated
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser, pytest.mark.p0]

SQUAD_CREATED_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "squad_created_line.txt"
)


def test_squad_created_contract_fixture_parses_expected_fields() -> None:
    """P0-EVT-006: parser fixture emits SquadCreated with expected payload."""
    line = SQUAD_CREATED_FIXTURE_PATH.read_text(encoding="utf-8").strip()
    store = EventStore()
    store.team_ids_by_name["United States Army"] = 1
    event = match_line(line, store)

    assert isinstance(event, SquadCreated)
    assert event.event_name == "squad_created"
    assert event.team_id == 1
    assert event.team_name == "United States Army"
    assert event.squad_id == 1
    assert event.squad_name == "Squad 1"
    assert event.creator.eos_id == "00029e5d00e947bbaed1b364814dd427"
    assert event.creator.name == "ObsidianHorse47"
