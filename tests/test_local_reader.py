"""Tests for the local file log reader."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.log_parser.local import LocalLogReader


class TestLocalLogReader:
    @pytest.fixture
    def log_file(self, tmp_path) -> Path:
        path = tmp_path / "SquadGame.log"
        path.write_text("existing line 1\nexisting line 2\n")
        return path

    async def test_seeks_to_end_on_start(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.05)
        await reader.start()
        lines = []
        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 1:
                    break
        # Write a new line after start
        with open(log_file, "a") as f:
            f.write("new line\n")
        await asyncio.wait_for(collect(), timeout=1.0)
        assert lines == ["new line"]
        await reader.stop()

    async def test_tails_multiple_lines(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.05)
        await reader.start()
        lines = []
        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 3:
                    break
        with open(log_file, "a") as f:
            f.write("line A\nline B\nline C\n")
        await asyncio.wait_for(collect(), timeout=1.0)
        assert lines == ["line A", "line B", "line C"]
        await reader.stop()

    async def test_reopens_on_rotation(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.01)
        await reader.start()

        lines = []

        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.03)

        with open(log_file, "a") as f:
            f.write("line before rotate\n")

        await asyncio.sleep(0.03)
        rotated_path = log_file.with_name(f"{log_file.name}.1")
        log_file.rename(rotated_path)
        log_file.write_text("line after rotate\n")

        await asyncio.wait_for(task, timeout=1.0)
        assert lines == ["line before rotate", "line after rotate"]
        await reader.stop()

    async def test_handles_copytruncate(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.01)
        await reader.start()

        lines = []

        async def collect():
            async for line in reader.tail():
                lines.append(line)
                if len(lines) >= 2:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.03)

        with open(log_file, "a") as f:
            f.write("line before truncate\n")

        await asyncio.sleep(0.03)
        with open(log_file, "w") as f:
            f.write("line after truncate\n")

        await asyncio.wait_for(task, timeout=1.0)
        assert lines == ["line before truncate", "line after truncate"]
        await reader.stop()

    async def test_handles_missing_file(self, tmp_path):
        reader = LocalLogReader(str(tmp_path / "nonexistent.log"), poll_interval=0.05)
        with pytest.raises(FileNotFoundError):
            await reader.start()

    async def test_stop_ends_iteration(self, log_file):
        reader = LocalLogReader(str(log_file), poll_interval=0.05)
        await reader.start()
        async def collect():
            async for _ in reader.tail():
                pass
        # Stop should cause tail() to end
        await reader.stop()
        await asyncio.wait_for(collect(), timeout=1.0)

    async def test_wait_for_update_uses_polling_fallback_without_watcher(self, tmp_path, monkeypatch):
        reader = LocalLogReader(str(tmp_path / "SquadGame.log"), poll_interval=0.2)
        sleep_mock = AsyncMock()
        monkeypatch.setattr("squadpy.log_parser.local.asyncio.sleep", sleep_mock)

        await reader._wait_for_update()

        sleep_mock.assert_awaited_once_with(0.2)

    async def test_wait_for_update_uses_watcher_when_available(self, tmp_path, monkeypatch):
        reader = LocalLogReader(str(tmp_path / "SquadGame.log"), poll_interval=0.2)
        emitted = False

        async def watcher_events():
            nonlocal emitted
            emitted = True
            yield {(1, "changed")}

        reader._watch_events = watcher_events()
        sleep_mock = AsyncMock()
        monkeypatch.setattr("squadpy.log_parser.local.asyncio.sleep", sleep_mock)

        await reader._wait_for_update()

        assert emitted is True
        sleep_mock.assert_not_awaited()

    async def test_wait_for_update_falls_back_after_watcher_error(self, tmp_path, monkeypatch):
        reader = LocalLogReader(str(tmp_path / "SquadGame.log"), poll_interval=0.2)

        async def broken_watcher():
            raise RuntimeError("watch failed")
            yield set()

        reader._watch_events = broken_watcher()
        sleep_mock = AsyncMock()
        monkeypatch.setattr("squadpy.log_parser.local.asyncio.sleep", sleep_mock)

        await reader._wait_for_update()

        assert reader._watch_events is None
        sleep_mock.assert_awaited_once_with(0.2)
