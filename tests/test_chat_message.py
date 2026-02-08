"""Tests for ChatMessage event parsing from RCON chat packets."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.events.types import ChatMessage
from squadpy.server import _CHAT_RE, SquadPyServer


class TestChatRegex:
    def test_chat_all(self):
        body = "[ChatAll] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] PlayerName : hello world"
        m = _CHAT_RE.match(body)
        assert m is not None
        assert m.group("channel") == "ChatAll"
        assert m.group("name") == "PlayerName"
        assert m.group("message") == "hello world"

    def test_chat_team(self):
        body = "[ChatTeam] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] SomeDude : team msg"
        m = _CHAT_RE.match(body)
        assert m is not None
        assert m.group("channel") == "ChatTeam"

    def test_chat_squad(self):
        body = "[ChatSquad] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] SquadPlayer : squad msg"
        m = _CHAT_RE.match(body)
        assert m is not None
        assert m.group("channel") == "ChatSquad"

    def test_chat_admin(self):
        body = "[ChatAdmin] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] Admin : admin msg"
        m = _CHAT_RE.match(body)
        assert m is not None
        assert m.group("channel") == "ChatAdmin"

    def test_special_chars_in_name(self):
        body = "[ChatAll] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] [CLAN] Player (TH) : hi"
        m = _CHAT_RE.match(body)
        assert m is not None
        assert m.group("name") == "[CLAN] Player (TH)"

    def test_empty_message(self):
        body = "[ChatAll] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] Player : "
        m = _CHAT_RE.match(body)
        assert m is not None
        assert m.group("message") == ""

    def test_non_chat_packet_no_match(self):
        """Admin cam, warn, kick messages don't match."""
        bodies = [
            "Admin has possessed admin camera.",
            "[Online IDs:EOS: abc123 steam: 12345678901234567] Player has been warned.",
            "Some random RCON message",
        ]
        for body in bodies:
            assert _CHAT_RE.match(body) is None

    def test_ids_parsed(self):
        body = "[ChatAll] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] Player : msg"
        m = _CHAT_RE.match(body)
        assert m is not None
        ids_raw = m.group("ids")
        assert "000249f6e3454b2cae8e993a96838faa" in ids_raw
        assert "76561199202672950" in ids_raw


class TestHandleChatEmitsEvent:
    @pytest.fixture
    def server(self):
        """Create a minimal server with mocked config for chat testing."""
        with patch("squadpy.server.setup_logging"):
            mock_config = MagicMock()
            mock_logging = MagicMock()
            srv = SquadPyServer(
                server_config=mock_config,
                logging_config=mock_logging,
                base_dir=MagicMock(),
            )
        return srv

    async def test_chat_message_emitted(self, server):
        """Valid chat body emits ChatMessage event."""
        received = []

        async def handler(event):
            received.append(event)

        server._event_bus.subscribe("chat_message", handler)

        body = "[ChatAll] [Online IDs:EOS: 000249f6e3454b2cae8e993a96838faa steam: 76561199202672950] TestPlayer : hello"
        server._handle_chat(body)

        # Give the event loop a tick to process the created task
        await asyncio.sleep(0.05)

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, ChatMessage)
        assert event.player_name == "TestPlayer"
        assert event.steam_id == "76561199202672950"
        assert event.eos_id == "000249f6e3454b2cae8e993a96838faa"
        assert event.channel == "ChatAll"
        assert event.message == "hello"

    async def test_non_chat_body_no_emit(self, server):
        """Non-matching body doesn't emit."""
        received = []

        async def handler(event):
            received.append(event)

        server._event_bus.subscribe("chat_message", handler)
        server._handle_chat("Admin has possessed admin camera.")
        await asyncio.sleep(0.05)
        assert len(received) == 0

    async def test_chat_admin_channel(self, server):
        """ChatAdmin channel parsed correctly."""
        received = []

        async def handler(event):
            received.append(event)

        server._event_bus.subscribe("chat_message", handler)
        body = "[ChatAdmin] [Online IDs:EOS: aabbccdd11224455aabbccdd11224455 steam: 76561198000000001] AdminGuy : test admin"
        server._handle_chat(body)
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0].channel == "ChatAdmin"
