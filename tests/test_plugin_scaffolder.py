"""Unit tests for plugin scaffolder CLI and helper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from squadpy.plugin_scaffolder import (
    normalize_plugin_slug,
    plugin_class_name,
    scaffold_plugin,
)

REPO_ROOT = Path(__file__).parent.parent


def test_normalize_plugin_slug_and_class_name() -> None:
    slug = normalize_plugin_slug("My Cool-Plugin")
    assert slug == "my_cool_plugin"
    assert plugin_class_name(slug) == "MyCoolPlugin"


def test_scaffold_plugin_writes_typed_plugin_test_and_config(tmp_path: Path) -> None:
    result = scaffold_plugin("my_cool_plugin", base_dir=tmp_path)

    plugin_path = tmp_path / "plugins" / "my_cool_plugin" / "plugin.py"
    test_path = tmp_path / "tests" / "test_plugin_my_cool_plugin.py"
    config_path = tmp_path / "config" / "plugins" / "my_cool_plugin.toml.example"
    assert result.writes == [plugin_path, test_path, config_path]

    plugin_content = plugin_path.read_text(encoding="utf-8")
    assert "from squadpy.events.types import ChatMessage, PlayerConnected" in plugin_content
    assert "async def handle_player_connected(self, event: PlayerConnected) -> None:" in plugin_content
    assert "async def handle_chat_message(self, event: ChatMessage) -> None:" in plugin_content
    assert "@periodic(seconds=60)" in plugin_content

    test_content = test_path.read_text(encoding="utf-8")
    assert "test_plugin_hooks_are_registered_and_typed" in test_content
    assert "handle_player_connected.__annotations__" in test_content
    assert "handle_chat_message.__annotations__" in test_content

    config_content = config_path.read_text(encoding="utf-8")
    assert "enabled = true" in config_content
    assert "[settings]" in config_content


def test_scaffold_plugin_rejects_existing_files_without_force(tmp_path: Path) -> None:
    scaffold_plugin("duplicate_plugin", base_dir=tmp_path)
    with pytest.raises(FileExistsError, match="Refusing to overwrite existing files"):
        scaffold_plugin("duplicate_plugin", base_dir=tmp_path)


def test_scaffold_plugin_cli_creates_skeleton(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "scaffold_plugin.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "typed_demo",
            "--display-name",
            "Typed Demo",
            "--base-dir",
            str(tmp_path),
        ],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    report = json.loads(result.stdout)
    assert report["plugin_slug"] == "typed_demo"
    assert report["display_name"] == "Typed Demo"

    plugin_path = tmp_path / "plugins" / "typed_demo" / "plugin.py"
    assert plugin_path.exists()
    assert "class TypedDemoPlugin(Plugin):" in plugin_path.read_text(encoding="utf-8")
