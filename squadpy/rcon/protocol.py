"""RCON packet encoding/decoding for Squad's UE4 RCON protocol.

Squad uses UE4's RCON module, not Valve's Source RCON. Key deviations:
- Packet type 0x01 (CHAT_VALUE) for unsolicited server messages
- 7-byte follow-response after multi-packet end markers
- Size field in follow-response packets is unreliable
"""

import struct
from dataclasses import dataclass
from enum import IntEnum

# UE4 RCON appends this after the empty end-of-multi-packet marker
FOLLOW_RESPONSE_BODY = b"\x00\x01\x00\x00\x00\x00\x00"

# Minimum packet: 4 (size) + 4 (id) + 4 (type) + 1 (body null) + 1 (terminator)
MIN_PACKET_SIZE = 14

# Header: size (4) + id (4) + type (4)
HEADER_SIZE = 12


class PacketType(IntEnum):
    RESPONSE_VALUE = 0
    CHAT_VALUE = 1         # Squad-specific: unsolicited server messages
    EXEC_COMMAND = 2
    AUTH_RESPONSE = 2      # Same value as EXEC_COMMAND, distinguished by context
    AUTH = 3


@dataclass
class RconPacket:
    id: int
    type: int
    body: str
    is_follow_response: bool = False


def encode_packet(packet_type: PacketType, packet_id: int, body: str) -> bytes:
    """Encode an RCON packet to bytes."""
    body_bytes = body.encode("utf-8")
    # size = id (4) + type (4) + body + null (1) + null (1)
    size = 4 + 4 + len(body_bytes) + 1 + 1
    return struct.pack(f"<iii{len(body_bytes)}scc",
                       size,
                       packet_id,
                       int(packet_type),
                       body_bytes,
                       b"\x00",
                       b"\x00")


def decode_packet(data: bytes) -> tuple[RconPacket, int] | None:
    """Decode one RCON packet from a byte buffer.

    Returns (packet, bytes_consumed) or None if the buffer doesn't
    contain a complete packet yet.
    """
    if len(data) < 4:
        return None

    size = struct.unpack_from("<i", data, 0)[0]
    total_length = size + 4  # size field itself is not included in size

    if len(data) < total_length:
        return None

    packet_id = struct.unpack_from("<i", data, 4)[0]
    packet_type = struct.unpack_from("<i", data, 8)[0]

    # Body is between header and the two null terminators
    body_length = size - 4 - 4 - 2  # minus id, type, two nulls
    body_bytes = data[HEADER_SIZE:HEADER_SIZE + body_length]
    body = body_bytes.decode("utf-8", errors="replace")

    # Check for UE4 follow-response: 7 extra bytes after an empty packet
    is_follow = False
    consumed = total_length
    if (body == "" and
            packet_type == PacketType.RESPONSE_VALUE and
            len(data) >= total_length + len(FOLLOW_RESPONSE_BODY)):
        trailing = data[total_length:total_length + len(FOLLOW_RESPONSE_BODY)]
        if trailing == FOLLOW_RESPONSE_BODY:
            is_follow = True
            consumed = total_length + len(FOLLOW_RESPONSE_BODY)

    return RconPacket(
        id=packet_id,
        type=packet_type,
        body=body,
        is_follow_response=is_follow,
    ), consumed
