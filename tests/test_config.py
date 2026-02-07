"""Tests for TOML config loading and validation."""

import pytest
from pathlib import Path
from squadpy.config import ServerConfig, LoggingConfig, LogConfig, load_config


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


class TestLogConfig:
    def test_defaults(self):
        config = LogConfig()
        assert config.enabled is False
        assert config.mode == "local"
        assert config.path == ""
        assert config.poll_interval == 1.0

    def test_local_mode(self):
        config = LogConfig(enabled=True, mode="local", path="/var/log/squad/SquadGame.log")
        assert config.enabled is True
        assert config.path == "/var/log/squad/SquadGame.log"

    def test_sftp_mode(self):
        config = LogConfig(
            enabled=True, mode="sftp", path="/logs/SquadGame.log",
            host="10.0.0.1", port=22, username="squad", password="pass",
        )
        assert config.mode == "sftp"
        assert config.host == "10.0.0.1"

    def test_invalid_mode_raises(self):
        with pytest.raises(Exception):
            LogConfig(mode="ftp")

    def test_invalid_poll_interval_raises(self):
        with pytest.raises(Exception):
            LogConfig(poll_interval=0)


class TestServerConfigWithLog:
    def test_log_is_optional(self):
        config = ServerConfig(rcon={"host": "127.0.0.1", "password": "pass"})
        assert config.log.enabled is False

    def test_log_section_parsed(self):
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "pass"},
            log={"enabled": True, "mode": "local", "path": "/tmp/SquadGame.log"},
        )
        assert config.log.enabled is True
        assert config.log.path == "/tmp/SquadGame.log"
