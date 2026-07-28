"""Bounded non-blocking status-frame outbox."""

from magwrite.status_message import encode_status
from magwrite.uart_protocol import encode_frame


class StatusQueueOverflow(Exception):
    pass


class StatusQueue:
    def __init__(self, capacity=32):
        if capacity <= 0:
            raise ValueError("status queue capacity must be positive")
        self.capacity = capacity
        self.items = []
        self.next_sequence = 1
        self.maximum_depth = 0
        self.frames_sent = 0

    def offer(self, message_type, revision, fields):
        if len(self.items) >= self.capacity:
            raise StatusQueueOverflow("status queue overflow")
        sequence = self.next_sequence
        self.next_sequence += 1
        payload = encode_status(message_type, fields)
        self.items.append(
            (message_type, sequence, revision,
             encode_frame(message_type, sequence, revision, payload))
        )
        self.maximum_depth = max(self.maximum_depth, len(self.items))
        return sequence

    def pop(self):
        if not self.items:
            return None
        item = self.items.pop(0)
        self.frames_sent += 1
        return item

    def __len__(self):
        return len(self.items)
