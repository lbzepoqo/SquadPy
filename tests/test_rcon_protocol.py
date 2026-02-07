"""Tests for RCON packet encoding and decoding."""

import pytest

from squadpy.rcon.protocol import (
    RconPacket,
    PacketType,
    encode_packet,
    decode_packet,
    FOLLOW_RESPONSE_BODY,
)


class TestPacketType:
    def test_auth_type(self):
        assert PacketType.AUTH == 3

    def test_auth_response_type(self):
        assert PacketType.AUTH_RESPONSE == 2

    def test_exec_command_type(self):
        assert PacketType.EXEC_COMMAND == 2

    def test_response_value_type(self):
        assert PacketType.RESPONSE_VALUE == 0

    def test_chat_value_type(self):
        assert PacketType.CHAT_VALUE == 1


class TestEncodePacket:
    def test_encode_auth_packet(self):
        data = encode_packet(PacketType.AUTH, 1, "password123")
        body = b"password123"
        expected_size = 4 + 4 + len(body) + 1 + 1  # 21
        assert len(data) == expected_size + 4  # +4 for size field itself
        # Size field (little-endian)
        size = int.from_bytes(data[0:4], "little")
        assert size == expected_size
        # ID field
        pkt_id = int.from_bytes(data[4:8], "little")
        assert pkt_id == 1
        # Type field
        pkt_type = int.from_bytes(data[8:12], "little")
        assert pkt_type == PacketType.AUTH
        # Body
        assert data[12:12 + len(body)] == body
        # Null terminators
        assert data[-2:] == b"\x00\x00"

    def test_encode_empty_body(self):
        data = encode_packet(PacketType.EXEC_COMMAND, 5, "")
        size = int.from_bytes(data[0:4], "little")
        assert size == 10  # minimum: 4 + 4 + 1 + 1

    def test_encode_exec_command(self):
        data = encode_packet(PacketType.EXEC_COMMAND, 42, "ListPlayers")
        pkt_type = int.from_bytes(data[8:12], "little")
        assert pkt_type == PacketType.EXEC_COMMAND
        body_end = data.index(b"\x00", 12)
        assert data[12:body_end] == b"ListPlayers"


class TestDecodePacket:
    def test_decode_response_packet(self):
        raw = encode_packet(PacketType.RESPONSE_VALUE, 7, "OK")
        packet, consumed = decode_packet(raw)
        assert packet.id == 7
        assert packet.type == PacketType.RESPONSE_VALUE
        assert packet.body == "OK"
        assert consumed == len(raw)

    def test_decode_auth_response_success(self):
        raw = encode_packet(PacketType.AUTH_RESPONSE, 1, "")
        packet, consumed = decode_packet(raw)
        assert packet.id == 1
        assert packet.type == PacketType.AUTH_RESPONSE

    def test_decode_auth_response_failure(self):
        raw = encode_packet(PacketType.AUTH_RESPONSE, -1, "")
        packet, consumed = decode_packet(raw)
        assert packet.id == -1

    def test_decode_chat_packet(self):
        raw = encode_packet(PacketType.CHAT_VALUE, 0, "Player said hello")
        packet, consumed = decode_packet(raw)
        assert packet.type == PacketType.CHAT_VALUE
        assert packet.body == "Player said hello"

    def test_decode_incomplete_data_returns_none(self):
        raw = encode_packet(PacketType.RESPONSE_VALUE, 1, "test")
        result = decode_packet(raw[:5])  # truncated
        assert result is None

    def test_decode_only_size_field_returns_none(self):
        result = decode_packet(b"\x0a\x00\x00\x00")
        assert result is None

    def test_decode_empty_data_returns_none(self):
        result = decode_packet(b"")
        assert result is None

    def test_decode_follow_response(self):
        """UE4 RCON sends a 7-byte follow-response after multi-packet end markers.
        The size field lies (says 10, actual data is 21 bytes)."""
        empty_pkt = encode_packet(PacketType.RESPONSE_VALUE, 1, "")
        follow = empty_pkt + FOLLOW_RESPONSE_BODY
        packet, consumed = decode_packet(follow)
        assert packet.body == ""
        assert packet.is_follow_response is True
        assert consumed == len(follow)

    def test_decode_multiple_packets_in_buffer(self):
        pkt1 = encode_packet(PacketType.RESPONSE_VALUE, 1, "first")
        pkt2 = encode_packet(PacketType.RESPONSE_VALUE, 2, "second")
        buf = pkt1 + pkt2
        packet1, consumed1 = decode_packet(buf)
        assert packet1.body == "first"
        packet2, consumed2 = decode_packet(buf[consumed1:])
        assert packet2.body == "second"
