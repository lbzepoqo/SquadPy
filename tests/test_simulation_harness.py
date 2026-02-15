"""Unit tests for local simulation harness replay."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from squadpy.simulation import LocalSimulationHarness, load_rcon_fixture

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "simulation"
LOG_FIXTURE = FIXTURES / "logs" / "basic_replay.log"
RCON_FIXTURE = FIXTURES / "rcon" / "replay.json"
PLUGINS_DIR = FIXTURES / "plugins"
PLUGIN_CONFIG_DIR = FIXTURES / "config" / "plugins"


def test_load_rcon_fixture_from_response_files() -> None:
    responses = load_rcon_fixture(RCON_FIXTURE)
    assert "ListPlayers" in responses
    assert "ListSquads" in responses
    assert "SimPlayer" in responses["ListPlayers"][0]


async def test_local_simulation_replays_logs_and_rcon_for_plugin_loop() -> None:
    harness = LocalSimulationHarness.from_fixture_files(
        log_fixture=LOG_FIXTURE,
        rcon_fixture=RCON_FIXTURE,
        plugins_dir=PLUGINS_DIR,
        plugin_config_dir=PLUGIN_CONFIG_DIR,
        plugin_names=["sim_demo_plugin"],
        run_periodic_once=True,
    )
    result = await harness.run()

    assert result.event_counts["player_connected"] == 1
    assert "join_succeeded" in result.event_counts
    assert result.rcon_commands.count("ListPlayers") >= 2
    assert result.rcon_commands.count("ListSquads") >= 1
    assert result.runtime_errors == []
    assert result.plugins[0]["dir_name"] == "sim_demo_plugin"
    assert result.plugins[0]["status"] == "enabled"


def test_simulate_local_replay_cli_outputs_summary(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "simulate_local_replay.py"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            str(LOG_FIXTURE),
            "--rcon-fixture",
            str(RCON_FIXTURE),
            "--plugins-dir",
            str(PLUGINS_DIR),
            "--plugin-config-dir",
            str(PLUGIN_CONFIG_DIR),
            "--plugin",
            "sim_demo_plugin",
            "--output",
            str(tmp_path / "result.json"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["event_counts"]["player_connected"] == 1
    assert payload["plugins"][0]["dir_name"] == "sim_demo_plugin"
    assert (tmp_path / "result.json").exists()
