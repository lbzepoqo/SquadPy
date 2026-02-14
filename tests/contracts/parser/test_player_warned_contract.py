"""Contract tests for the P0 PlayerWarned parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import PlayerWarned
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser, pytest.mark.p0]

PLAYER_WARNED_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "player_warned_line.txt"
)


def test_player_warned_contract_fixture_parses_expected_fields() -> None:
    """P0-EVT-001: parser fixture emits PlayerWarned with expected payload."""
    line = PLAYER_WARNED_FIXTURE_PATH.read_text(encoding="utf-8").strip()
    event = match_line(line, EventStore())

    assert isinstance(event, PlayerWarned)
    assert event.event_name == "player_warned"
    assert event.admin == "Remote admin"
    assert event.player.name == "Rellmi"
    assert event.reason == "Type !commands to know the server commands."
    assert event.source == "RCON"
