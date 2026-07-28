"""Host-safe sequence validation and newest-viewport coalescing."""

from magwrite.uart_protocol import END_OF_SCENARIO, END_OF_TEST, HELLO, VIEWPORT
from magwrite.viewport_message import ViewportMessage


class UartReceiver:
    def __init__(self, logger=None):
        self.logger = logger or (lambda record: None)
        self.last_sequence = None
        self.latest_revision = 0
        self.pending = None
        self.duplicates = 0
        self.stale = 0
        self.sequence_gaps = 0
        self.superseded = 0
        self.frames_valid = 0
        self.viewport_frames = 0
        self.hello_received = False
        self.end_received = False
        self.expected_final_revision = None
        self.expected_viewport_count = None
        self.expected_final_hash = None
        self.final_hash_valid = None
        self.last_viewport_hash = None
        self.scenarios_completed = 0

    def accept(self, frame):
        self.logger({
            "event": "uart_frame_received",
            "sequence": frame.sequence,
            "revision": frame.revision,
            "message_type": frame.message_type,
            "crc_valid": True,
            "pending_revision": self.pending.revision if self.pending else None,
        })
        if self.last_sequence is not None:
            if frame.sequence == self.last_sequence:
                self.duplicates += 1
                return None
            if frame.sequence < self.last_sequence:
                self.stale += 1
                return None
            if frame.sequence != self.last_sequence + 1:
                self.sequence_gaps += 1
        self.last_sequence = frame.sequence
        self.frames_valid += 1
        if frame.message_type == HELLO:
            self.hello_received = True
            return frame
        if frame.message_type == END_OF_TEST:
            try:
                revision, count, digest = frame.payload.decode("ascii").split(";")
                self.expected_final_revision = int(revision)
                self.expected_viewport_count = int(count)
                self.expected_final_hash = digest
            except (UnicodeError, ValueError):
                raise ValueError("malformed END_OF_TEST")
            self.end_received = True
            self.final_hash_valid = self.last_viewport_hash == digest
            return frame
        if frame.message_type == END_OF_SCENARIO:
            if len(frame.payload) != 9:
                raise ValueError("malformed END_OF_SCENARIO")
            digest = frame.payload[1:].decode("ascii")
            if digest != self.last_viewport_hash:
                raise ValueError("scenario viewport hash mismatch")
            self.scenarios_completed += 1
            return frame
        if frame.message_type != VIEWPORT:
            return frame
        if not self.hello_received:
            raise ValueError("VIEWPORT received before HELLO")
        viewport = ViewportMessage.decode(frame.revision, frame.payload)
        self.viewport_frames += 1
        if frame.revision <= self.latest_revision:
            self.stale += 1
            return None
        self.latest_revision = frame.revision
        self.last_viewport_hash = viewport.digest()
        if self.pending is not None:
            self.superseded += 1
            self.logger({"event": "viewport_superseded",
                         "old_revision": self.pending.revision,
                         "new_revision": viewport.revision})
        self.pending = viewport
        return viewport

    def take_pending(self):
        value = self.pending
        self.pending = None
        return value
