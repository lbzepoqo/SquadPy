"""Tests for TOML config loading and validation."""

from pathlib import Path

import pytest

from squadpy.config import (
    ApiConfig,
    DiscordConfig,
    LogConfig,
    LoggingConfig,
    ServerConfig,
    load_config,
)


class TestServerConfig:
    def test_valid_config(self):
        config = ServerConfig.model_validate({
            "rcon": {"host": "192.168.1.10", "port": 21114, "password": "secret"},
        })
        assert config.rcon.host == "192.168.1.10"
        assert config.rcon.port == 21114
        assert config.rcon.password == "secret"

    def test_default_port(self):
        config = ServerConfig.model_validate({"rcon": {"host": "127.0.0.1", "password": "pass"}})
        assert config.rcon.port == 21114

    def test_missing_host_raises(self):
        with pytest.raises(Exception):
            ServerConfig.model_validate({"rcon": {"password": "pass"}})

    def test_missing_password_raises(self):
        with pytest.raises(Exception):
            ServerConfig.model_validate({"rcon": {"host": "127.0.0.1"}})

    def test_invalid_port_raises(self):
        with pytest.raises(Exception):
            ServerConfig.model_validate({"rcon": {"host": "127.0.0.1", "port": 99999, "password": "p"}})


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
        assert config.poll_interval == 0.25

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
            LogConfig.model_validate({"mode": "ftp"})

    def test_invalid_poll_interval_raises(self):
        with pytest.raises(Exception):
            LogConfig(poll_interval=0)


class TestServerConfigWithLog:
    def test_log_is_optional(self):
        config = ServerConfig.model_validate({"rcon": {"host": "127.0.0.1", "password": "pass"}})
        assert config.log.enabled is False

    def test_log_section_parsed(self):
        config = ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "password": "pass"},
            "log": {"enabled": True, "mode": "local", "path": "/tmp/SquadGame.log"},
        })
        assert config.log.enabled is True
        assert config.log.path == "/tmp/SquadGame.log"


class TestDiscordConfig:
    def test_defaults(self):
        config = DiscordConfig()
        assert config.enabled is False
        assert config.token == ""
        assert config.guild_id == 0
        assert config.command_prefix == "!"

    def test_valid_config(self):
        config = DiscordConfig(
            enabled=True,
            token="Bot_Token_Here",
            guild_id=123456789012345678,
        )
        assert config.enabled is True
        assert config.guild_id == 123456789012345678

    def test_enabled_without_token_raises(self):
        with pytest.raises(Exception):
            DiscordConfig(enabled=True, guild_id=123456789012345678)

    def test_enabled_without_guild_id_raises(self):
        with pytest.raises(Exception):
            DiscordConfig(enabled=True, token="some_token")


class TestServerConfigWithDiscord:
    def test_discord_is_optional(self):
        config = ServerConfig.model_validate({"rcon": {"host": "127.0.0.1", "password": "pass"}})
        assert config.discord.enabled is False

    def test_discord_section_parsed(self):
        config = ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "password": "pass"},
            "discord": {"enabled": True, "token": "tok", "guild_id": 123456789012345678},
        })
        assert config.discord.enabled is True
        assert config.discord.token == "tok"


class TestApiConfig:
    def test_defaults(self):
        config = ApiConfig()
        assert config.enabled is False
        assert config.host == "127.0.0.1"
        assert config.port == 8090
        assert config.websocket_path == "/ws/control"
        assert config.auth_token == ""
        assert config.rbac_enabled is False
        assert config.rbac_default_role == "admin"
        assert config.rbac_role_permissions == {}
        assert config.webhook_signing_enabled is False
        assert config.webhook_signing_secret == ""
        assert config.webhook_signature_header == "X-SquadPy-Signature"
        assert config.webhook_timestamp_header == "X-SquadPy-Timestamp"
        assert config.webhook_max_age_seconds == 300

    def test_enabled_requires_auth_token(self):
        with pytest.raises(Exception):
            ApiConfig(enabled=True, auth_token="")

    def test_invalid_port_raises(self):
        with pytest.raises(Exception):
            ApiConfig(port=70000)

    def test_invalid_websocket_path_raises(self):
        with pytest.raises(Exception):
            ApiConfig(websocket_path="ws/control")

    def test_invalid_empty_default_role_raises(self):
        with pytest.raises(Exception):
            ApiConfig(rbac_default_role="   ")

    def test_invalid_role_permissions_value_raises(self):
        with pytest.raises(Exception):
            ApiConfig.model_validate({"rbac_role_permissions": {"admin": "not-a-list"}})

    def test_webhook_signing_enabled_requires_secret(self):
        with pytest.raises(Exception):
            ApiConfig(webhook_signing_enabled=True, webhook_signing_secret="")

    def test_webhook_headers_must_not_be_empty(self):
        with pytest.raises(Exception):
            ApiConfig(webhook_signature_header=" ")
        with pytest.raises(Exception):
            ApiConfig(webhook_timestamp_header=" ")

    def test_webhook_max_age_must_be_positive(self):
        with pytest.raises(Exception):
            ApiConfig(webhook_max_age_seconds=0)


class TestServerConfigWithApi:
    def test_api_is_optional(self):
        config = ServerConfig.model_validate({"rcon": {"host": "127.0.0.1", "password": "pass"}})
        assert config.api.enabled is False

    def test_api_section_parsed(self):
        config = ServerConfig.model_validate({
            "rcon": {"host": "127.0.0.1", "password": "pass"},
            "api": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 18090,
                "websocket_path": "/ws/control",
                "auth_token": "secret_token",
                "rbac_enabled": True,
                "rbac_default_role": "moderator",
                "rbac_role_permissions": {
                    "moderator": ["control.health", "control.status"],
                    "admin": ["*"],
                },
                "webhook_signing_enabled": True,
                "webhook_signing_secret": "webhook-secret",
                "webhook_signature_header": "X-Hub-Signature-256",
                "webhook_timestamp_header": "X-Hub-Timestamp",
                "webhook_max_age_seconds": 120,
            },
        })
        assert config.api.enabled is True
        assert config.api.port == 18090
        assert config.api.auth_token == "secret_token"
        assert config.api.rbac_enabled is True
        assert config.api.rbac_default_role == "moderator"
        assert config.api.rbac_role_permissions["admin"] == ["*"]
        assert config.api.webhook_signing_enabled is True
        assert config.api.webhook_signing_secret == "webhook-secret"
        assert config.api.webhook_signature_header == "X-Hub-Signature-256"
        assert config.api.webhook_timestamp_header == "X-Hub-Timestamp"
        assert config.api.webhook_max_age_seconds == 120
