"""Contract tests for the P0 PlayerKicked parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import PlayerKicked
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser, pytest.mark.p0]

PLAYER_KICKED_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "player_kicked_line.txt"
)


def test_player_kicked_contract_fixture_parses_expected_fields() -> None:
    """P0-EVT-002: parser fixture emits PlayerKicked with expected payload."""
    line = PLAYER_KICKED_FIXTURE_PATH.read_text(encoding="utf-8").strip()
    event = match_line(line, EventStore())

    assert isinstance(event, PlayerKicked)
    assert event.event_name == "player_kicked"
    assert event.admin == "Remote admin"
    assert event.player.name == "Rellmi"
    assert event.reason == "Spamming in command chat."
    assert event.source == "RCON"
    assert event.source_detail == "RCON"
