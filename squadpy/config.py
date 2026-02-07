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
