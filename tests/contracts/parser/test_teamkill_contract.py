"""Contract tests for the P0 Teamkill parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import Teamkill
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser, pytest.mark.p0]

TEAMKILL_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "teamkill_lines.txt"
)


def test_teamkill_contract_fixture_parses_expected_fields() -> None:
    """P0-EVT-007: parser fixture emits Teamkill with attacker/victim/weapon."""
    lines = TEAMKILL_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
    store = EventStore()
    emitted: list[object] = []
    for line in lines:
        parsed = match_line(line.strip(), store)
        if parsed is not None:
            emitted.append(parsed)
        emitted.extend(store.drain_pending_events())

    teamkills = [event for event in emitted if isinstance(event, Teamkill)]
    assert len(teamkills) == 1

    event = teamkills[0]
    assert event.event_name == "teamkill"
    assert event.attacker.eos_id == "00024bce20aa414282702cf909896053"
    assert event.attacker.steam_id == "76561198191272778"
    assert event.attacker.name == "Blackburn"
    assert event.victim.eos_id == "000202cd1a3a4c739203a874221393d0"
    assert event.victim.steam_id == "76561198161847878"
    assert event.victim.name == "PamanPanda"
    assert event.weapon == "BP_M134_Loach_Dual_C"
