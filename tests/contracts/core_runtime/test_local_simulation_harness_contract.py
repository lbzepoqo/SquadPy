"""Contract test for local simulation harness fixture replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from squadpy.simulation import LocalSimulationHarness

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]

FIXTURES = Path(__file__).parents[2] / "fixtures" / "simulation"


async def test_local_simulation_harness_contract_replays_logs_and_rcon() -> None:
    """P2-BEYOND-008: local replay supports plugin development loops."""
    harness = LocalSimulationHarness.from_fixture_files(
        log_fixture=FIXTURES / "logs" / "basic_replay.log",
        rcon_fixture=FIXTURES / "rcon" / "replay.json",
        plugins_dir=FIXTURES / "plugins",
        plugin_config_dir=FIXTURES / "config" / "plugins",
        plugin_names=["sim_demo_plugin"],
        run_periodic_once=True,
    )
    result = await harness.run()

    assert result.event_counts["player_connected"] == 1
    assert result.rcon_commands.count("ListPlayers") >= 2
    assert result.rcon_commands.count("ListSquads") >= 1
    assert result.runtime_errors == []
