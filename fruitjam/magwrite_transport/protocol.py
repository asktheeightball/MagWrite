"""Fruit Jam copy of the fixed wire constants and encoder."""

MAGIC = b"MW"
VERSION = 1
BYTE_ORDER = "big"
HEADER_SIZE = 14
CRC_SIZE = 4
# Mirrors magtag/magwrite/uart_protocol.py, which carries the reasoning; a host
# test asserts the two agree. Raised from 192/512 for the 48-column panel the
# built-in font fits.
MAX_PAYLOAD_SIZE = 384
MAX_FRAME_SIZE = HEADER_SIZE + MAX_PAYLOAD_SIZE + CRC_SIZE
MAX_RECEIVE_BUFFER = 1024
HELLO = 1
VIEWPORT = 2
END_OF_SCENARIO = 3
END_OF_TEST = 4
STATUS_HELLO = 5
FRAME_ACCEPTED = 6
REFRESH_STARTED = 7
REFRESH_COMPLETED = 8
DISPLAY_CAUGHT_UP = 9
FRAME_REJECTED = 10
DISPLAY_ERROR = 11
TEST_COMPLETE = 12
# V1.5. The return channel's first message that is not about the display. It
# rides the identical frame, version, CRC-32, and sequence numbering as every
# acknowledgement, which is the whole reason buttons needed no second transport:
# a button frame is duplicate-suppressed and gap-detected by the machinery the
# acknowledgements already proved.
BUTTON_EVENT = 13
MESSAGE_TYPES = (
    HELLO, VIEWPORT, END_OF_SCENARIO, END_OF_TEST,
    STATUS_HELLO, FRAME_ACCEPTED, REFRESH_STARTED, REFRESH_COMPLETED,
    DISPLAY_CAUGHT_UP, FRAME_REJECTED, DISPLAY_ERROR, TEST_COMPLETE,
    BUTTON_EVENT,
)
MESSAGE_NAMES = {
    HELLO: "HELLO", VIEWPORT: "VIEWPORT",
    END_OF_SCENARIO: "END_OF_SCENARIO", END_OF_TEST: "END_OF_TEST",
    STATUS_HELLO: "STATUS_HELLO", FRAME_ACCEPTED: "FRAME_ACCEPTED",
    REFRESH_STARTED: "REFRESH_STARTED", REFRESH_COMPLETED: "REFRESH_COMPLETED",
    DISPLAY_CAUGHT_UP: "DISPLAY_CAUGHT_UP", FRAME_REJECTED: "FRAME_REJECTED",
    DISPLAY_ERROR: "DISPLAY_ERROR", TEST_COMPLETE: "TEST_COMPLETE",
    BUTTON_EVENT: "BUTTON_EVENT",
}


def crc32(data):
    value = 0xFFFFFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
    return value ^ 0xFFFFFFFF


def encode_frame(message_type, sequence, revision, payload=b""):
    if message_type not in MESSAGE_TYPES:
        raise ValueError("unknown message type")
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError("payload exceeds maximum")
    header = (
        MAGIC + bytes((VERSION, message_type))
        + int(sequence).to_bytes(4, BYTE_ORDER)
        + int(revision).to_bytes(4, BYTE_ORDER)
        + len(payload).to_bytes(2, BYTE_ORDER)
    )
    body = header + payload
    return body + crc32(body).to_bytes(4, BYTE_ORDER)


class Frame:
    def __init__(self, message_type, sequence, revision, payload):
        self.message_type = message_type
        self.sequence = sequence
        self.revision = revision
        self.payload = payload


class FrameParser:
    def __init__(self):
        self.buffer = bytearray()
        self.rejected = 0
        self.crc_failures = 0
        self.oversized = 0
        self.version_failures = 0
        self.type_failures = 0
        self.buffer_overflows = 0
        self.bytes_discarded_before_magic = 0
        self.resynchronization_events = 0
        self.maximum_discarded_prefix = 0

    def _discard_prefix(self, count):
        if count <= 0:
            return
        self.bytes_discarded_before_magic += count
        self.resynchronization_events += 1
        self.maximum_discarded_prefix = max(self.maximum_discarded_prefix, count)
        self.buffer = self.buffer[count:]

    def feed(self, data):
        if len(data) > MAX_RECEIVE_BUFFER:
            data = data[-MAX_RECEIVE_BUFFER:]
            self.buffer_overflows += 1
        self.buffer.extend(data)
        if len(self.buffer) > MAX_RECEIVE_BUFFER:
            self.buffer = self.buffer[-MAX_RECEIVE_BUFFER:]
            self.buffer_overflows += 1

    def _reject_prefix(self, reason):
        self.rejected += 1
        setattr(self, reason, getattr(self, reason) + 1)
        self._discard_prefix(1)

    def pop(self):
        while True:
            at = self.buffer.find(MAGIC)
            if at < 0:
                if self.buffer[-1:] == MAGIC[:1]:
                    self._discard_prefix(len(self.buffer) - 1)
                    self.buffer = bytearray(MAGIC[:1])
                else:
                    self._discard_prefix(len(self.buffer))
                    self.buffer = bytearray()
                return None
            if at:
                self._discard_prefix(at)
            if len(self.buffer) < HEADER_SIZE:
                return None
            version = self.buffer[2]
            message_type = self.buffer[3]
            payload_size = int.from_bytes(self.buffer[12:14], BYTE_ORDER)
            if payload_size > MAX_PAYLOAD_SIZE:
                self._reject_prefix("oversized")
                continue
            total = HEADER_SIZE + payload_size + CRC_SIZE
            if len(self.buffer) < total:
                return None
            if version != VERSION:
                self._reject_prefix("version_failures")
                continue
            if message_type not in MESSAGE_TYPES:
                self._reject_prefix("type_failures")
                continue
            candidate = bytes(self.buffer[:total])
            expected = int.from_bytes(candidate[-4:], BYTE_ORDER)
            if crc32(candidate[:-4]) != expected:
                self._reject_prefix("crc_failures")
                continue
            self.buffer = self.buffer[total:]
            return Frame(
                message_type,
                int.from_bytes(candidate[4:8], BYTE_ORDER),
                int.from_bytes(candidate[8:12], BYTE_ORDER),
                candidate[14:-4],
            )
