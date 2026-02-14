"""Contract tests for the P1 PlayerSwitchedTeam parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import PlayerSwitchedTeam
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser]

PLAYER_SWITCHED_TEAM_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "player_switched_team_lines.txt"
)


def test_player_switched_team_contract_fixture_parses_expected_fields() -> None:
    """P1-EVT-008: parser fixture emits PlayerSwitchedTeam transition payload."""
    lines = PLAYER_SWITCHED_TEAM_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
    store = EventStore()
    emitted: list[object] = []
    for line in lines:
        parsed = match_line(line.strip(), store)
        if parsed is not None:
            emitted.append(parsed)
        emitted.extend(store.drain_pending_events())

    switched_events = [event for event in emitted if isinstance(event, PlayerSwitchedTeam)]
    assert len(switched_events) == 1

    event = switched_events[0]
    assert event.event_name == "player_switched_team"
    assert event.player.name == "PamanPanda"
    assert event.old_team == 1
    assert event.new_team == 2
