"""Bounded payloads for MagTag-to-Fruit Jam status frames."""

from magwrite.uart_protocol import (
    DISPLAY_CAUGHT_UP,
    DISPLAY_ERROR,
    FRAME_ACCEPTED,
    FRAME_REJECTED,
    REFRESH_COMPLETED,
    REFRESH_STARTED,
    STATUS_HELLO,
    TEST_COMPLETE,
)

MAX_REASON = 32
MAX_TEST_ID = 24
FULL_REFRESH = 1
PARTIAL_REFRESH = 0


def _u16(value):
    if not 0 <= value <= 0xFFFF:
        raise ValueError("u16 out of range")
    return int(value).to_bytes(2, "big")


def _u32(value):
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("u32 out of range")
    return int(value).to_bytes(4, "big")


def _text(value, limit):
    try:
        data = value.encode("ascii")
    except UnicodeError:
        raise ValueError("status text must be ASCII")
    if len(data) > limit:
        raise ValueError("status text exceeds maximum")
    return bytes((len(data),)) + data


def encode_status(message_type, fields):
    if message_type == STATUS_HELLO:
        flags = (1 if fields["receiver_ready"] else 0) | (
            2 if fields["display_ready"] else 0
        )
        return (
            bytes((fields["protocol_version"], fields["app_version"]))
            + _u32(fields["displayed_revision"])
            + bytes((flags,))
            + _text(fields["test_id"], MAX_TEST_ID)
        )
    if message_type == FRAME_ACCEPTED:
        return (
            _u32(fields["received_sequence"])
            + _u32(fields["pending_revision"])
            + bytes((1 if fields["superseded"] else 0,))
        )
    if message_type == REFRESH_STARTED:
        return (
            _u32(fields["viewport_sequence"])
            + bytes((fields["refresh_mode"],))
            + _u32(fields["latest_received_revision"])
            + _u32(fields["previous_displayed_revision"])
        )
    if message_type == REFRESH_COMPLETED:
        return (
            _u32(fields["viewport_sequence"])
            + _u32(fields["duration_ms"])
            + _u32(fields["latest_received_revision"])
            + bytes((1 if fields["stale"] else 0,))
        )
    if message_type == DISPLAY_CAUGHT_UP:
        return (
            _u32(fields["displayed_revision"])
            + _u32(fields["latest_received_revision"])
            + _u32(fields["viewport_hash"])
        )
    if message_type == FRAME_REJECTED:
        return (
            _u32(fields["received_sequence"])
            + _u32(fields["received_revision"])
            + bytes((fields["code"],))
            + _u32(fields["displayed_revision"])
            + _text(fields["reason"], MAX_REASON)
        )
    if message_type == DISPLAY_ERROR:
        return (
            bytes((fields["code"],))
            + _u32(fields["inflight_revision"])
            + _u32(fields["latest_received_revision"])
            + _u32(fields["displayed_revision"])
            + _text(fields["reason"], MAX_REASON)
        )
    if message_type == TEST_COMPLETE:
        return (
            _u32(fields["displayed_revision"])
            + _u32(fields["viewport_hash"])
            + _u16(fields["accepted_count"])
            + _u16(fields["rendered_count"])
            + _u16(fields["superseded_count"])
            + _u16(fields["refresh_count"])
            + _u16(fields["error_count"])
        )
    raise ValueError("not a status message type")


def _require(payload, size):
    if len(payload) != size:
        raise ValueError("malformed status payload")


def _read_text(payload, at, limit):
    if at >= len(payload):
        raise ValueError("malformed status text")
    size = payload[at]
    if size > limit or at + 1 + size != len(payload):
        raise ValueError("malformed status text")
    try:
        return payload[at + 1 :].decode("ascii")
    except UnicodeError:
        raise ValueError("malformed status text")


def decode_status(message_type, payload):
    if message_type == STATUS_HELLO:
        if len(payload) < 8:
            raise ValueError("malformed STATUS_HELLO")
        flags = payload[6]
        return {
            "protocol_version": payload[0],
            "app_version": payload[1],
            "displayed_revision": int.from_bytes(payload[2:6], "big"),
            "receiver_ready": bool(flags & 1),
            "display_ready": bool(flags & 2),
            "test_id": _read_text(payload, 7, MAX_TEST_ID),
        }
    if message_type == FRAME_ACCEPTED:
        _require(payload, 9)
        return {
            "received_sequence": int.from_bytes(payload[0:4], "big"),
            "pending_revision": int.from_bytes(payload[4:8], "big"),
            "superseded": bool(payload[8]),
        }
    if message_type == REFRESH_STARTED:
        _require(payload, 13)
        return {
            "viewport_sequence": int.from_bytes(payload[0:4], "big"),
            "refresh_mode": payload[4],
            "latest_received_revision": int.from_bytes(payload[5:9], "big"),
            "previous_displayed_revision": int.from_bytes(payload[9:13], "big"),
        }
    if message_type == REFRESH_COMPLETED:
        _require(payload, 13)
        return {
            "viewport_sequence": int.from_bytes(payload[0:4], "big"),
            "duration_ms": int.from_bytes(payload[4:8], "big"),
            "latest_received_revision": int.from_bytes(payload[8:12], "big"),
            "stale": bool(payload[12]),
        }
    if message_type == DISPLAY_CAUGHT_UP:
        _require(payload, 12)
        return {
            "displayed_revision": int.from_bytes(payload[0:4], "big"),
            "latest_received_revision": int.from_bytes(payload[4:8], "big"),
            "viewport_hash": int.from_bytes(payload[8:12], "big"),
        }
    if message_type == FRAME_REJECTED:
        if len(payload) < 14:
            raise ValueError("malformed FRAME_REJECTED")
        return {
            "received_sequence": int.from_bytes(payload[0:4], "big"),
            "received_revision": int.from_bytes(payload[4:8], "big"),
            "code": payload[8],
            "displayed_revision": int.from_bytes(payload[9:13], "big"),
            "reason": _read_text(payload, 13, MAX_REASON),
        }
    if message_type == DISPLAY_ERROR:
        if len(payload) < 14:
            raise ValueError("malformed DISPLAY_ERROR")
        return {
            "code": payload[0],
            "inflight_revision": int.from_bytes(payload[1:5], "big"),
            "latest_received_revision": int.from_bytes(payload[5:9], "big"),
            "displayed_revision": int.from_bytes(payload[9:13], "big"),
            "reason": _read_text(payload, 13, MAX_REASON),
        }
    if message_type == TEST_COMPLETE:
        _require(payload, 18)
        return {
            "displayed_revision": int.from_bytes(payload[0:4], "big"),
            "viewport_hash": int.from_bytes(payload[4:8], "big"),
            "accepted_count": int.from_bytes(payload[8:10], "big"),
            "rendered_count": int.from_bytes(payload[10:12], "big"),
            "superseded_count": int.from_bytes(payload[12:14], "big"),
            "refresh_count": int.from_bytes(payload[14:16], "big"),
            "error_count": int.from_bytes(payload[16:18], "big"),
        }
    raise ValueError("not a status message type")
