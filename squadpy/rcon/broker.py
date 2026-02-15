"""RCON broker mode: one upstream client, many authenticated local clients."""

from datetime import datetime, timezone
from typing import Callable

from squadpy.rcon.client import RconClient


class RconBrokerError(Exception):
    """Base broker exception."""


class RconBrokerAuthenticationError(RconBrokerError):
    """Raised when a broker client token is not recognized."""


class RconBrokerAuthorizationError(RconBrokerError):
    """Raised when a client is authenticated but not authorized for a command."""


class RconBroker:
    """Broker that multiplexes authenticated local clients over one upstream RCON client."""

    def __init__(
        self,
        upstream: RconClient,
        *,
        clients: dict[str, str] | None = None,
        policy: Callable[[str, str], bool] | None = None,
        max_audit_records: int = 1000,
    ):
        self._upstream = upstream
        self._policy = policy
        self._client_tokens: dict[str, str] = {}
        self._token_to_client: dict[str, str] = {}
        self._audit_records: list[dict[str, str]] = []
        self._max_audit_records = max(1, int(max_audit_records))

        for client_id, token in (clients or {}).items():
            self.register_client(client_id, token)

    @property
    def upstream(self) -> RconClient:
        return self._upstream

    def register_client(self, client_id: str, token: str) -> None:
        normalized_client_id = str(client_id).strip()
        normalized_token = str(token).strip()
        if not normalized_client_id:
            raise ValueError("client_id must be non-empty")
        if not normalized_token:
            raise ValueError("token must be non-empty")

        existing_client = self._token_to_client.get(normalized_token)
        if existing_client and existing_client != normalized_client_id:
            raise ValueError("token is already assigned to a different client")

        previous_token = self._client_tokens.get(normalized_client_id)
        if previous_token and previous_token != normalized_token:
            self._token_to_client.pop(previous_token, None)

        self._client_tokens[normalized_client_id] = normalized_token
        self._token_to_client[normalized_token] = normalized_client_id

    def remove_client(self, client_id: str) -> None:
        normalized_client_id = str(client_id).strip()
        token = self._client_tokens.pop(normalized_client_id, None)
        if token:
            self._token_to_client.pop(token, None)

    def authenticate(self, token: str) -> str:
        normalized_token = str(token).strip()
        client_id = self._token_to_client.get(normalized_token)
        if client_id is None:
            raise RconBrokerAuthenticationError("Invalid broker client token")
        return client_id

    async def execute(
        self,
        *,
        token: str,
        command: str,
        origin: str = "broker",
    ) -> str:
        client_id = self.authenticate(token)
        return await self.execute_for_client(
            client_id=client_id,
            command=command,
            origin=origin,
        )

    async def execute_for_client(
        self,
        *,
        client_id: str,
        command: str,
        origin: str = "broker",
    ) -> str:
        normalized_client_id = str(client_id).strip()
        normalized_command = str(command).strip()
        if not normalized_client_id:
            raise ValueError("client_id must be non-empty")
        if not normalized_command:
            raise ValueError("command must be non-empty")

        if normalized_client_id not in self._client_tokens:
            self._audit(
                client_id=normalized_client_id,
                origin=origin,
                target=normalized_command,
                outcome="rejected",
                detail="unknown client",
            )
            raise RconBrokerAuthenticationError("Unknown broker client")

        if self._policy and not self._policy(normalized_client_id, normalized_command):
            self._audit(
                client_id=normalized_client_id,
                origin=origin,
                target=normalized_command,
                outcome="rejected",
                detail="unauthorized",
            )
            raise RconBrokerAuthorizationError("Broker command not authorized")

        try:
            response = await self._upstream.execute(normalized_command)
        except Exception as exc:
            self._audit(
                client_id=normalized_client_id,
                origin=origin,
                target=normalized_command,
                outcome="error",
                detail=str(exc),
            )
            raise

        self._audit(
            client_id=normalized_client_id,
            origin=origin,
            target=normalized_command,
            outcome="success",
        )
        return response

    def recent_audit_records(self) -> list[dict[str, str]]:
        return list(self._audit_records)

    def _audit(
        self,
        *,
        client_id: str,
        origin: str,
        target: str,
        outcome: str,
        detail: str = "",
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_id": client_id,
            "origin": origin,
            "target": target,
            "outcome": outcome,
        }
        if detail:
            record["detail"] = detail

        self._audit_records.append(record)
        if len(self._audit_records) > self._max_audit_records:
            self._audit_records = self._audit_records[-self._max_audit_records :]
