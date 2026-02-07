"""Logging setup with Squad-style timestamped file rotation."""

import logging
from datetime import datetime
from pathlib import Path

from squadpy.config import LoggingConfig


class SquadPyTimedRotatingHandler(logging.FileHandler):
    """File handler that rotates logs with timestamped backup names.

    Current log: SquadPy.log
    Backups: SquadPy_2026_02_08_12_30_00.log
    """

    def __init__(self, filename: Path, max_files: int = 10):
        self.log_path = Path(filename)
        self.max_files = max_files
        super().__init__(filename, mode="a", encoding="utf-8")

    def doRollover(self):
        self.close()
        if self.log_path.exists():
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            stem = self.log_path.stem
            backup = self.log_path.parent / f"{stem}_{timestamp}.log"
            self.log_path.rename(backup)
        self._delete_old_backups()
        self.stream = self._open()

    def _delete_old_backups(self):
        pattern = f"{self.log_path.stem}_*.log"
        backups = sorted(
            self.log_path.parent.glob(pattern),
            key=lambda p: p.stat().st_mtime,
        )
        while len(backups) > self.max_files:
            backups.pop(0).unlink()

    def shouldRollover(self, record: logging.LogRecord) -> int:
        if not self.log_path.exists():
            return 0
        # Rollover if file exceeds 10 MB
        if self.log_path.stat().st_size > 10 * 1024 * 1024:
            return 1
        return 0


def setup_logging(config: LoggingConfig, log_dir: Path | None) -> logging.Logger:
    """Configure logging from a LoggingConfig."""
    logger = logging.getLogger("squadpy")
    logger.setLevel(getattr(logging, config.level))
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, config.console.level))
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler
    if config.file.enabled and log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "SquadPy.log"
        file_handler = SquadPyTimedRotatingHandler(log_file, max_files=config.file.max_files)
        file_handler.setLevel(getattr(logging, config.file.level))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
