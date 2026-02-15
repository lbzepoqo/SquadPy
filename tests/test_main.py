"""Tests for SquadPy entrypoint runtime mode selection."""

from pathlib import Path

import pytest

import squadpy.__main__ as entrypoint


class TestResolveRuntimeMode:
    def test_defaults_to_auto_when_no_overrides(self, tmp_path: Path) -> None:
        mode = entrypoint._resolve_runtime_mode(
            cli_mode=None,
            config_dir=tmp_path / "config",
            environ={},
        )
        assert mode == "auto"

    def test_reads_runtime_toml_mode(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "runtime.toml").write_text('mode = "single"\n', encoding="utf-8")

        mode = entrypoint._resolve_runtime_mode(
            cli_mode=None,
            config_dir=config_dir,
            environ={},
        )
        assert mode == "single"

    def test_env_overrides_runtime_toml(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "runtime.toml").write_text('mode = "single"\n', encoding="utf-8")

        mode = entrypoint._resolve_runtime_mode(
            cli_mode=None,
            config_dir=config_dir,
            environ={"SQUADPY_RUNTIME_MODE": "multi"},
        )
        assert mode == "multi"

    def test_cli_overrides_env_and_file(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "runtime.toml").write_text('mode = "single"\n', encoding="utf-8")

        mode = entrypoint._resolve_runtime_mode(
            cli_mode="auto",
            config_dir=config_dir,
            environ={"SQUADPY_RUNTIME_MODE": "multi"},
        )
        assert mode == "auto"


class TestMainModeRouting:
    def test_single_mode_bypasses_multi_discovery(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(entrypoint.Path, "cwd", lambda: tmp_path)

        called = {"single": False}

        def _single(_base_dir: Path, _config_dir: Path) -> None:
            called["single"] = True

        def _discover(_base_dir: Path) -> list[object]:
            raise AssertionError("discover should not be called in single mode")

        monkeypatch.setattr(entrypoint, "_run_single_server", _single)
        monkeypatch.setattr(entrypoint, "discover_server_runtime_definitions", _discover)

        entrypoint.main(["--mode", "single"])
        assert called["single"] is True

    def test_auto_mode_uses_multi_when_definitions_present(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(entrypoint.Path, "cwd", lambda: tmp_path)
        definitions = [object()]

        called = {"multi": False}

        def _multi(resolved: list[object]) -> None:
            called["multi"] = True
            assert resolved == definitions

        def _single(_base_dir: Path, _config_dir: Path) -> None:
            raise AssertionError("single mode should not be used when definitions exist")

        monkeypatch.setattr(
            entrypoint,
            "discover_server_runtime_definitions",
            lambda _base_dir: definitions,
        )
        monkeypatch.setattr(entrypoint, "_run_multi_server", _multi)
        monkeypatch.setattr(entrypoint, "_run_single_server", _single)

        entrypoint.main([])
        assert called["multi"] is True

    def test_auto_mode_falls_back_to_single_when_no_definitions(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(entrypoint.Path, "cwd", lambda: tmp_path)
        called = {"single": False}

        monkeypatch.setattr(entrypoint, "discover_server_runtime_definitions", lambda _base_dir: [])
        monkeypatch.setattr(entrypoint, "_run_multi_server", lambda _definitions: None)
        monkeypatch.setattr(
            entrypoint,
            "_run_single_server",
            lambda _base_dir, _config_dir: called.__setitem__("single", True),
        )

        entrypoint.main([])
        assert called["single"] is True

    def test_multi_mode_requires_definitions(self, monkeypatch, tmp_path: Path, capsys) -> None:
        monkeypatch.setattr(entrypoint.Path, "cwd", lambda: tmp_path)
        monkeypatch.setattr(entrypoint, "discover_server_runtime_definitions", lambda _base_dir: [])
        monkeypatch.setattr(entrypoint, "_run_multi_server", lambda _definitions: None)
        monkeypatch.setattr(entrypoint, "_run_single_server", lambda _base_dir, _config_dir: None)

        with pytest.raises(SystemExit, match="1"):
            entrypoint.main(["--mode", "multi"])

        stderr = capsys.readouterr().err
        assert "Runtime mode is 'multi' but no server definitions were found" in stderr
