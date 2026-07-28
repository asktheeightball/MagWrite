"""Deterministic host reconciliation for the one-way UART harness."""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.ack_scheduler import AckDisplayScheduler
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import FrameParser, TEST_COMPLETE, VIEWPORT
from magwrite.viewport_message import ViewportMessage
from magwrite_transport.ack_tracker import AckTracker
from magwrite_transport.ack_viewports import ack_test_messages
from magwrite_transport.deterministic_viewports import deterministic_messages
from magwrite_transport.protocol import FrameParser as ReturnParser
from magwrite_transport.protocol import crc32, encode_frame

messages = deterministic_messages()
wire = b"".join(
    encode_frame(kind, sequence, revision, payload)
    for sequence, (kind, revision, payload) in enumerate(messages, 1)
)
parser = FrameParser()
parser.feed(wire[:256])
frames = []
while True:
    frame = parser.pop()
    if frame is None:
        break
    frames.append(frame)
at = 256
while at < len(wire):
    parser.feed(wire[at:at + 256])
    at += 256
    while True:
        frame = parser.pop()
        if frame is None:
            break
        frames.append(frame)
views = [ViewportMessage.decode(frame.revision, frame.payload)
         for frame in frames if frame.message_type == VIEWPORT]
for filename in (
    "FRUITJAM_UART_TX_SERIAL.jsonl",
    "MAGTAG_UART_RX_SERIAL.jsonl",
    "FRUITJAM_UART_ACK_SERIAL.jsonl",
    "MAGTAG_UART_STATUS_SERIAL.jsonl",
):
    with open(os.path.join(ROOT, "docs", filename), encoding="utf-8") as handle:
        for line in handle:
            json.loads(line)


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Display:
    def __init__(self):
        self.busy = False

    def begin_refresh(self, framebuffer, full=False):
        self.busy = True
        return full

    def is_busy(self):
        return self.busy


clock = Clock()
display = Display()
outbox = StatusQueue(32)
ack_scheduler = AckDisplayScheduler(
    FrameParser(), display, lambda viewport: viewport.revision, outbox, clock
)
tracker = AckTracker(16, clock())
input_sequence = 0
status_parser = ReturnParser()
ack_messages = ack_test_messages()
for kind, revision, payload in ack_messages:
    input_sequence += 1
    if kind == VIEWPORT:
        tracker.sent(revision, input_sequence, crc32(payload), clock())
    ack_scheduler.service([
        encode_frame(kind, input_sequence, revision, payload)
    ])
    for _ in range(20):
        while len(outbox):
            status_parser.feed(outbox.pop()[3])
        while True:
            status = status_parser.pop()
            if status is None:
                break
            tracker.apply(status, clock())
        if ack_scheduler.inflight is not None:
            display.busy = False
            clock.now += 0.7
        ack_scheduler.service()
        if (
            kind != VIEWPORT
            or (tracker.find(revision) and tracker.find(revision).displayed)
        ):
            break
if not tracker.final_complete or not ack_scheduler.test_complete_sent:
    raise RuntimeError("bidirectional acknowledgement reconciliation failed")
if tracker.final_hash != ack_scheduler.latest_hash:
    raise RuntimeError("bidirectional final hash reconciliation failed")
print(json.dumps({
    "frames": len(frames),
    "viewport_frames": len(views),
    "wire_bytes": len(wire),
    "final_revision": views[-1].revision,
    "final_viewport_hash": views[-1].digest(),
    "parser_rejections": parser.rejected,
    "ack_input_frames": len(ack_messages),
    "ack_status_frames": outbox.frames_sent,
    "ack_final_revision": tracker.final_displayed_revision,
    "ack_final_hash": "%08X" % tracker.final_hash,
    "ack_test_complete": tracker.final_complete,
}, sort_keys=True))
