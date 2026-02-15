"""Authenticated websocket control service."""

from collections import Counter
import inspect
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiohttp import WSMsgType, web

from squadpy.observability import get_trace_recorder

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
        layer_catalog_service: Any = None,
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
        self._layer_catalog_service = layer_catalog_service
        self._server = server
        self._rcon = rcon
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._audit_records: list[dict[str, Any]] = []
        self._max_audit_records = 1000
        self._started_at_epoch: int | None = None

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
        self._started_at_epoch = self._epoch_seconds()
        logger.info("Websocket control service started at ws://%s:%d%s", self._host, self._port, self._path)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            self._started_at_epoch = None
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

        if action == "layers.query":
            if not self._is_allowed(role_name, "layers.query"):
                self._audit(
                    actor=actor or "unknown",
                    origin=origin,
                    target="layers.query",
                    outcome="rejected",
                    detail=f"forbidden role={role_name} permission=layers.query",
                )
                return ControlResponse(
                    ok=False,
                    error="Forbidden",
                    code="forbidden",
                    request_id=request_id,
                ).as_dict()

            query = payload.get("query", {})
            if not isinstance(query, dict):
                self._audit(
                    actor=actor or "unknown",
                    origin=origin,
                    target="layers.query",
                    outcome="rejected",
                    detail="invalid query payload",
                )
                return ControlResponse(
                    ok=False,
                    error="Invalid query payload",
                    code="invalid_request",
                    request_id=request_id,
                ).as_dict()

            result = self._run_layer_query(query)
            if result is None:
                self._audit(
                    actor=actor or "unknown",
                    origin=origin,
                    target="layers.query",
                    outcome="error",
                    detail="layer catalog unavailable",
                )
                return ControlResponse(
                    ok=False,
                    error="Layer catalog unavailable",
                    code="unavailable",
                    request_id=request_id,
                ).as_dict()

            self._audit(
                actor=actor or "unknown",
                origin=origin,
                target="layers.query",
                outcome="success",
            )
            return ControlResponse(
                ok=True,
                result=result,
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
        snapshot = self._build_dependency_snapshot()
        return await self._process_health_or_status(
            token=token,
            role=role,
            permission="control.health",
            result={
                "service": "control_api",
                "status": "ok" if snapshot["ready"] else "degraded",
                "ready": snapshot["ready"],
                "dependencies": snapshot["dependencies"],
            },
        )

    async def process_readiness(self, *, token: str | None) -> dict[str, Any]:
        return await self.process_readiness_with_role(token=token, role="")

    async def process_readiness_with_role(
        self,
        *,
        token: str | None,
        role: str = "",
    ) -> dict[str, Any]:
        authorized = await self._process_health_or_status(
            token=token,
            role=role,
            permission="control.readiness",
            result={},
        )
        if not bool(authorized.get("ok")):
            return authorized

        snapshot = self._build_dependency_snapshot()
        if snapshot["ready"]:
            return ControlResponse(
                ok=True,
                result={
                    "service": "control_api",
                    "status": "ready",
                    "ready": True,
                    "dependencies": snapshot["dependencies"],
                },
            ).as_dict()

        return ControlResponse(
            ok=False,
            error="Service not ready",
            code="unavailable",
            result={
                "service": "control_api",
                "status": "not_ready",
                "ready": False,
                "dependencies": snapshot["dependencies"],
            },
        ).as_dict()

    async def process_metrics(self, *, token: str | None) -> dict[str, Any]:
        return await self.process_metrics_with_role(token=token, role="")

    async def process_metrics_with_role(
        self,
        *,
        token: str | None,
        role: str = "",
    ) -> dict[str, Any]:
        authorized = await self._process_health_or_status(
            token=token,
            role=role,
            permission="control.metrics",
            result={},
        )
        if not bool(authorized.get("ok")):
            return authorized

        return ControlResponse(
            ok=True,
            result={"metrics": self._build_metrics_text()},
        ).as_dict()

    async def process_traces(self, *, token: str | None) -> dict[str, Any]:
        return await self.process_traces_with_role(token=token, role="")

    async def process_traces_with_role(
        self,
        *,
        token: str | None,
        role: str = "",
        name: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        authorized = await self._process_health_or_status(
            token=token,
            role=role,
            permission="control.traces",
            result={},
        )
        if not bool(authorized.get("ok")):
            return authorized

        trace_name = str(name).strip() or None
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError):
            parsed_limit = 100
        parsed_limit = max(1, min(parsed_limit, 500))
        recorder = get_trace_recorder()
        return ControlResponse(
            ok=True,
            result={
                "trace_name": trace_name or "all",
                "limit": parsed_limit,
                "summary": recorder.summary(name=trace_name),
                "spans": recorder.recent_spans(name=trace_name, limit=parsed_limit),
            },
        ).as_dict()

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
        snapshot = self._build_dependency_snapshot()
        response = {
            "service": "control_api",
            "rcon_connected": bool(rcon and getattr(rcon, "connected", False)),
            "server_running": bool(getattr(self._server, "running", False)) if self._server else False,
            "ready": snapshot["ready"],
            "dependencies": snapshot["dependencies"],
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

    async def process_layer_query(
        self,
        payload: dict[str, Any],
        *,
        token: str | None,
        origin: str = "rest",
        actor: str = "",
        role: str = "",
    ) -> dict[str, Any]:
        request_id = str(payload.get("request_id", "")).strip()
        query = payload.get("query", {})
        return await self.process_payload(
            {
                "request_id": request_id,
                "action": "layers.query",
                "query": query,
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

    async def _handle_traces(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        role = self._request_role(request)
        name = str(request.query.get("name", "")).strip()
        limit_raw = str(request.query.get("limit", "100")).strip()
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        response = await self.process_traces_with_role(
            token=token,
            role=role,
            name=name,
            limit=limit,
        )
        return web.json_response(response, status=self._http_status(response))

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        role = self._request_role(request)
        response = await self.process_metrics_with_role(token=token, role=role)
        status = self._http_status(response)
        headers = {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}
        if not bool(response.get("ok")):
            return web.Response(
                text=f"# metrics_error {response.get('code', 'internal_error')}\n",
                status=status,
                headers=headers,
            )
        metrics = str(response.get("result", {}).get("metrics", ""))
        return web.Response(text=metrics, status=status, headers=headers)

    async def _handle_readiness(self, request: web.Request) -> web.Response:
        token = self._request_token(request)
        role = self._request_role(request)
        response = await self.process_readiness_with_role(token=token, role=role)
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

    async def _handle_layer_query(self, request: web.Request) -> web.Response:
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
        response = await self.process_layer_query(
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
        if "_rcon" not in vars(self._server):
            return None
        return getattr(self._server, "_rcon", None)

    def _resolve_layer_catalog_service(self):
        if self._layer_catalog_service is not None:
            return self._layer_catalog_service
        if self._server is None:
            return None
        if "_layers" not in vars(self._server):
            return None
        return getattr(self._server, "_layers", None)

    def _run_layer_query(self, query: dict[str, Any]) -> dict[str, Any] | None:
        layer_service = self._resolve_layer_catalog_service()
        if layer_service is None:
            return None

        catalog = getattr(layer_service, "catalog", None)
        if catalog is None:
            return None

        layer_name = str(query.get("layer", "")).strip()
        faction_name = str(query.get("faction", "")).strip()
        vehicle_class = str(query.get("vehicle_class", "")).strip()
        include_catalog = bool(query.get("include_catalog", False))
        include_health = bool(query.get("include_health", True))

        source_url = str(
            getattr(catalog, "source_url", "")
            or getattr(layer_service, "source_url", "")
        ).strip()
        result: dict[str, Any] = {
            "source_url": source_url,
            "has_layer": catalog.has_layer(layer_name) if layer_name else None,
            "has_faction": catalog.has_faction(faction_name) if faction_name else None,
            "vehicle_names": sorted(catalog.vehicle_names(vehicle_class)) if vehicle_class else [],
            "helicopter_names": sorted(catalog.helicopter_names),
            "melee_weapons": sorted(set(catalog.melee_weapons)),
        }

        if include_catalog:
            result["layers"] = sorted(set(catalog.layers))
            result["factions"] = sorted(set(catalog.factions))
            result["vehicles_by_class"] = {
                vehicle_type: sorted(set(names))
                for vehicle_type, names in catalog.vehicles_by_class.items()
            }

        if include_health:
            health_fn = getattr(layer_service, "health", None)
            if callable(health_fn):
                health = health_fn()
                if hasattr(health, "as_dict"):
                    result["health"] = health.as_dict()
                elif isinstance(health, dict):
                    result["health"] = health
                else:
                    result["health"] = {"status": str(health)}

        return result

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get(self._path, self._handle_ws)
        app.router.add_get("/metrics", self._handle_metrics)
        app.router.add_get("/api/health", self._handle_health)
        app.router.add_get("/api/readiness", self._handle_readiness)
        app.router.add_get("/api/traces", self._handle_traces)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_post("/api/command", self._handle_command)
        app.router.add_post("/api/layers/query", self._handle_layer_query)
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

    def _build_dependency_snapshot(self) -> dict[str, Any]:
        dependencies: dict[str, dict[str, Any]] = {}
        required_health: list[bool] = []
        server = self._server

        def add_dependency(
            name: str,
            *,
            required: bool,
            healthy: bool,
            detail: str,
            extras: dict[str, Any] | None = None,
        ) -> None:
            entry: dict[str, Any] = {
                "required": required,
                "healthy": healthy,
                "detail": detail,
            }
            if extras:
                entry.update(extras)
            dependencies[name] = entry
            if required:
                required_health.append(healthy)

        server_required = server is not None
        server_running = bool(getattr(server, "running", False)) if server_required else True
        add_dependency(
            "server",
            required=server_required,
            healthy=server_running,
            detail="running" if server_running else "not running",
        )

        rcon = self._resolve_rcon()
        rcon_required = bool(server_required or rcon is not None)
        rcon_connected = bool(rcon and getattr(rcon, "connected", False))
        if not rcon_required:
            rcon_detail = "not attached"
        elif rcon is None:
            rcon_detail = "unavailable"
        else:
            rcon_detail = "connected" if rcon_connected else "disconnected"
        add_dependency(
            "rcon",
            required=rcon_required,
            healthy=rcon_connected if rcon_required else True,
            detail=rcon_detail,
        )

        server_config = getattr(server, "_server_config", None)
        discord_required = bool(
            server_config
            and getattr(getattr(server_config, "discord", None), "enabled", False)
        )
        discord = getattr(server, "_discord", None) if server is not None else None
        discord_running = bool(discord and getattr(discord, "running", False))
        add_dependency(
            "discord",
            required=discord_required,
            healthy=discord_running if discord_required else True,
            detail=(
                "running"
                if discord_running
                else ("not configured" if not discord_required else "not running")
            ),
        )

        db_config = getattr(server, "_db_config", None) if server is not None else None
        database_required = bool(db_config and getattr(db_config, "enabled", False))
        database = getattr(server, "_db", None) if server is not None else None
        database_ready = database is not None
        add_dependency(
            "database",
            required=database_required,
            healthy=database_ready if database_required else True,
            detail=(
                "initialized"
                if database_ready
                else ("not configured" if not database_required else "unavailable")
            ),
        )

        layer_service = self._resolve_layer_catalog_service()
        layer_health = self._layer_health_payload(layer_service)
        layer_status = str(layer_health.get("status", "unknown")).lower()
        add_dependency(
            "layers",
            required=False,
            healthy=layer_status in {"healthy", "ok"},
            detail=layer_status,
            extras={"health": layer_health},
        )

        ready = all(required_health) if required_health else True
        return {
            "ready": ready,
            "dependencies": dependencies,
        }

    def _build_metrics_text(self) -> str:
        snapshot = self._build_dependency_snapshot()
        dependencies = snapshot["dependencies"]
        server = self._server
        loaded_plugins = []
        periodic_tasks = []
        if server is not None:
            loaded_plugins = list(getattr(server, "_loaded_plugins", []))
            periodic_tasks = list(getattr(server, "_periodic_tasks", []))

        plugin_status_counts = Counter()
        plugin_status_rows: list[tuple[str, str]] = []
        for plugin in loaded_plugins:
            status_value = self._plugin_status_value(getattr(plugin, "status", "unknown"))
            plugin_name = str(
                getattr(plugin, "dir_name", "")
                or getattr(plugin, "name", "")
                or "unknown_plugin"
            )
            plugin_status_counts[status_value] += 1
            plugin_status_rows.append((plugin_name, status_value))

        now = self._epoch_seconds()
        uptime_seconds = 0
        if self._started_at_epoch is not None:
            uptime_seconds = max(0, now - self._started_at_epoch)

        lines: list[str] = []
        definitions: set[str] = set()

        def add_metric(
            name: str,
            value: int | float,
            *,
            labels: dict[str, str] | None = None,
            help_text: str,
            metric_type: str = "gauge",
        ) -> None:
            if name not in definitions:
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} {metric_type}")
                definitions.add(name)
            if labels:
                label_text = ",".join(
                    f'{key}="{self._escape_prometheus_label(labels[key])}"'
                    for key in sorted(labels)
                )
                lines.append(f"{name}{{{label_text}}} {value}")
            else:
                lines.append(f"{name} {value}")

        add_metric(
            "squadpy_runtime_ready",
            self._metric_bool(snapshot["ready"]),
            help_text="Overall readiness across required runtime dependencies.",
        )
        add_metric(
            "squadpy_runtime_server_running",
            self._metric_bool(dependencies["server"]["healthy"]),
            help_text="Server orchestrator running state.",
        )
        add_metric(
            "squadpy_runtime_rcon_connected",
            self._metric_bool(dependencies["rcon"]["healthy"]),
            help_text="RCON connectivity state.",
        )
        add_metric(
            "squadpy_runtime_discord_running",
            self._metric_bool(dependencies["discord"]["healthy"]),
            help_text="Discord connector running state.",
        )
        add_metric(
            "squadpy_runtime_database_initialized",
            self._metric_bool(dependencies["database"]["healthy"]),
            help_text="Database readiness state.",
        )
        add_metric(
            "squadpy_runtime_periodic_tasks_active",
            len(periodic_tasks),
            help_text="Number of active plugin periodic tasks.",
        )
        add_metric(
            "squadpy_runtime_plugins_loaded",
            len(loaded_plugins),
            help_text="Number of plugins discovered by the runtime.",
        )
        add_metric(
            "squadpy_api_uptime_seconds",
            uptime_seconds,
            help_text="Control API uptime in seconds.",
        )

        for dependency_name, dependency in dependencies.items():
            labels = {"dependency": dependency_name}
            add_metric(
                "squadpy_dependency_required",
                self._metric_bool(dependency["required"]),
                labels=labels,
                help_text="Dependency is required for readiness (1=yes).",
            )
            add_metric(
                "squadpy_dependency_healthy",
                self._metric_bool(dependency["healthy"]),
                labels=labels,
                help_text="Dependency health state (1=healthy).",
            )

        for status_name in sorted(plugin_status_counts):
            add_metric(
                "squadpy_plugins_total",
                plugin_status_counts[status_name],
                labels={"status": status_name},
                help_text="Plugin count by lifecycle status.",
            )
        for plugin_name, status_name in sorted(plugin_status_rows):
            add_metric(
                "squadpy_plugin_status",
                1,
                labels={"plugin": plugin_name, "status": status_name},
                help_text="Per-plugin lifecycle status exposure.",
            )

        return "\n".join(lines) + "\n"

    @staticmethod
    def _metric_bool(value: Any) -> int:
        return 1 if bool(value) else 0

    @staticmethod
    def _plugin_status_value(status: Any) -> str:
        raw = getattr(status, "value", status)
        normalized = str(raw).strip().lower()
        if normalized.startswith("pluginstatus."):
            normalized = normalized.split(".", 1)[1]
        return normalized or "unknown"

    @staticmethod
    def _escape_prometheus_label(value: str) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace('"', '\\"')
        )

    @staticmethod
    def _layer_health_payload(layer_service: Any) -> dict[str, Any]:
        if layer_service is None:
            return {"status": "unavailable"}

        health_fn = getattr(layer_service, "health", None)
        if not callable(health_fn):
            return {"status": "unavailable"}
        if inspect.iscoroutinefunction(health_fn):
            return {"status": "unknown"}

        health = health_fn()
        if inspect.isawaitable(health):
            if hasattr(health, "close"):
                health.close()
            return {"status": "unknown"}
        if hasattr(health, "as_dict"):
            return health.as_dict()
        if isinstance(health, dict):
            return health
        return {"status": str(health)}

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
