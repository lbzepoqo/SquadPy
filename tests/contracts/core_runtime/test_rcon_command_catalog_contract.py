"""Ensure request fixtures map to real commands from ListCommands output."""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p0]

RCON_FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "rcon"
COMMAND_CATALOG_PATH = RCON_FIXTURE_ROOT / "commands" / "commands_with_details.txt"
REQUEST_FIXTURES_DIR = RCON_FIXTURE_ROOT / "requests"


def _extract_command_name(line: str) -> str:
    return line.split(maxsplit=1)[0]


def test_request_fixtures_use_known_rcon_commands() -> None:
    """Every request fixture should start with a command listed by ListCommands."""
    assert COMMAND_CATALOG_PATH.exists(), (
        "Missing command catalog fixture: run ListCommands 1 and save output to "
        f"{COMMAND_CATALOG_PATH}"
    )

    catalog_commands: set[str] = set()
    for line in COMMAND_CATALOG_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        catalog_commands.add(_extract_command_name(stripped))

    assert catalog_commands

    for fixture_path in sorted(REQUEST_FIXTURES_DIR.glob("*.txt")):
        template = fixture_path.read_text(encoding="utf-8").strip()
        assert template, f"Empty request fixture: {fixture_path}"
        command_name = _extract_command_name(template)
        assert command_name in catalog_commands, (
            f"Unknown command '{command_name}' in {fixture_path}. "
            "Update fixture to match ListCommands output."
        )
