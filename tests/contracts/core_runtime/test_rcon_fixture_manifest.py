"""Validate RCON parity fixture inventory."""

from pathlib import Path
import tomllib

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p0]

MANIFEST_PATH = Path(__file__).parents[1] / "fixtures" / "rcon" / "manifest.toml"

EXPECTED_PARITY_COMMAND_IDS = {
    "list_players",
    "list_squads",
    "broadcast",
    "warn",
    "kick",
    "show_current_map",
    "show_next_map",
    "ban",
    "switch_team",
    "force_team_change",
    "set_fog_of_war",
    "set_next_layer",
    "demote_commander",
    "set_team",
    "end_match",
}


def test_rcon_manifest_covers_expected_parity_commands() -> None:
    """RCON fixture inventory includes all parity command IDs."""
    assert MANIFEST_PATH.exists()

    manifest = tomllib.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    commands = manifest.get("commands", [])
    assert commands, "RCON fixture manifest must define command fixtures"

    command_ids = {item["id"] for item in commands}
    assert command_ids == EXPECTED_PARITY_COMMAND_IDS

    for item in commands:
        request_path = Path(item["request_fixture"])
        response_path = Path(item["response_fixture"])
        assert request_path.exists(), f"Missing request fixture: {request_path}"
        assert response_path.exists(), f"Missing response fixture: {response_path}"
