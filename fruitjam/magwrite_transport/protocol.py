"""Fruit Jam copy of the fixed wire constants and encoder."""

MAGIC = b"MW"
VERSION = 1
BYTE_ORDER = "big"
HEADER_SIZE = 14
CRC_SIZE = 4
MAX_PAYLOAD_SIZE = 192
MAX_FRAME_SIZE = HEADER_SIZE + MAX_PAYLOAD_SIZE + CRC_SIZE
MAX_RECEIVE_BUFFER = 512
HELLO = 1
VIEWPORT = 2
END_OF_SCENARIO = 3
END_OF_TEST = 4
MESSAGE_TYPES = (HELLO, VIEWPORT, END_OF_SCENARIO, END_OF_TEST)


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
