"""Deterministic host reconciliation for the one-way UART harness."""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.uart_protocol import FrameParser, VIEWPORT
from magwrite.viewport_message import ViewportMessage
from magwrite_transport.deterministic_viewports import deterministic_messages
from magwrite_transport.protocol import encode_frame

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
for filename in ("FRUITJAM_UART_TX_SERIAL.jsonl", "MAGTAG_UART_RX_SERIAL.jsonl"):
    with open(os.path.join(ROOT, "docs", filename), encoding="utf-8") as handle:
        for line in handle:
            json.loads(line)
print(json.dumps({
    "frames": len(frames),
    "viewport_frames": len(views),
    "wire_bytes": len(wire),
    "final_revision": views[-1].revision,
    "final_viewport_hash": views[-1].digest(),
    "parser_rejections": parser.rejected,
}, sort_keys=True))
