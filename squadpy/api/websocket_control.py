"""Authenticated websocket control service."""

import hashlib
import hmac
import json
import logging
import time
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
        rbac_enabled: bool = False,
        rbac_default_role: str = "admin",
        rbac_role_permissions: dict[str, list[str]] | None = None,
        webhook_signing_enabled: bool = False,
        webhook_signing_secret: str = "",
        webhook_signature_header: str = "X-SquadPy-Signature",
        webhook_timestamp_header: str = "X-SquadPy-Timestamp",
        webhook_max_age_seconds: int = 300,
        server: Any = None,
        rcon: Any = None,
    ):
        self._token = token
        self._host = host
        self._port = port
        self._path = path
        self._rbac_enabled = bool(rbac_enabled)
        self._rbac_default_role = self._normalize_role(rbac_default_role) or "admin"
        self._rbac_role_permissions = self._build_rbac_permissions(rbac_role_permissions)
        self._webhook_signing_enabled = bool(webhook_signing_enabled)
        self._webhook_signing_secret = str(webhook_signing_secret)
        self._webhook_signature_header = str(webhook_signature_header)
        self._webhook_timestamp_header = str(webhook_timestamp_header)
        self._webhook_max_age_seconds = max(1, int(webhook_max_age_seconds))
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
        role: str = "",
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

        role_name = self._effective_role(role)
        action = str(payload.get("action", "")).strip().lower()
        if action == "rcon.execute":
            if not self._is_allowed(role_name, "rcon.execute"):
                self._audit(
                    actor=actor or "unknown",
                    origin=origin,
                    target="rcon.execute",
                    outcome="rejected",
                    detail=f"forbidden role={role_name} permission=rcon.execute",
                )
                return ControlResponse(
                    ok=False,
                    error="Forbidden",
                    code="forbidden",
                    request_id=request_id,
                ).as_dict()

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
        return await self.process_health_with_role(token=token, role="")

    async def process_health_with_role(
        self,
        *,
        token: str | None,
        role: str = "",
    ) -> dict[str, Any]:
        return await self._process_health_or_status(
            token=token,
            role=role,
            permission="control.health",
            result={"status": "ok"},
        )

    async def process_status(self, *, token: str | None) -> dict[str, Any]:
        return await self.process_status_with_role(token=token, role="")

    async def process_status_with_role(
        self,
        *,
        token: str | None,
        role: str = "",
    ) -> dict[str, Any]:
        if not self._is_authorized(token):
            return ControlResponse(
                ok=False,
                error="Unauthorized",
                code="unauthorized",
            ).as_dict()

        role_name = self._effective_role(role)
        if not self._is_allowed(role_name, "control.status"):
            return ControlResponse(
                ok=False,
                error="Forbidden",
                code="forbidden",
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
        role: str = "",
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
            role=role,
        )

    async def process_webhook_command(
        self,
        payload: dict[str, Any],
        *,
        raw_body: str,
        signature: str,
        timestamp: str,
        actor: str = "",
        role: str = "",
    ) -> dict[str, Any]:
        request_id = str(payload.get("request_id", "")).strip()
        if not self._webhook_signing_enabled:
            return ControlResponse(
                ok=False,
                error="Webhook signing policy is disabled",
                code="unavailable",
                request_id=request_id,
            ).as_dict()

        valid, detail = self._validate_webhook_signature(
            raw_body=raw_body,
            signature=signature,
            timestamp=timestamp,
        )
        if not valid:
            self._audit(
                actor=actor or "webhook_client",
                origin="webhook",
                target="webhook.command",
                outcome="rejected",
                detail=detail or "invalid_signature",
            )
            return ControlResponse(
                ok=False,
                error="Invalid signature",
                code="invalid_signature",
                request_id=request_id,
            ).as_dict()

        return await self.process_command(
            payload,
            token=self._token,
            origin="webhook",
            actor=actor or "webhook_client",
            role=role,
        )

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        session_token = self._request_token(request)
        session_role = self._request_role(request)

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
                        role = str(payload.get("role", "")).strip() or session_role
                        response = await self.process_payload(
                            payload,
                            token=request_token,
                            origin="websocket",
                            actor=actor or "websocket_client",
                            role=role,
                        )

                await ws.send_json(response)
                continue

            if msg.type == WSMsgType.ERROR:
                logger.warning("Websocket connection error: %s", ws.exception())
                break

        return ws

    async def _handle_health(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        role = self._request_role(request)
        response = await self.process_health_with_role(token=token, role=role)
        return web.json_response(response, status=self._http_status(response))

    async def _handle_status(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        role = self._request_role(request)
        response = await self.process_status_with_role(token=token, role=role)
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
        role = str(payload.get("role", "")).strip() or self._request_role(request)
        response = await self.process_command(
            payload,
            token=request_token,
            origin="rest",
            actor=actor,
            role=role,
        )
        return web.json_response(response, status=self._http_status(response))

    async def _handle_webhook_command(self, request: web.Request) -> web.Response:
        raw_body = await request.text()
        try:
            payload = json.loads(raw_body)
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

        signature = str(request.headers.get(self._webhook_signature_header, "")).strip()
        timestamp = str(request.headers.get(self._webhook_timestamp_header, "")).strip()
        actor = str(payload.get("actor", "")).strip() or "webhook_client"
        role = str(payload.get("role", "")).strip() or self._request_role(request)

        response = await self.process_webhook_command(
            payload,
            raw_body=raw_body,
            signature=signature,
            timestamp=timestamp,
            actor=actor,
            role=role,
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

    def _request_role(self, request: web.Request) -> str:
        header_role = request.headers.get("X-SquadPy-Role")
        if header_role:
            return str(header_role).strip()

        query_role = request.query.get("role")
        if query_role:
            return str(query_role).strip()
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
        app.router.add_post("/api/webhook/command", self._handle_webhook_command)
        return app

    def _http_status(self, response: dict[str, Any]) -> int:
        if bool(response.get("ok")):
            return 200
        code = str(response.get("code", ""))
        if code == "unauthorized":
            return 401
        if code == "invalid_signature":
            return 401
        if code == "forbidden":
            return 403
        if code in {"invalid_json", "invalid_request", "unknown_action"}:
            return 400
        if code == "unavailable":
            return 503
        return 500

    async def _process_health_or_status(
        self,
        *,
        token: str | None,
        role: str,
        permission: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._is_authorized(token):
            return ControlResponse(
                ok=False,
                error="Unauthorized",
                code="unauthorized",
            ).as_dict()

        role_name = self._effective_role(role)
        if not self._is_allowed(role_name, permission):
            return ControlResponse(
                ok=False,
                error="Forbidden",
                code="forbidden",
            ).as_dict()

        return ControlResponse(
            ok=True,
            result=result,
        ).as_dict()

    def _build_rbac_permissions(
        self,
        configured: dict[str, list[str]] | None,
    ) -> dict[str, set[str]]:
        if not configured:
            configured = {self._rbac_default_role: ["*"]}

        normalized: dict[str, set[str]] = {}
        for role, permissions in configured.items():
            role_name = self._normalize_role(role)
            if not role_name:
                continue
            normalized[role_name] = {
                str(permission).strip().lower()
                for permission in permissions
                if str(permission).strip()
            }
        if not normalized:
            normalized = {self._rbac_default_role: {"*"}}
        return normalized

    def _effective_role(self, role: str) -> str:
        normalized = self._normalize_role(role)
        if normalized:
            return normalized
        return self._rbac_default_role

    def _is_allowed(self, role: str, permission: str) -> bool:
        if not self._rbac_enabled:
            return True

        permissions = self._rbac_role_permissions.get(self._normalize_role(role), set())
        target = permission.strip().lower()
        if "*" in permissions or target in permissions:
            return True
        return any(
            wildcard.endswith(".*") and target.startswith(wildcard[:-1])
            for wildcard in permissions
        )

    @staticmethod
    def _normalize_role(role: str) -> str:
        return str(role).strip().lower()

    def _validate_webhook_signature(
        self,
        *,
        raw_body: str,
        signature: str,
        timestamp: str,
    ) -> tuple[bool, str]:
        if not signature:
            return False, "missing signature"
        if not timestamp:
            return False, "missing timestamp"
        if not self._webhook_signing_secret:
            return False, "missing signing secret"

        try:
            timestamp_value = int(timestamp)
        except (TypeError, ValueError):
            return False, "invalid timestamp"

        now = self._epoch_seconds()
        age = abs(now - timestamp_value)
        if age > self._webhook_max_age_seconds:
            return False, "stale timestamp"

        payload = f"{timestamp}.{raw_body}".encode("utf-8")
        expected = hmac.new(
            self._webhook_signing_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        provided = signature.strip()
        if provided.lower().startswith("sha256="):
            provided = provided[7:].strip()

        if not hmac.compare_digest(expected, provided):
            return False, "invalid signature"
        return True, ""

    @staticmethod
    def _epoch_seconds() -> int:
        return int(time.time())

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
