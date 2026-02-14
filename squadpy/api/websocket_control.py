"""Authenticated websocket control service."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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
        self._audit_records: list[dict[str, Any]] = []
        self._max_audit_records = 1000

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
        app = self._build_app()
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
        origin: str = "websocket",
        actor: str = "",
    ) -> dict[str, Any]:
        request_id = str(payload.get("request_id", "")).strip()
        if not self._is_authorized(token):
            self._audit(
                actor=actor or "unknown",
                origin=origin,
                target=str(payload.get("action", "unknown")),
                outcome="rejected",
                detail="unauthorized",
            )
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
                self._audit(
                    actor=actor or "unknown",
                    origin=origin,
                    target="rcon.execute",
                    outcome="rejected",
                    detail="missing command",
                )
                return ControlResponse(
                    ok=False,
                    error="Missing command",
                    code="invalid_request",
                    request_id=request_id,
                ).as_dict()

            rcon = self._resolve_rcon()
            if rcon is None:
                self._audit(
                    actor=actor or "unknown",
                    origin=origin,
                    target="rcon.execute",
                    outcome="error",
                    detail="rcon unavailable",
                )
                return ControlResponse(
                    ok=False,
                    error="RCON unavailable",
                    code="unavailable",
                    request_id=request_id,
                ).as_dict()

            response = await rcon.execute(command)
            self._audit(
                actor=actor or "unknown",
                origin=origin,
                target=command,
                outcome="success",
            )
            return ControlResponse(
                ok=True,
                result={"response": response},
                request_id=request_id,
            ).as_dict()

        self._audit(
            actor=actor or "unknown",
            origin=origin,
            target=action or "unknown",
            outcome="rejected",
            detail="unknown action",
        )
        return ControlResponse(
            ok=False,
            error=f"Unknown action: {action}",
            code="unknown_action",
            request_id=request_id,
        ).as_dict()

    async def process_health(self, *, token: str | None) -> dict[str, Any]:
        if not self._is_authorized(token):
            return ControlResponse(
                ok=False,
                error="Unauthorized",
                code="unauthorized",
            ).as_dict()

        return ControlResponse(
            ok=True,
            result={"status": "ok"},
        ).as_dict()

    async def process_status(self, *, token: str | None) -> dict[str, Any]:
        if not self._is_authorized(token):
            return ControlResponse(
                ok=False,
                error="Unauthorized",
                code="unauthorized",
            ).as_dict()

        rcon = self._resolve_rcon()
        response = {
            "service": "control_api",
            "rcon_connected": bool(rcon and getattr(rcon, "connected", False)),
            "server_running": bool(getattr(self._server, "running", False)) if self._server else False,
        }
        return ControlResponse(
            ok=True,
            result=response,
        ).as_dict()

    async def process_command(
        self,
        payload: dict[str, Any],
        *,
        token: str | None,
        origin: str = "rest",
        actor: str = "",
    ) -> dict[str, Any]:
        request_id = str(payload.get("request_id", "")).strip()
        command = str(payload.get("command", "")).strip()
        return await self.process_payload(
            {
                "request_id": request_id,
                "action": "rcon.execute",
                "command": command,
            },
            token=token,
            origin=origin,
            actor=actor,
        )

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
                        if "actor" in payload:
                            actor = str(payload.get("actor", "")).strip()
                        else:
                            actor = str(payload.get("request_id", "")).strip()
                        response = await self.process_payload(
                            payload,
                            token=request_token,
                            origin="websocket",
                            actor=actor or "websocket_client",
                        )

                await ws.send_json(response)
                continue

            if msg.type == WSMsgType.ERROR:
                logger.warning("Websocket connection error: %s", ws.exception())
                break

        return ws

    async def _handle_health(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        response = await self.process_health(token=token)
        return web.json_response(response, status=self._http_status(response))

    async def _handle_status(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        response = await self.process_status(token=token)
        return web.json_response(response, status=self._http_status(response))

    async def _handle_command(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            response = ControlResponse(
                ok=False,
                error="Malformed JSON",
                code="invalid_json",
            ).as_dict()
            return web.json_response(response, status=self._http_status(response))

        if not isinstance(payload, dict):
            response = ControlResponse(
                ok=False,
                error="Payload must be an object",
                code="invalid_json",
            ).as_dict()
            return web.json_response(response, status=self._http_status(response))

        request_token = str(payload.get("token", "")).strip() or token
        actor = str(payload.get("actor", "")).strip() or "rest_client"
        response = await self.process_command(
            payload,
            token=request_token,
            origin="rest",
            actor=actor,
        )
        return web.json_response(response, status=self._http_status(response))

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

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get(self._path, self._handle_ws)
        app.router.add_get("/api/health", self._handle_health)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_post("/api/command", self._handle_command)
        return app

    def _http_status(self, response: dict[str, Any]) -> int:
        if bool(response.get("ok")):
            return 200
        code = str(response.get("code", ""))
        if code == "unauthorized":
            return 401
        if code in {"invalid_json", "invalid_request", "unknown_action"}:
            return 400
        if code == "unavailable":
            return 503
        return 500

    def recent_audit_records(self) -> list[dict[str, Any]]:
        return list(self._audit_records)

    def _audit(
        self,
        *,
        actor: str,
        origin: str,
        target: str,
        outcome: str,
        detail: str = "",
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "origin": origin,
            "target": target,
            "outcome": outcome,
        }
        if detail:
            record["detail"] = detail

        self._audit_records.append(record)
        if len(self._audit_records) > self._max_audit_records:
            self._audit_records = self._audit_records[-self._max_audit_records :]

        logger.info(
            "control audit actor=%s origin=%s target=%s outcome=%s detail=%s",
            actor,
            origin,
            target,
            outcome,
            detail,
        )
