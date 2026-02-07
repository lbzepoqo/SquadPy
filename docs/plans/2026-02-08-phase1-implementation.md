# Phase 1: Core Foundation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a runnable SquadPy that connects to RCON, loads plugins with error isolation, and displays a startup summary.

**Architecture:** Async-first Python framework using asyncio. RCON client handles Squad's non-standard UE4 RCON protocol (oversized packets, chat type 0x01, follow-response quirks). Event bus dispatches typed events to decorator-registered plugin handlers. TOML configs with Pydantic validation. Clean startup/shutdown lifecycle.

**Tech Stack:** Python 3.12+, asyncio, Pydantic, pytest + pytest-asyncio, stdlib logging + tomllib

**Reference:** `docs/plans/2026-02-08-squadpy-design.md` for full architecture context.

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `squadpy/__init__.py`
- Create: `squadpy/__main__.py` (placeholder)
- Create: `squadpy/rcon/__init__.py`
- Create: `squadpy/events/__init__.py`
- Create: `squadpy/log_parser/__init__.py`
- Create: `squadpy/discord/__init__.py`
- Create: `squadpy/database/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `config/server.toml`
- Create: `config/logging.toml`
- Create: `config/database.toml`
- Create: `config/plugins/.gitkeep`
- Create: `plugins/.gitkeep`
- Create: `data/.gitkeep`
- Create: `logs/.gitkeep`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "squadpy"
version = "0.1.0"
description = "Python-based Squad game server management framework"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create requirements.txt**

```
pydantic>=2.0
```

**Step 3: Create directory structure and placeholder files**

Create all `__init__.py` files (empty). Create `squadpy/__main__.py` with:

```python
"""SquadPy entry point: python -m squadpy"""


def main():
    print("SquadPy v0.1.0")


if __name__ == "__main__":
    main()
```

**Step 4: Create default config files**

`config/server.toml`:
```toml
[rcon]
host = "127.0.0.1"
port = 21114
password = ""
```

`config/logging.toml`:
```toml
level = "INFO"

[console]
level = "INFO"

[file]
enabled = true
level = "DEBUG"
path = "logs"
max_files = 10
```

`config/database.toml`:
```toml
enabled = false
driver = "sqlite"
path = "data/squadpy.db"
```

**Step 5: Create tests/conftest.py**

```python
"""Shared test fixtures for SquadPy."""
```

**Step 6: Install project and verify**

Run: `pip install -e ".[dev]"` then `python -m squadpy`
Expected: Prints "SquadPy v0.1.0"

Run: `pytest --co`
Expected: "no tests ran" (no tests yet, but pytest finds the test directory)

**Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold project structure, configs, and dev tooling"
```

---

## Task 2: Config Loader

**Files:**
- Create: `squadpy/config.py`
- Create: `tests/test_config.py`

**Step 1: Write failing tests for config loading**

`tests/test_config.py`:
```python
"""Tests for TOML config loading and validation."""

import pytest
from pathlib import Path
from squadpy.config import ServerConfig, LoggingConfig, load_config


class TestServerConfig:
    def test_valid_config(self):
        config = ServerConfig(
            rcon={"host": "192.168.1.10", "port": 21114, "password": "secret"}
        )
        assert config.rcon.host == "192.168.1.10"
        assert config.rcon.port == 21114
        assert config.rcon.password == "secret"

    def test_default_port(self):
        config = ServerConfig(rcon={"host": "127.0.0.1", "password": "pass"})
        assert config.rcon.port == 21114

    def test_missing_host_raises(self):
        with pytest.raises(Exception):
            ServerConfig(rcon={"password": "pass"})

    def test_missing_password_raises(self):
        with pytest.raises(Exception):
            ServerConfig(rcon={"host": "127.0.0.1"})

    def test_invalid_port_raises(self):
        with pytest.raises(Exception):
            ServerConfig(rcon={"host": "127.0.0.1", "port": 99999, "password": "p"})


class TestLoggingConfig:
    def test_valid_config(self):
        config = LoggingConfig(level="INFO")
        assert config.level == "INFO"
        assert config.console.level == "INFO"
        assert config.file.enabled is True
        assert config.file.max_files == 10

    def test_invalid_level_raises(self):
        with pytest.raises(Exception):
            LoggingConfig(level="INVALID")


class TestLoadConfig:
    def test_load_from_toml_file(self, tmp_path):
        toml_file = tmp_path / "server.toml"
        toml_file.write_text(
            '[rcon]\nhost = "10.0.0.1"\nport = 21114\npassword = "test"\n'
        )
        config = load_config(ServerConfig, toml_file)
        assert config.rcon.host == "10.0.0.1"

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(ServerConfig, tmp_path / "nonexistent.toml")

    def test_load_invalid_toml_raises(self, tmp_path):
        toml_file = tmp_path / "bad.toml"
        toml_file.write_text("this is not valid toml [[[")
        with pytest.raises(Exception):
            load_config(ServerConfig, toml_file)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (module not found)

**Step 3: Implement config module**

`squadpy/config.py`:
```python
"""TOML config loading with Pydantic validation."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator


class RconConfig(BaseModel):
    host: str
    port: int = 21114
    password: str

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"Port must be 1-65535, got {v}")
        return v


class ConsoleLogConfig(BaseModel):
    level: str = "INFO"

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()


class FileLogConfig(BaseModel):
    enabled: bool = True
    level: str = "DEBUG"
    path: str = "logs"
    max_files: int = 10

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()


class ServerConfig(BaseModel):
    rcon: RconConfig


class LoggingConfig(BaseModel):
    level: str = "INFO"
    console: ConsoleLogConfig = ConsoleLogConfig()
    file: FileLogConfig = FileLogConfig()

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()


class DatabaseConfig(BaseModel):
    enabled: bool = False
    driver: Literal["sqlite", "mysql", "postgresql"] = "sqlite"
    path: str = "data/squadpy.db"
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    database: str = ""


def load_config[T: BaseModel](model: type[T], path: Path) -> T:
    """Load a TOML file and validate it against a Pydantic model."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return model.model_validate(data)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add squadpy/config.py tests/test_config.py
git commit -m "feat: add TOML config loader with Pydantic validation"
```

---

## Task 3: Logging Setup

**Files:**
- Create: `squadpy/logger.py`
- Create: `tests/test_logger.py`

**Step 1: Write failing tests**

`tests/test_logger.py`:
```python
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
        config = LoggingConfig(level="DEBUG", file={"enabled": True, "path": str(tmp_path)})
        logger = setup_logging(config, log_dir=tmp_path)
        handler_types = [type(h) for h in logger.handlers]
        assert SquadPyTimedRotatingHandler in handler_types

    def test_no_file_handler_when_disabled(self):
        config = LoggingConfig(level="INFO", file={"enabled": False})
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
        # The original file should be recreated (empty or new)
        # and a backup file should exist with timestamp pattern
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_logger.py -v`
Expected: FAIL (module not found)

**Step 3: Implement logging module**

`squadpy/logger.py`:
```python
"""Logging setup with Squad-style timestamped file rotation."""

import logging
import os
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_logger.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add squadpy/logger.py tests/test_logger.py
git commit -m "feat: add logging with Squad-style timestamped file rotation"
```

---

## Task 4: Event Bus

**Files:**
- Create: `squadpy/events/emitter.py`
- Create: `squadpy/events/types.py`
- Create: `tests/test_events.py`

**Step 1: Write failing tests**

`tests/test_events.py`:
```python
"""Tests for the async event bus."""

import asyncio
from dataclasses import dataclass

import pytest

from squadpy.events.emitter import EventBus
from squadpy.events.types import BaseEvent


@dataclass
class FakeEvent(BaseEvent):
    event_name: str = "fake_event"
    value: str = ""


class TestEventBus:
    @pytest.fixture
    def bus(self):
        return EventBus()

    async def test_subscribe_and_emit(self, bus):
        received = []

        async def handler(event: FakeEvent):
            received.append(event)

        bus.subscribe("fake_event", handler)
        event = FakeEvent(value="hello")
        await bus.emit(event)
        assert len(received) == 1
        assert received[0].value == "hello"

    async def test_multiple_subscribers(self, bus):
        received_a = []
        received_b = []

        async def handler_a(event):
            received_a.append(event)

        async def handler_b(event):
            received_b.append(event)

        bus.subscribe("fake_event", handler_a)
        bus.subscribe("fake_event", handler_b)
        await bus.emit(FakeEvent(value="test"))
        assert len(received_a) == 1
        assert len(received_b) == 1

    async def test_unsubscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("fake_event", handler)
        bus.unsubscribe("fake_event", handler)
        await bus.emit(FakeEvent(value="ignored"))
        assert len(received) == 0

    async def test_emit_unknown_event_does_nothing(self, bus):
        await bus.emit(FakeEvent(value="nobody listening"))
        # No error raised

    async def test_handler_error_does_not_break_others(self, bus):
        received = []

        async def bad_handler(event):
            raise ValueError("boom")

        async def good_handler(event):
            received.append(event)

        bus.subscribe("fake_event", bad_handler)
        bus.subscribe("fake_event", good_handler)
        await bus.emit(FakeEvent(value="still works"))
        assert len(received) == 1

    async def test_handler_error_is_logged(self, bus, caplog):
        async def bad_handler(event):
            raise ValueError("test error")

        bus.subscribe("fake_event", bad_handler)
        with caplog.at_level("ERROR", logger="squadpy.events"):
            await bus.emit(FakeEvent(value="trigger"))
        assert "test error" in caplog.text
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_events.py -v`
Expected: FAIL

**Step 3: Implement event types**

`squadpy/events/types.py`:
```python
"""Base event type and core event definitions."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BaseEvent:
    """Base class for all SquadPy events."""
    event_name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
```

**Step 4: Implement event bus**

`squadpy/events/emitter.py`:
```python
"""Async event bus for dispatching events to subscribers."""

import logging
from collections import defaultdict
from typing import Callable, Coroutine, Any

from squadpy.events.types import BaseEvent

logger = logging.getLogger("squadpy.events")

EventHandler = Callable[[BaseEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Async event bus that dispatches events to registered handlers."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: BaseEvent) -> None:
        handlers = self._handlers.get(event.event_name, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Error in handler %s for event %s",
                    handler.__qualname__,
                    event.event_name,
                )

    def clear(self) -> None:
        self._handlers.clear()
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_events.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add squadpy/events/ tests/test_events.py
git commit -m "feat: add async event bus with error-isolated dispatch"
```

---

## Task 5: RCON Protocol (Packet Encoding/Decoding)

**Files:**
- Create: `squadpy/rcon/protocol.py`
- Create: `tests/test_rcon_protocol.py`

Squad's RCON is UE4-based, not Valve Source RCON. Key differences from standard:
- Packet type `0x01` (`CHAT_VALUE`) for unsolicited server messages (chat, admin cam, etc.)
- Follow-response: 7-byte sequence `\x00\x01\x00\x00\x00\x00\x00` after multi-packet end markers
- The size field in follow-response packets lies (says 10, actual is 21 bytes)

**Step 1: Write failing tests**

`tests/test_rcon_protocol.py`:
```python
"""Tests for RCON packet encoding and decoding."""

import pytest

from squadpy.rcon.protocol import (
    RconPacket,
    PacketType,
    encode_packet,
    decode_packet,
    FOLLOW_RESPONSE_BODY,
)


class TestPacketType:
    def test_auth_type(self):
        assert PacketType.AUTH == 3

    def test_auth_response_type(self):
        assert PacketType.AUTH_RESPONSE == 2

    def test_exec_command_type(self):
        assert PacketType.EXEC_COMMAND == 2

    def test_response_value_type(self):
        assert PacketType.RESPONSE_VALUE == 0

    def test_chat_value_type(self):
        assert PacketType.CHAT_VALUE == 1


class TestEncodePacket:
    def test_encode_auth_packet(self):
        data = encode_packet(PacketType.AUTH, 1, "password123")
        # size (4) + id (4) + type (4) + body + null (1) + null (1)
        body = b"password123"
        expected_size = 4 + 4 + len(body) + 1 + 1  # 21
        assert len(data) == expected_size + 4  # +4 for size field itself
        # Size field (little-endian)
        size = int.from_bytes(data[0:4], "little")
        assert size == expected_size
        # ID field
        pkt_id = int.from_bytes(data[4:8], "little")
        assert pkt_id == 1
        # Type field
        pkt_type = int.from_bytes(data[8:12], "little")
        assert pkt_type == PacketType.AUTH
        # Body
        assert data[12:12 + len(body)] == body
        # Null terminators
        assert data[-2:] == b"\x00\x00"

    def test_encode_empty_body(self):
        data = encode_packet(PacketType.EXEC_COMMAND, 5, "")
        size = int.from_bytes(data[0:4], "little")
        assert size == 10  # minimum: 4 + 4 + 1 + 1

    def test_encode_exec_command(self):
        data = encode_packet(PacketType.EXEC_COMMAND, 42, "ListPlayers")
        pkt_type = int.from_bytes(data[8:12], "little")
        assert pkt_type == PacketType.EXEC_COMMAND
        body_end = data.index(b"\x00", 12)
        assert data[12:body_end] == b"ListPlayers"


class TestDecodePacket:
    def test_decode_response_packet(self):
        raw = encode_packet(PacketType.RESPONSE_VALUE, 7, "OK")
        packet, consumed = decode_packet(raw)
        assert packet.id == 7
        assert packet.type == PacketType.RESPONSE_VALUE
        assert packet.body == "OK"
        assert consumed == len(raw)

    def test_decode_auth_response_success(self):
        raw = encode_packet(PacketType.AUTH_RESPONSE, 1, "")
        packet, consumed = decode_packet(raw)
        assert packet.id == 1
        assert packet.type == PacketType.AUTH_RESPONSE

    def test_decode_auth_response_failure(self):
        raw = encode_packet(PacketType.AUTH_RESPONSE, -1, "")
        packet, consumed = decode_packet(raw)
        assert packet.id == -1

    def test_decode_chat_packet(self):
        raw = encode_packet(PacketType.CHAT_VALUE, 0, "Player said hello")
        packet, consumed = decode_packet(raw)
        assert packet.type == PacketType.CHAT_VALUE
        assert packet.body == "Player said hello"

    def test_decode_incomplete_data_returns_none(self):
        raw = encode_packet(PacketType.RESPONSE_VALUE, 1, "test")
        result = decode_packet(raw[:5])  # truncated
        assert result is None

    def test_decode_only_size_field_returns_none(self):
        result = decode_packet(b"\x0a\x00\x00\x00")
        assert result is None

    def test_decode_empty_data_returns_none(self):
        result = decode_packet(b"")
        assert result is None

    def test_decode_follow_response(self):
        """UE4 RCON sends a 7-byte follow-response after multi-packet end markers.
        The size field lies (says 10, actual data is 21 bytes)."""
        # Build: normal empty packet (14 bytes) + 7-byte follow-response body
        empty_pkt = encode_packet(PacketType.RESPONSE_VALUE, 1, "")
        follow = empty_pkt + FOLLOW_RESPONSE_BODY
        packet, consumed = decode_packet(follow)
        assert packet.body == ""
        assert packet.is_follow_response is True
        assert consumed == len(follow)

    def test_decode_multiple_packets_in_buffer(self):
        pkt1 = encode_packet(PacketType.RESPONSE_VALUE, 1, "first")
        pkt2 = encode_packet(PacketType.RESPONSE_VALUE, 2, "second")
        buf = pkt1 + pkt2
        packet1, consumed1 = decode_packet(buf)
        assert packet1.body == "first"
        packet2, consumed2 = decode_packet(buf[consumed1:])
        assert packet2.body == "second"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rcon_protocol.py -v`
Expected: FAIL

**Step 3: Implement protocol module**

`squadpy/rcon/protocol.py`:
```python
"""RCON packet encoding/decoding for Squad's UE4 RCON protocol.

Squad uses UE4's RCON module, not Valve's Source RCON. It is based on
the Valve protocol but has important deviations:
- Packet type 0x01 (CHAT_VALUE) for unsolicited server messages
- 7-byte follow-response after multi-packet end markers
- Size field in follow-response packets is unreliable
"""

import struct
from dataclasses import dataclass, field
from enum import IntEnum

# UE4 RCON appends this after the empty end-of-multi-packet marker
FOLLOW_RESPONSE_BODY = b"\x00\x01\x00\x00\x00\x00\x00"

# Minimum packet: 4 (size) + 4 (id) + 4 (type) + 1 (body null) + 1 (terminator)
MIN_PACKET_SIZE = 14

# Header: size (4) + id (4) + type (4)
HEADER_SIZE = 12


class PacketType(IntEnum):
    RESPONSE_VALUE = 0
    CHAT_VALUE = 1         # Squad-specific: unsolicited server messages
    EXEC_COMMAND = 2
    AUTH_RESPONSE = 2      # Same value as EXEC_COMMAND, distinguished by context
    AUTH = 3


@dataclass
class RconPacket:
    id: int
    type: int
    body: str
    is_follow_response: bool = False


def encode_packet(packet_type: PacketType, packet_id: int, body: str) -> bytes:
    """Encode an RCON packet to bytes."""
    body_bytes = body.encode("utf-8")
    # size = id (4) + type (4) + body + null (1) + null (1)
    size = 4 + 4 + len(body_bytes) + 1 + 1
    return struct.pack(f"<iii{len(body_bytes)}scc",
                       size,
                       packet_id,
                       int(packet_type),
                       body_bytes,
                       b"\x00",
                       b"\x00")


def decode_packet(data: bytes) -> tuple[RconPacket, int] | None:
    """Decode one RCON packet from a byte buffer.

    Returns (packet, bytes_consumed) or None if the buffer doesn't
    contain a complete packet yet.
    """
    if len(data) < 4:
        return None

    size = struct.unpack_from("<i", data, 0)[0]
    total_length = size + 4  # size field itself is not included in size

    if len(data) < total_length:
        return None

    packet_id = struct.unpack_from("<i", data, 4)[0]
    packet_type = struct.unpack_from("<i", data, 8)[0]

    # Body is between header and the two null terminators
    body_length = size - 4 - 4 - 2  # minus id, type, two nulls
    body_bytes = data[HEADER_SIZE:HEADER_SIZE + body_length]
    body = body_bytes.decode("utf-8", errors="replace")

    # Check for UE4 follow-response: 7 extra bytes after an empty packet
    is_follow = False
    consumed = total_length
    if (body == "" and
            packet_type == PacketType.RESPONSE_VALUE and
            len(data) >= total_length + len(FOLLOW_RESPONSE_BODY)):
        trailing = data[total_length:total_length + len(FOLLOW_RESPONSE_BODY)]
        if trailing == FOLLOW_RESPONSE_BODY:
            is_follow = True
            consumed = total_length + len(FOLLOW_RESPONSE_BODY)

    return RconPacket(
        id=packet_id,
        type=packet_type,
        body=body,
        is_follow_response=is_follow,
    ), consumed
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rcon_protocol.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add squadpy/rcon/protocol.py tests/test_rcon_protocol.py
git commit -m "feat: add RCON packet encoding/decoding with UE4 quirk handling"
```

---

## Task 6: RCON Client

**Files:**
- Create: `squadpy/rcon/client.py`
- Create: `tests/test_rcon_client.py`

This is the largest task. The RCON client needs:
- Async TCP connection
- Auth handshake
- Multi-packet response reassembly (empty-packet trick)
- Auto-reconnect with exponential backoff
- Request queuing during reconnection
- Per-command timeout
- Chat packet callback (for unsolicited server messages)

**Step 1: Write failing tests**

`tests/test_rcon_client.py`:
```python
"""Tests for the async RCON client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.rcon.client import RconClient, RconError, RconAuthError
from squadpy.rcon.protocol import (
    PacketType,
    RconPacket,
    encode_packet,
)


class FakeTransport:
    """Mock asyncio transport for testing."""

    def __init__(self):
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: bytes):
        self.written.append(data)

    def close(self):
        self.closed = True

    def is_closing(self):
        return self.closed


class TestRconClient:
    @pytest.fixture
    def client(self):
        return RconClient(host="127.0.0.1", port=21114, password="test")

    async def test_initial_state(self, client):
        assert not client.connected

    async def test_execute_when_not_connected_raises(self, client):
        with pytest.raises(RconError, match="Not connected"):
            await client.execute("ListPlayers")

    async def test_packet_id_increments(self, client):
        id1 = client._next_packet_id()
        id2 = client._next_packet_id()
        assert id2 == id1 + 1

    async def test_packet_id_wraps(self, client):
        client._packet_id_counter = 2**31 - 1
        next_id = client._next_packet_id()
        assert next_id == 1


class TestRconProtocolHandler:
    """Test the protocol handling logic with simulated data."""

    @pytest.fixture
    def client(self):
        return RconClient(host="127.0.0.1", port=21114, password="test")

    async def test_single_packet_response(self, client):
        """Simulate receiving a single-packet response."""
        request_id = 1
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = []

        # Simulate receiving the response data
        response_body = "Player list here"
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body=response_body)
        )

        # Simulate receiving the empty end marker
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

        result = await asyncio.wait_for(future, timeout=1.0)
        assert result == response_body

    async def test_multi_packet_response(self, client):
        """Simulate receiving a multi-packet response."""
        request_id = 1
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = []

        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="part1")
        )
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="part2")
        )
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

        result = await asyncio.wait_for(future, timeout=1.0)
        assert result == "part1part2"

    async def test_chat_packet_callback(self, client):
        """Chat packets (type=1) should trigger the chat callback."""
        received = []
        client.on_chat = lambda body: received.append(body)

        client._handle_chat_packet(
            RconPacket(id=0, type=PacketType.CHAT_VALUE, body="Player: hello")
        )

        assert received == ["Player: hello"]

    async def test_follow_response_ignored(self, client):
        """Follow-response packets should be silently discarded."""
        request_id = 1
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future
        client._response_buffers[request_id] = []

        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="data")
        )
        # Follow response — should be ignored, not treated as end marker
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="",
                       is_follow_response=True)
        )
        # Actual end marker
        client._handle_response_packet(
            RconPacket(id=request_id, type=PacketType.RESPONSE_VALUE, body="")
        )

        result = await asyncio.wait_for(future, timeout=1.0)
        assert result == "data"


class TestRconReconnect:
    @pytest.fixture
    def client(self):
        return RconClient(
            host="127.0.0.1", port=21114, password="test",
            auto_reconnect=True, max_retries=3, retry_delay=0.01,
        )

    async def test_reconnect_delays_are_exponential(self, client):
        delays = [client._get_retry_delay(i) for i in range(4)]
        assert delays[0] == client._retry_delay
        assert delays[1] == client._retry_delay * 2
        assert delays[2] == client._retry_delay * 4
        assert delays[3] == client._retry_delay * 8
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rcon_client.py -v`
Expected: FAIL

**Step 3: Implement RCON client**

`squadpy/rcon/client.py`:
```python
"""Async RCON client for Squad's UE4 RCON protocol.

Handles:
- TCP connection and auth handshake
- Multi-packet response reassembly (empty-packet trick)
- Chat packets (type 0x01, unsolicited)
- Follow-response detection and discarding
- Auto-reconnect with exponential backoff
- Request queuing during reconnection
- Per-command timeout
"""

import asyncio
import logging
from typing import Callable

from squadpy.rcon.protocol import (
    PacketType,
    RconPacket,
    encode_packet,
    decode_packet,
)

logger = logging.getLogger("squadpy.rcon")

BUFFER_SIZE = 8192


class RconError(Exception):
    """General RCON error."""


class RconAuthError(RconError):
    """Authentication failed."""


class RconClient:
    """Async RCON client for Squad servers."""

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        auto_reconnect: bool = True,
        max_retries: int = 4,
        retry_delay: float = 5.0,
        command_timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.auto_reconnect = auto_reconnect
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._command_timeout = command_timeout

        self._transport: asyncio.Transport | None = None
        self._packet_id_counter = 0
        self._buffer = bytearray()
        self._pending_requests: dict[int, asyncio.Future[str]] = {}
        self._response_buffers: dict[int, list[str]] = {}
        self._connected = False
        self._reconnecting = False
        self._reconnect_event: asyncio.Event = asyncio.Event()
        self._reconnect_event.set()  # Not reconnecting initially

        # Callback for unsolicited chat/server messages
        self.on_chat: Callable[[str], None] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def _next_packet_id(self) -> int:
        self._packet_id_counter += 1
        if self._packet_id_counter >= 2**31:
            self._packet_id_counter = 1
        return self._packet_id_counter

    def _get_retry_delay(self, attempt: int) -> float:
        return self._retry_delay * (2 ** attempt)

    async def connect(self) -> None:
        """Connect to the RCON server and authenticate."""
        logger.info("Connecting to RCON at %s:%d", self.host, self.port)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self._command_timeout,
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise RconError(f"Failed to connect to {self.host}:{self.port}: {e}") from e

        self._reader = reader
        self._writer = writer
        self._connected = True
        self._buffer.clear()

        # Start the reader task
        self._reader_task = asyncio.create_task(self._read_loop())

        # Authenticate
        await self._authenticate()
        logger.info("RCON connected and authenticated")

    async def _authenticate(self) -> None:
        """Send auth packet and wait for response."""
        auth_id = self._next_packet_id()
        packet = encode_packet(PacketType.AUTH, auth_id, self.password)
        self._writer.write(packet)
        await self._writer.drain()

        # Wait for auth response
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_requests[auth_id] = future
        self._response_buffers[auth_id] = []

        try:
            await asyncio.wait_for(future, timeout=self._command_timeout)
        except asyncio.TimeoutError:
            raise RconAuthError("Authentication timed out")

    async def execute(self, command: str) -> str:
        """Send a command and return the response."""
        if not self._connected:
            raise RconError("Not connected")

        # Wait if reconnecting
        await self._reconnect_event.wait()

        request_id = self._next_packet_id()

        # Send the command packet
        cmd_packet = encode_packet(PacketType.EXEC_COMMAND, request_id, command)
        # Send an empty packet with same ID as end-of-response marker
        end_packet = encode_packet(PacketType.EXEC_COMMAND, request_id, "")

        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        self._response_buffers[request_id] = []

        self._writer.write(cmd_packet + end_packet)
        await self._writer.drain()

        try:
            return await asyncio.wait_for(future, timeout=self._command_timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            self._response_buffers.pop(request_id, None)
            raise RconError(f"Command timed out: {command}")

    async def _read_loop(self) -> None:
        """Continuously read data from the server and decode packets."""
        try:
            while self._connected:
                data = await self._reader.read(BUFFER_SIZE)
                if not data:
                    logger.warning("RCON connection closed by server")
                    await self._handle_disconnect()
                    return
                self._buffer.extend(data)
                self._process_buffer()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("RCON read error: %s", e)
            await self._handle_disconnect()

    def _process_buffer(self) -> None:
        """Decode all complete packets from the buffer."""
        while len(self._buffer) > 0:
            result = decode_packet(bytes(self._buffer))
            if result is None:
                break  # Incomplete packet, wait for more data

            packet, consumed = result
            del self._buffer[:consumed]

            if packet.type == PacketType.CHAT_VALUE:
                self._handle_chat_packet(packet)
            elif packet.type == PacketType.AUTH_RESPONSE:
                self._handle_auth_response(packet)
            else:
                self._handle_response_packet(packet)

    def _handle_auth_response(self, packet: RconPacket) -> None:
        """Handle an auth response packet."""
        # Find the auth future — it'll be in pending_requests
        if packet.id in self._pending_requests:
            future = self._pending_requests.pop(packet.id)
            self._response_buffers.pop(packet.id, None)
            if packet.id == -1:
                future.set_exception(RconAuthError("Authentication failed"))
            elif not future.done():
                future.set_result("")

    def _handle_response_packet(self, packet: RconPacket) -> None:
        """Handle a response value packet (type 0)."""
        if packet.is_follow_response:
            return  # Discard UE4 follow-response

        request_id = packet.id
        if request_id not in self._pending_requests:
            return

        if packet.body == "":
            # Empty body = end of multi-packet response
            future = self._pending_requests.pop(request_id)
            parts = self._response_buffers.pop(request_id, [])
            if not future.done():
                future.set_result("".join(parts))
        else:
            self._response_buffers.setdefault(request_id, []).append(packet.body)

    def _handle_chat_packet(self, packet: RconPacket) -> None:
        """Handle unsolicited chat/server message."""
        if self.on_chat is not None:
            try:
                self.on_chat(packet.body)
            except Exception:
                logger.exception("Error in chat callback")

    async def _handle_disconnect(self) -> None:
        """Handle unexpected disconnection."""
        self._connected = False
        # Reject all pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(RconError("Connection lost"))
        self._pending_requests.clear()
        self._response_buffers.clear()

        if self.auto_reconnect:
            await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        self._reconnecting = True
        self._reconnect_event.clear()

        for attempt in range(self._max_retries):
            delay = self._get_retry_delay(attempt)
            logger.info("Reconnecting in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, self._max_retries)
            await asyncio.sleep(delay)

            try:
                await self.connect()
                self._reconnecting = False
                self._reconnect_event.set()
                logger.info("Reconnected successfully")
                return
            except RconError as e:
                logger.warning("Reconnect attempt %d failed: %s", attempt + 1, e)

        self._reconnecting = False
        self._reconnect_event.set()
        logger.error("Failed to reconnect after %d attempts", self._max_retries)

    async def close(self) -> None:
        """Close the RCON connection."""
        self._connected = False
        if hasattr(self, "_reader_task"):
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "_writer") and self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        logger.info("RCON connection closed")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rcon_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add squadpy/rcon/client.py tests/test_rcon_client.py
git commit -m "feat: add async RCON client with reconnect and multi-packet support"
```

---

## Task 7: Plugin Base Class & Decorators

**Files:**
- Create: `squadpy/plugin.py`
- Create: `tests/test_plugin.py`

**Step 1: Write failing tests**

`tests/test_plugin.py`:
```python
"""Tests for plugin base class and decorators."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.plugin import Plugin, on_event, periodic


class SamplePlugin(Plugin):
    name = "Sample"
    description = "A test plugin"
    requires = ["rcon"]

    async def on_enable(self):
        self.enabled_called = True

    async def on_disable(self):
        self.disabled_called = True

    @on_event("player_connected")
    async def handle_connect(self, event):
        self.last_event = event

    @on_event("chat_message")
    async def handle_chat(self, event):
        self.last_chat = event

    @periodic(seconds=5)
    async def check_something(self):
        self.check_called = True


class MinimalPlugin(Plugin):
    name = "Minimal"
    description = "No requirements"


class TestPluginClass:
    @pytest.fixture
    def plugin(self):
        p = SamplePlugin(
            rcon=MagicMock(),
            discord=None,
            db=None,
            config={"timeout": 30},
            server=MagicMock(),
        )
        return p

    def test_plugin_name(self, plugin):
        assert plugin.name == "Sample"

    def test_plugin_has_rcon(self, plugin):
        assert plugin.rcon is not None

    def test_plugin_has_logger(self, plugin):
        assert plugin.logger.name == "squadpy.plugins.sample"

    def test_plugin_config(self, plugin):
        assert plugin.config["timeout"] == 30

    def test_no_discord_is_none(self, plugin):
        assert plugin.discord is None

    async def test_on_enable(self, plugin):
        await plugin.on_enable()
        assert plugin.enabled_called

    async def test_on_disable(self, plugin):
        await plugin.on_disable()
        assert plugin.disabled_called


class TestOnEventDecorator:
    def test_marks_handler_with_event_name(self):
        p = SamplePlugin(
            rcon=MagicMock(), discord=None, db=None,
            config={}, server=MagicMock(),
        )
        assert hasattr(p.handle_connect, "_squadpy_event")
        assert p.handle_connect._squadpy_event == "player_connected"

    def test_collects_all_event_handlers(self):
        handlers = SamplePlugin.get_event_handlers()
        event_names = {name for name, _ in handlers}
        assert "player_connected" in event_names
        assert "chat_message" in event_names

    def test_handlers_are_callable(self):
        handlers = SamplePlugin.get_event_handlers()
        for _, method_name in handlers:
            assert isinstance(method_name, str)


class TestPeriodicDecorator:
    def test_marks_method_with_interval(self):
        p = SamplePlugin(
            rcon=MagicMock(), discord=None, db=None,
            config={}, server=MagicMock(),
        )
        assert hasattr(p.check_something, "_squadpy_periodic")
        assert p.check_something._squadpy_periodic == 5

    def test_collects_periodic_tasks(self):
        tasks = SamplePlugin.get_periodic_tasks()
        assert len(tasks) == 1
        method_name, interval = tasks[0]
        assert method_name == "check_something"
        assert interval == 5


class TestPluginRequires:
    def test_requires_list(self):
        assert SamplePlugin.requires == ["rcon"]

    def test_no_requires(self):
        assert MinimalPlugin.requires == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugin.py -v`
Expected: FAIL

**Step 3: Implement plugin module**

`squadpy/plugin.py`:
```python
"""Plugin base class and decorators."""

import logging
from typing import Any


def on_event(event_name: str):
    """Decorator to subscribe a plugin method to an event."""
    def decorator(func):
        func._squadpy_event = event_name
        return func
    return decorator


def periodic(seconds: float):
    """Decorator to run a plugin method on an interval."""
    def decorator(func):
        func._squadpy_periodic = seconds
        return func
    return decorator


class Plugin:
    """Base class for all SquadPy plugins."""

    name: str = ""
    description: str = ""
    requires: list[str] = []

    def __init__(
        self,
        rcon: Any = None,
        discord: Any = None,
        db: Any = None,
        config: dict = None,
        server: Any = None,
    ):
        self.rcon = rcon
        self.discord = discord
        self.db = db
        self.config = config or {}
        self.server = server
        plugin_id = self.name.lower().replace(" ", "_") or self.__class__.__name__.lower()
        self.logger = logging.getLogger(f"squadpy.plugins.{plugin_id}")

    async def on_enable(self) -> None:
        """Called when the plugin is enabled. Override in subclass."""

    async def on_disable(self) -> None:
        """Called when the plugin is disabled. Override in subclass."""

    @classmethod
    def get_event_handlers(cls) -> list[tuple[str, str]]:
        """Return list of (event_name, method_name) for all @on_event methods."""
        handlers = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if callable(attr) and hasattr(attr, "_squadpy_event"):
                handlers.append((attr._squadpy_event, attr_name))
        return handlers

    @classmethod
    def get_periodic_tasks(cls) -> list[tuple[str, float]]:
        """Return list of (method_name, interval_seconds) for all @periodic methods."""
        tasks = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if callable(attr) and hasattr(attr, "_squadpy_periodic"):
                tasks.append((attr_name, attr._squadpy_periodic))
        return tasks
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugin.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add squadpy/plugin.py tests/test_plugin.py
git commit -m "feat: add plugin base class with @on_event and @periodic decorators"
```

---

## Task 8: Plugin Loader

**Files:**
- Create: `squadpy/plugin_loader.py`
- Create: `tests/test_plugin_loader.py`
- Create: `tests/fixtures/plugins/good_plugin/plugin.py`
- Create: `tests/fixtures/plugins/bad_plugin/plugin.py`
- Create: `tests/fixtures/plugins/disabled_plugin/plugin.py`
- Create: `tests/fixtures/config/plugins/good_plugin.toml`
- Create: `tests/fixtures/config/plugins/bad_plugin.toml`
- Create: `tests/fixtures/config/plugins/disabled_plugin.toml`

**Step 1: Create test fixture plugins**

`tests/fixtures/plugins/good_plugin/plugin.py`:
```python
from squadpy.plugin import Plugin, on_event


class GoodPlugin(Plugin):
    name = "Good Plugin"
    description = "A working test plugin"
    requires = ["rcon"]

    async def on_enable(self):
        self.logger.info("Good plugin enabled")

    @on_event("test_event")
    async def handle_test(self, event):
        pass
```

`tests/fixtures/plugins/bad_plugin/plugin.py`:
```python
from squadpy.plugin import Plugin


class BadPlugin(Plugin):
    name = "Bad Plugin"
    description = "Fails on enable"

    async def on_enable(self):
        raise RuntimeError("Intentional failure")
```

`tests/fixtures/plugins/disabled_plugin/plugin.py`:
```python
from squadpy.plugin import Plugin


class DisabledPlugin(Plugin):
    name = "Disabled Plugin"
    description = "This plugin is disabled"
```

`tests/fixtures/config/plugins/good_plugin.toml`:
```toml
enabled = true

[settings]
test_value = 42
```

`tests/fixtures/config/plugins/bad_plugin.toml`:
```toml
enabled = true
```

`tests/fixtures/config/plugins/disabled_plugin.toml`:
```toml
enabled = false
```

**Step 2: Write failing tests**

`tests/test_plugin_loader.py`:
```python
"""Tests for plugin discovery, loading, and error isolation."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

from squadpy.plugin_loader import PluginLoader, PluginStatus


FIXTURES = Path(__file__).parent / "fixtures"


class TestPluginDiscovery:
    def test_discover_plugins(self):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        discovered = loader.discover()
        names = {d.dir_name for d in discovered}
        assert "good_plugin" in names
        assert "bad_plugin" in names
        assert "disabled_plugin" in names

    def test_discover_reads_config(self):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        discovered = loader.discover()
        good = next(d for d in discovered if d.dir_name == "good_plugin")
        assert good.config["settings"]["test_value"] == 42
        assert good.enabled is True

    def test_discover_disabled_plugin(self):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        discovered = loader.discover()
        disabled = next(d for d in discovered if d.dir_name == "disabled_plugin")
        assert disabled.enabled is False


class TestPluginLoading:
    @pytest.fixture
    def services(self):
        return {
            "rcon": MagicMock(),
            "discord": None,
            "db": None,
            "server": MagicMock(),
        }

    async def test_load_good_plugin(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert good.status == PluginStatus.ENABLED
        assert good.instance is not None

    async def test_bad_plugin_fails_gracefully(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        bad = next(r for r in results if r.name == "Bad Plugin")
        assert bad.status == PluginStatus.FAILED
        assert "Intentional failure" in bad.error

    async def test_disabled_plugin_skipped(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        disabled = next(r for r in results if r.name == "Disabled Plugin")
        assert disabled.status == PluginStatus.DISABLED

    async def test_missing_requirement_fails(self, services):
        services["rcon"] = None  # Remove RCON
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert good.status == PluginStatus.FAILED
        assert "rcon" in good.error.lower()

    async def test_good_plugin_event_handlers_registered(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert len(good.event_handlers) > 0
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_plugin_loader.py -v`
Expected: FAIL

**Step 4: Implement plugin loader**

`squadpy/plugin_loader.py`:
```python
"""Plugin discovery, loading, and lifecycle management."""

import importlib
import importlib.util
import logging
import sys
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from squadpy.plugin import Plugin

logger = logging.getLogger("squadpy.plugins")


class PluginStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass
class DiscoveredPlugin:
    dir_name: str
    module_path: Path
    config: dict
    enabled: bool


@dataclass
class LoadedPlugin:
    name: str
    dir_name: str
    status: PluginStatus
    instance: Plugin | None = None
    error: str = ""
    event_handlers: list[tuple[str, str]] = field(default_factory=list)
    periodic_tasks: list[tuple[str, float]] = field(default_factory=list)


class PluginLoader:
    """Discovers and loads plugins from the plugins directory."""

    def __init__(self, plugins_dir: Path, config_dir: Path):
        self.plugins_dir = plugins_dir
        self.config_dir = config_dir

    def discover(self) -> list[DiscoveredPlugin]:
        """Find all plugin directories and their configs."""
        discovered = []
        if not self.plugins_dir.exists():
            return discovered

        for plugin_dir in sorted(self.plugins_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            module_path = plugin_dir / "plugin.py"
            if not module_path.exists():
                continue

            # Load config
            config_file = self.config_dir / f"{plugin_dir.name}.toml"
            config = {}
            enabled = True
            if config_file.exists():
                with open(config_file, "rb") as f:
                    config = tomllib.load(f)
                enabled = config.get("enabled", True)

            discovered.append(DiscoveredPlugin(
                dir_name=plugin_dir.name,
                module_path=module_path,
                config=config,
                enabled=enabled,
            ))

        return discovered

    async def load_all(self, services: dict[str, Any]) -> list[LoadedPlugin]:
        """Load all discovered plugins, isolating failures."""
        discovered = self.discover()
        results = []

        for plugin_info in discovered:
            result = await self._load_one(plugin_info, services)
            results.append(result)

        return results

    async def _load_one(
        self, info: DiscoveredPlugin, services: dict[str, Any]
    ) -> LoadedPlugin:
        """Load a single plugin with full error isolation."""
        if not info.enabled:
            # Still need to import to get the plugin name
            try:
                plugin_cls = self._import_plugin_class(info)
                name = plugin_cls.name or info.dir_name
            except Exception:
                name = info.dir_name
            return LoadedPlugin(
                name=name,
                dir_name=info.dir_name,
                status=PluginStatus.DISABLED,
            )

        try:
            plugin_cls = self._import_plugin_class(info)
        except Exception as e:
            logger.error("Failed to import plugin %s: %s", info.dir_name, e)
            return LoadedPlugin(
                name=info.dir_name,
                dir_name=info.dir_name,
                status=PluginStatus.FAILED,
                error=str(e),
            )

        name = plugin_cls.name or info.dir_name

        # Check requirements
        for req in plugin_cls.requires:
            if services.get(req) is None:
                error = f"Requires {req} but it is not configured"
                logger.error("Plugin %s: %s", name, error)
                return LoadedPlugin(
                    name=name,
                    dir_name=info.dir_name,
                    status=PluginStatus.FAILED,
                    error=error,
                )

        # Instantiate
        try:
            settings = info.config.get("settings", {})
            instance = plugin_cls(
                rcon=services.get("rcon"),
                discord=services.get("discord"),
                db=services.get("db"),
                config=settings,
                server=services.get("server"),
            )
        except Exception as e:
            logger.error("Failed to instantiate plugin %s: %s", name, e)
            return LoadedPlugin(
                name=name,
                dir_name=info.dir_name,
                status=PluginStatus.FAILED,
                error=str(e),
            )

        # Enable
        try:
            await instance.on_enable()
        except Exception as e:
            logger.error("Plugin %s failed on enable: %s", name, e)
            return LoadedPlugin(
                name=name,
                dir_name=info.dir_name,
                status=PluginStatus.FAILED,
                error=str(e),
            )

        event_handlers = plugin_cls.get_event_handlers()
        periodic_tasks = plugin_cls.get_periodic_tasks()

        logger.info("Plugin %s enabled", name)
        return LoadedPlugin(
            name=name,
            dir_name=info.dir_name,
            status=PluginStatus.ENABLED,
            instance=instance,
            event_handlers=event_handlers,
            periodic_tasks=periodic_tasks,
        )

    def _import_plugin_class(self, info: DiscoveredPlugin) -> type[Plugin]:
        """Import a plugin module and find the Plugin subclass."""
        module_name = f"squadpy_plugin_{info.dir_name}"

        spec = importlib.util.spec_from_file_location(module_name, info.module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {info.module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find the Plugin subclass
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                    issubclass(attr, Plugin) and
                    attr is not Plugin):
                return attr

        raise ImportError(f"No Plugin subclass found in {info.module_path}")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plugin_loader.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add squadpy/plugin_loader.py tests/test_plugin_loader.py tests/fixtures/
git commit -m "feat: add plugin loader with discovery, validation, and error isolation"
```

---

## Task 9: Server Orchestrator & Startup Summary

**Files:**
- Create: `squadpy/server.py`
- Create: `tests/test_server.py`

**Step 1: Write failing tests**

`tests/test_server.py`:
```python
"""Tests for the server orchestrator."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.server import SquadPyServer
from squadpy.config import ServerConfig, LoggingConfig
from squadpy.plugin_loader import LoadedPlugin, PluginStatus


class TestSquadPyServer:
    @pytest.fixture
    def server_config(self):
        return ServerConfig(
            rcon={"host": "127.0.0.1", "port": 21114, "password": "test"}
        )

    @pytest.fixture
    def logging_config(self):
        return LoggingConfig(level="INFO", file={"enabled": False})

    @pytest.fixture
    def server(self, server_config, logging_config):
        return SquadPyServer(
            server_config=server_config,
            logging_config=logging_config,
            base_dir=Path("/tmp/test"),
        )

    def test_initial_state(self, server):
        assert not server.running

    def test_version(self, server):
        assert server.version == "0.1.0"


class TestStartupSummary:
    def test_format_service_status_ok(self):
        from squadpy.server import format_service_line
        line = format_service_line("RCON", True, "connected (127.0.0.1:21114)")
        assert "RCON" in line
        assert "connected" in line

    def test_format_service_status_fail(self):
        from squadpy.server import format_service_line
        line = format_service_line("Discord", False, "not configured")
        assert "Discord" in line
        assert "not configured" in line

    def test_format_plugin_status_enabled(self):
        from squadpy.server import format_plugin_line
        plugin = LoadedPlugin(
            name="TKWarn", dir_name="tk_warn",
            status=PluginStatus.ENABLED,
        )
        line = format_plugin_line(plugin)
        assert "TKWarn" in line
        assert "enabled" in line.lower() or "ok" in line.lower()

    def test_format_plugin_status_failed(self):
        from squadpy.server import format_plugin_line
        plugin = LoadedPlugin(
            name="BadPlugin", dir_name="bad_plugin",
            status=PluginStatus.FAILED,
            error="missing channel_id",
        )
        line = format_plugin_line(plugin)
        assert "BadPlugin" in line
        assert "missing channel_id" in line

    def test_format_plugin_status_disabled(self):
        from squadpy.server import format_plugin_line
        plugin = LoadedPlugin(
            name="SeedReward", dir_name="seed_reward",
            status=PluginStatus.DISABLED,
        )
        line = format_plugin_line(plugin)
        assert "SeedReward" in line
        assert "disabled" in line.lower()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: FAIL

**Step 3: Implement server module**

`squadpy/server.py`:
```python
"""Main server orchestrator — startup, shutdown, and lifecycle."""

import asyncio
import logging
import signal
from pathlib import Path

from squadpy.config import ServerConfig, LoggingConfig, load_config
from squadpy.events.emitter import EventBus
from squadpy.logger import setup_logging
from squadpy.plugin import Plugin
from squadpy.plugin_loader import PluginLoader, LoadedPlugin, PluginStatus
from squadpy.rcon.client import RconClient

logger = logging.getLogger("squadpy")

VERSION = "0.1.0"


def format_service_line(name: str, ok: bool, detail: str) -> str:
    status = "ok" if ok else "FAIL"
    return f"    {name:<16s} {status:<5s} {detail}"


def format_plugin_line(plugin: LoadedPlugin) -> str:
    if plugin.status == PluginStatus.ENABLED:
        return f"    {plugin.name:<24s} ok       enabled"
    elif plugin.status == PluginStatus.DISABLED:
        return f"    {plugin.name:<24s} --       disabled"
    else:
        return f"    {plugin.name:<24s} FAIL     {plugin.error}"


class SquadPyServer:
    """Main SquadPy server that orchestrates all components."""

    def __init__(
        self,
        server_config: ServerConfig,
        logging_config: LoggingConfig,
        base_dir: Path,
    ):
        self._server_config = server_config
        self._logging_config = logging_config
        self._base_dir = base_dir
        self._running = False
        self._event_bus = EventBus()
        self._rcon: RconClient | None = None
        self._loaded_plugins: list[LoadedPlugin] = []
        self._periodic_tasks: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()

    @property
    def version(self) -> str:
        return VERSION

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start the server: connect services, load plugins, display summary."""
        self._running = True

        # Setup logging
        log_dir = self._base_dir / self._logging_config.file.path
        setup_logging(self._logging_config, log_dir if self._logging_config.file.enabled else None)

        # Connect RCON
        rcon_ok = False
        rcon_detail = ""
        try:
            self._rcon = RconClient(
                host=self._server_config.rcon.host,
                port=self._server_config.rcon.port,
                password=self._server_config.rcon.password,
            )
            await self._rcon.connect()
            self._rcon.on_chat = self._handle_chat
            rcon_ok = True
            rcon_detail = f"connected ({self._server_config.rcon.host}:{self._server_config.rcon.port})"
        except Exception as e:
            rcon_detail = str(e)
            logger.error("RCON connection failed: %s", e)

        # Load plugins
        services = {
            "rcon": self._rcon if rcon_ok else None,
            "discord": None,   # Phase 3
            "db": None,        # Phase 4
            "server": self,
        }

        plugin_loader = PluginLoader(
            plugins_dir=self._base_dir / "plugins",
            config_dir=self._base_dir / "config" / "plugins",
        )
        self._loaded_plugins = await plugin_loader.load_all(services)

        # Register event handlers for enabled plugins
        for lp in self._loaded_plugins:
            if lp.status == PluginStatus.ENABLED and lp.instance:
                self._register_plugin_events(lp)
                self._start_periodic_tasks(lp)

        # Display startup summary
        self._print_summary(rcon_ok, rcon_detail)

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Wait until shutdown
        await self._shutdown_event.wait()

    def _register_plugin_events(self, loaded: LoadedPlugin) -> None:
        """Register a plugin's event handlers with the event bus."""
        for event_name, method_name in loaded.event_handlers:
            handler = getattr(loaded.instance, method_name)
            self._event_bus.subscribe(event_name, handler)

    def _start_periodic_tasks(self, loaded: LoadedPlugin) -> None:
        """Start asyncio tasks for a plugin's @periodic methods."""
        for method_name, interval in loaded.periodic_tasks:
            method = getattr(loaded.instance, method_name)
            task = asyncio.create_task(
                self._run_periodic(loaded.name, method, interval)
            )
            self._periodic_tasks.append(task)

    async def _run_periodic(self, plugin_name: str, method, interval: float) -> None:
        """Run a periodic task in a loop."""
        while self._running:
            await asyncio.sleep(interval)
            try:
                await method()
            except Exception:
                logger.exception("Error in periodic task %s.%s",
                                 plugin_name, method.__name__)

    def _handle_chat(self, body: str) -> None:
        """Handle unsolicited RCON chat messages."""
        # Will be expanded in Phase 2 when log parser events are defined
        logger.debug("Chat: %s", body)

    def _print_summary(self, rcon_ok: bool, rcon_detail: str) -> None:
        """Print the startup summary to console."""
        lines = [
            "",
            f"  SquadPy v{self.version}",
            "",
            "  Core Services:",
            format_service_line("RCON", rcon_ok, rcon_detail),
            format_service_line("Log Reader", False, "not configured (Phase 2)"),
            format_service_line("Discord", False, "not configured (Phase 3)"),
            format_service_line("Database", False, "not configured (Phase 4)"),
            "",
        ]

        if self._loaded_plugins:
            lines.append("  Plugins:")
            for lp in self._loaded_plugins:
                lines.append(format_plugin_line(lp))
            lines.append("")

        print("\n".join(lines))

    async def stop(self) -> None:
        """Graceful shutdown: disable plugins, close connections."""
        if not self._running:
            return
        logger.info("Shutting down...")
        self._running = False

        # Cancel periodic tasks
        for task in self._periodic_tasks:
            task.cancel()

        # Disable plugins (with timeout)
        for lp in self._loaded_plugins:
            if lp.status == PluginStatus.ENABLED and lp.instance:
                try:
                    await asyncio.wait_for(lp.instance.on_disable(), timeout=5.0)
                except Exception:
                    logger.exception("Error disabling plugin %s", lp.name)

        # Close RCON
        if self._rcon:
            await self._rcon.close()

        self._event_bus.clear()
        self._shutdown_event.set()
        logger.info("Shutdown complete")

    async def reload_plugin(self, plugin_name: str) -> tuple[bool, str]:
        """Hot-reload a plugin by name."""
        # Find the loaded plugin
        target = None
        for lp in self._loaded_plugins:
            if lp.dir_name == plugin_name or lp.name == plugin_name:
                target = lp
                break

        if target is None:
            return False, f"Plugin '{plugin_name}' not found"

        # Disable old instance
        if target.instance:
            try:
                await target.instance.on_disable()
            except Exception:
                logger.exception("Error disabling %s during reload", target.name)

            # Unsubscribe old event handlers
            for event_name, method_name in target.event_handlers:
                handler = getattr(target.instance, method_name)
                self._event_bus.unsubscribe(event_name, handler)

        # Re-load
        services = {
            "rcon": self._rcon,
            "discord": None,
            "db": None,
            "server": self,
        }
        loader = PluginLoader(
            plugins_dir=self._base_dir / "plugins",
            config_dir=self._base_dir / "config" / "plugins",
        )
        discovered = loader.discover()
        info = next((d for d in discovered if d.dir_name == target.dir_name), None)
        if info is None:
            return False, "Plugin directory no longer exists"

        new_loaded = await loader._load_one(info, services)

        # Replace in list
        idx = self._loaded_plugins.index(target)
        self._loaded_plugins[idx] = new_loaded

        if new_loaded.status == PluginStatus.ENABLED and new_loaded.instance:
            self._register_plugin_events(new_loaded)
            self._start_periodic_tasks(new_loaded)
            return True, ""

        return False, new_loaded.error
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add squadpy/server.py tests/test_server.py
git commit -m "feat: add server orchestrator with startup summary and graceful shutdown"
```

---

## Task 10: Entry Point & Wiring

**Files:**
- Modify: `squadpy/__main__.py`
- Modify: `squadpy/__init__.py`

**Step 1: Update __init__.py exports**

`squadpy/__init__.py`:
```python
"""SquadPy — Python-based Squad game server management framework."""

from squadpy.plugin import Plugin, on_event, periodic
from squadpy.events.types import BaseEvent
from squadpy.server import VERSION as __version__

__all__ = ["Plugin", "on_event", "periodic", "BaseEvent", "__version__"]
```

**Step 2: Implement __main__.py**

`squadpy/__main__.py`:
```python
"""SquadPy entry point: python -m squadpy"""

import asyncio
import sys
from pathlib import Path

from squadpy.config import ServerConfig, LoggingConfig, DatabaseConfig, load_config
from squadpy.server import SquadPyServer


def main():
    base_dir = Path.cwd()
    config_dir = base_dir / "config"

    # Load configs
    try:
        server_config = load_config(ServerConfig, config_dir / "server.toml")
    except Exception as e:
        print(f"Error loading server.toml: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        logging_config = load_config(LoggingConfig, config_dir / "logging.toml")
    except FileNotFoundError:
        logging_config = LoggingConfig()
    except Exception as e:
        print(f"Error loading logging.toml: {e}", file=sys.stderr)
        sys.exit(1)

    server = SquadPyServer(
        server_config=server_config,
        logging_config=logging_config,
        base_dir=base_dir,
    )

    asyncio.run(server.start())


if __name__ == "__main__":
    main()
```

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 4: Verify entry point works**

Run: `python -m squadpy` (from project root with valid config)
Expected: Starts, tries to connect RCON (will fail without a server), shows startup summary, handles Ctrl+C gracefully

**Step 5: Commit**

```bash
git add squadpy/__init__.py squadpy/__main__.py
git commit -m "feat: add entry point and public API exports"
```

---

## Summary

After completing all 10 tasks, Phase 1 delivers:

| Component | Status |
|-----------|--------|
| Project scaffolding | pyproject.toml, directory structure, dev tooling |
| Config loader | TOML loading with Pydantic validation |
| Logging | Configurable levels, Squad-style timestamped file rotation |
| Event bus | Async dispatch with error isolation |
| RCON protocol | Packet encode/decode with UE4 quirks (chat type, follow-response) |
| RCON client | Async with reconnect, multi-packet reassembly, request queuing |
| Plugin base class | `@on_event`, `@periodic` decorators, service injection |
| Plugin loader | Discovery, config loading, requirement checking, error isolation |
| Server orchestrator | Startup sequence, shutdown hooks, startup summary |
| Entry point | `python -m squadpy` |

Total estimated commits: 10
