"""Contract tests for plugin scaffolder CLI output shape."""

from __future__ import annotations

from pathlib import Path

import pytest

from squadpy.plugin_scaffolder import scaffold_plugin

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime]


def test_plugin_scaffolder_contract_generates_typed_skeleton(tmp_path: Path) -> None:
    """P2-BEYOND-007: scaffolder emits typed plugin hooks and starter tests."""
    result = scaffold_plugin("contract_demo", base_dir=tmp_path)

    plugin_path = tmp_path / "plugins" / "contract_demo" / "plugin.py"
    test_path = tmp_path / "tests" / "test_plugin_contract_demo.py"
    config_path = tmp_path / "config" / "plugins" / "contract_demo.toml.example"

    assert plugin_path in result.writes
    assert test_path in result.writes
    assert config_path in result.writes

    plugin_content = plugin_path.read_text(encoding="utf-8")
    assert "event: PlayerConnected" in plugin_content
    assert "event: ChatMessage" in plugin_content
    assert "async def periodic_healthcheck(self) -> None:" in plugin_content

    test_content = test_path.read_text(encoding="utf-8")
    assert "test_plugin_hooks_are_registered_and_typed" in test_content
