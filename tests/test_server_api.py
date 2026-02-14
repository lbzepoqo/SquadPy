"""Tests for API service integration in server orchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from squadpy.config import LoggingConfig, ServerConfig
from squadpy.server import SquadPyServer


class TestServerApiIntegration:
    async def test_start_api_not_configured(self):
        server = SquadPyServer(
            server_config=ServerConfig.model_validate({
                "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
            }),
            logging_config=LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}}),
            base_dir=Path("/tmp/test"),
        )
        ok, detail = await server._start_api()
        assert ok is False
        assert detail == "not configured"

    async def test_start_api_enabled_starts_service(self):
        server = SquadPyServer(
            server_config=ServerConfig.model_validate({
                "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
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
                },
            }),
            logging_config=LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}}),
            base_dir=Path("/tmp/test"),
        )

        with patch("squadpy.server.WebsocketControlService") as mock_cls:
            service = AsyncMock()
            mock_cls.return_value = service
            ok, detail = await server._start_api()

        assert ok is True
        assert "ws://127.0.0.1:18090/ws/control" in detail
        mock_cls.assert_called_once_with(
            token="secret_token",
            host="127.0.0.1",
            port=18090,
            path="/ws/control",
            rbac_enabled=True,
            rbac_default_role="moderator",
            rbac_role_permissions={
                "moderator": ["control.health", "control.status"],
                "admin": ["*"],
            },
            server=server,
        )
        service.start.assert_awaited_once()

    async def test_stop_shuts_down_api_service(self):
        server = SquadPyServer(
            server_config=ServerConfig.model_validate({
                "rcon": {"host": "127.0.0.1", "port": 21114, "password": "test"},
            }),
            logging_config=LoggingConfig.model_validate({"level": "INFO", "file": {"enabled": False}}),
            base_dir=Path("/tmp/test"),
        )
        server._running = True
        server._api = AsyncMock()

        await server.stop()

        server._api.stop.assert_awaited_once()
