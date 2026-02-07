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
