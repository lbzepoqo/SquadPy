"""Authenticated websocket control service."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from aiohttp import WSMsgType, web

logger = logging.getLogger("squadpy.api.websocket")


@dataclass
class ControlResponse:
    ok: bool
    error: str = ""
    code: str = ""
    result: dict[str, Any] | None = None
    request_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok}
        if self.request_id:
            payload["request_id"] = self.request_id
        if self.result is not None:
            payload["result"] = self.result
        if not self.ok:
            payload["error"] = self.error
            payload["code"] = self.code
        return payload


class WebsocketControlService:
    """Authenticated websocket service for privileged control commands."""

    def __init__(
        self,
        *,
        token: str,
        host: str = "127.0.0.1",
        port: int = 8090,
        path: str = "/ws/control",
        server: Any = None,
        rcon: Any = None,
    ):
        self._token = token
        self._host = host
        self._port = port
        self._path = path
        self._server = server
        self._rcon = rcon
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def path(self) -> str:
        return self._path

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get(self._path, self._handle_ws)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self._host, port=self._port)
        await self._site.start()
        logger.info("Websocket control service started at ws://%s:%d%s", self._host, self._port, self._path)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            logger.info("Websocket control service stopped")

    async def process_payload(
        self,
        payload: dict[str, Any],
        *,
        token: str | None,
    ) -> dict[str, Any]:
        request_id = str(payload.get("request_id", "")).strip()
        if not self._is_authorized(token):
            return ControlResponse(
                ok=False,
                error="Unauthorized",
                code="unauthorized",
                request_id=request_id,
            ).as_dict()

        action = str(payload.get("action", "")).strip().lower()
        if action == "rcon.execute":
            command = str(payload.get("command", "")).strip()
            if not command:
                return ControlResponse(
                    ok=False,
                    error="Missing command",
                    code="invalid_request",
                    request_id=request_id,
                ).as_dict()

            rcon = self._resolve_rcon()
            if rcon is None:
                return ControlResponse(
                    ok=False,
                    error="RCON unavailable",
                    code="unavailable",
                    request_id=request_id,
                ).as_dict()

            response = await rcon.execute(command)
            return ControlResponse(
                ok=True,
                result={"response": response},
                request_id=request_id,
            ).as_dict()

        return ControlResponse(
            ok=False,
            error=f"Unknown action: {action}",
            code="unknown_action",
            request_id=request_id,
        ).as_dict()

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        session_token = self._request_token(request)

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                response: dict[str, Any]
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    response = ControlResponse(
                        ok=False,
                        error="Malformed JSON",
                        code="invalid_json",
                    ).as_dict()
                else:
                    if not isinstance(payload, dict):
                        response = ControlResponse(
                            ok=False,
                            error="Payload must be an object",
                            code="invalid_json",
                        ).as_dict()
                    else:
                        request_token = str(payload.get("token", "")).strip() or session_token
                        response = await self.process_payload(payload, token=request_token)

                await ws.send_json(response)
                continue

            if msg.type == WSMsgType.ERROR:
                logger.warning("Websocket connection error: %s", ws.exception())
                break

        return ws

    def _request_token(self, request: web.Request) -> str:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:].strip()

        query_token = request.query.get("token")
        if query_token:
            return str(query_token).strip()
        return ""

    def _is_authorized(self, token: str | None) -> bool:
        if not self._token:
            return False
        return bool(token) and token == self._token

    def _resolve_rcon(self):
        if self._rcon is not None:
            return self._rcon
        if self._server is None:
            return None
        return getattr(self._server, "_rcon", None)
