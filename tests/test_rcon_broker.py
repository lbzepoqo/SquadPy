"""Tests for RCON broker mode."""

from typing import cast
from unittest.mock import AsyncMock

import pytest

from squadpy.rcon.broker import (
    RconBroker,
    RconBrokerAuthenticationError,
    RconBrokerAuthorizationError,
)
from squadpy.rcon.client import RconClient


@pytest.fixture
def upstream() -> RconClient:
    client = cast(RconClient, AsyncMock(spec=RconClient))
    client.execute = AsyncMock()
    return client


class TestRconBroker:
    def test_authenticate_returns_client_id_for_valid_token(self, upstream: RconClient) -> None:
        broker = RconBroker(
            upstream,
            clients={"alpha": "token-alpha", "bravo": "token-bravo"},
        )

        assert broker.authenticate("token-alpha") == "alpha"
        assert broker.authenticate("token-bravo") == "bravo"

    def test_authenticate_rejects_unknown_token(self, upstream: RconClient) -> None:
        broker = RconBroker(upstream, clients={"alpha": "token-alpha"})

        with pytest.raises(RconBrokerAuthenticationError, match="Invalid broker client token"):
            broker.authenticate("token-unknown")

    async def test_execute_routes_many_clients_to_one_upstream(
        self,
        upstream: RconClient,
    ) -> None:
        upstream.execute = AsyncMock(side_effect=["players", "squads"])
        broker = RconBroker(
            upstream,
            clients={"alpha": "token-alpha", "bravo": "token-bravo"},
        )

        players = await broker.execute(token="token-alpha", command="ListPlayers")
        squads = await broker.execute(token="token-bravo", command="ListSquads")

        assert broker.upstream is upstream
        assert players == "players"
        assert squads == "squads"
        assert upstream.execute.await_count == 2
        assert [call.args[0] for call in upstream.execute.await_args_list] == [
            "ListPlayers",
            "ListSquads",
        ]

    async def test_execute_rejects_blank_command(self, upstream: RconClient) -> None:
        broker = RconBroker(upstream, clients={"alpha": "token-alpha"})

        with pytest.raises(ValueError, match="command must be non-empty"):
            await broker.execute(token="token-alpha", command="   ")

    async def test_policy_can_reject_command(self, upstream: RconClient) -> None:
        broker = RconBroker(
            upstream,
            clients={"alpha": "token-alpha"},
            policy=lambda client_id, command: client_id == "alpha" and command == "ListPlayers",
        )

        with pytest.raises(RconBrokerAuthorizationError, match="not authorized"):
            await broker.execute(token="token-alpha", command="AdminEndMatch")

        upstream.execute.assert_not_called()
        records = broker.recent_audit_records()
        assert records[-1]["client_id"] == "alpha"
        assert records[-1]["outcome"] == "rejected"
        assert records[-1]["detail"] == "unauthorized"

    def test_register_rejects_token_reuse_by_other_client(self, upstream: RconClient) -> None:
        broker = RconBroker(upstream, clients={"alpha": "token-alpha"})

        with pytest.raises(ValueError, match="already assigned"):
            broker.register_client("bravo", "token-alpha")
