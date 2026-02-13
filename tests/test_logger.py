"""Tests for logging setup with file rotation."""

import logging
from pathlib import Path

import pytest

from squadpy.config import LoggingConfig
from squadpy.logger import setup_logging, SquadPyTimedRotatingHandler


class TestSetupLogging:
    def test_returns_root_logger(self):
        config = LoggingConfig(level="INFO")
        logger = setup_logging(config, log_dir=None)
        assert isinstance(logger, logging.Logger)
        assert logger.name == "squadpy"

    def test_console_handler_added(self):
        config = LoggingConfig(level="INFO")
        logger = setup_logging(config, log_dir=None)
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types

    def test_file_handler_added_when_enabled(self, tmp_path):
        config = LoggingConfig.model_validate({
            "level": "DEBUG",
            "file": {"enabled": True, "path": str(tmp_path)},
        })
        logger = setup_logging(config, log_dir=tmp_path)
        handler_types = [type(h) for h in logger.handlers]
        assert SquadPyTimedRotatingHandler in handler_types

    def test_no_file_handler_when_disabled(self):
        config = LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}})
        logger = setup_logging(config, log_dir=None)
        handler_types = [type(h) for h in logger.handlers]
        assert SquadPyTimedRotatingHandler not in handler_types

    def test_logger_level_set(self):
        config = LoggingConfig(level="DEBUG")
        logger = setup_logging(config, log_dir=None)
        assert logger.level == logging.DEBUG


class TestTimedRotatingHandler:
    def test_current_log_name(self, tmp_path):
        log_file = tmp_path / "SquadPy.log"
        handler = SquadPyTimedRotatingHandler(log_file, max_files=10)
        assert handler.baseFilename == str(log_file)

    def test_rotation_creates_timestamped_backup(self, tmp_path):
        log_file = tmp_path / "SquadPy.log"
        handler = SquadPyTimedRotatingHandler(log_file, max_files=3)
        # Write some content so the file exists
        log_file.write_text("test log line\n")
        handler.doRollover()
        # A backup file should exist with timestamp pattern
        backups = list(tmp_path.glob("SquadPy_*.log"))
        assert len(backups) == 1

    def test_max_files_enforced(self, tmp_path):
        log_file = tmp_path / "SquadPy.log"
        handler = SquadPyTimedRotatingHandler(log_file, max_files=2)
        for _ in range(4):
            log_file.write_text("test log line\n")
            handler.doRollover()
        backups = list(tmp_path.glob("SquadPy_*.log"))
        assert len(backups) <= 2
