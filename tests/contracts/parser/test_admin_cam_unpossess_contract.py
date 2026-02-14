"""Contract tests for the P0 AdminCamUnpossess parser event."""

from pathlib import Path

import pytest

from squadpy.events.types import AdminCamUnpossess
from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

pytestmark = [pytest.mark.contract, pytest.mark.parser, pytest.mark.p0]

ADMIN_CAM_UNPOSSESS_FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "parser" / "admin_cam_unpossess_lines.txt"
)


def test_admin_cam_unpossess_contract_fixture_parses_expected_fields() -> None:
    """P0-EVT-005: parser fixture emits AdminCamUnpossess with open/close pairing context."""
    lines = ADMIN_CAM_UNPOSSESS_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
    store = EventStore()
    event = None
    for line in lines:
        parsed = match_line(line.strip(), store)
        if parsed is not None:
            event = parsed

    assert isinstance(event, AdminCamUnpossess)
    assert event.event_name == "admin_cam_unpossess"
    assert event.admin.name == "Callsign"
    assert event.admin.eos_id == "00025c44975740ca82effe91ef190757"
    assert event.admin.steam_id == "76561199267250463"
    assert event.target == "Admin Camera"
    assert event.context["pawn_classname"] == "BP_DeveloperAdminCam_C"
    assert event.context["open_chain_id"] == 529
    assert event.context["close_chain_id"] == 912
