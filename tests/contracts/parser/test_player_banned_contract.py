"""Contract tests for the P0 PlayerBanned parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import PlayerBanned
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser, pytest.mark.p0]

PLAYER_BANNED_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "player_banned_line.txt"
)


def test_player_banned_contract_fixture_parses_expected_fields() -> None:
    """P0-EVT-003: parser fixture emits PlayerBanned with expected payload."""
    lines = PLAYER_BANNED_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
    store = EventStore()
    event = None
    for line in lines:
        parsed = match_line(line.strip(), store)
        if parsed is not None:
            event = parsed

    assert isinstance(event, PlayerBanned)
    assert event.event_name == "player_banned"
    assert event.admin == "N/A"
    assert event.player.eos_id == "00029e5d00e947bbaed1b364814dd427"
    assert event.player.steam_id == "76561198061567555"
    assert event.player.name == "ObsidianHorse47"
    assert event.duration == "1 Day(s)"
    assert event.reason == "Kupal na admin"
    assert event.source == "RCON"
