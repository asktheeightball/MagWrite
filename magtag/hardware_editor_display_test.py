"""One-shot display-only MagTag terminal for the Fruit Jam editor test.

The MagTag never edits, corrects, persists, scrolls, or reinterprets the
document. It validates bounds, renders the supplied semantic viewport, and
reports frame acceptance, refresh start, refresh completion, and displayed
revision. All of that behaviour is the physically proven bidirectional
acknowledgement scheduler, reused unchanged.
"""

import json
import os
import storage
import supervisor
import time

import config
from magwrite.ack_scheduler import AckDisplayScheduler
from magwrite.display_adapter import validate_physical_test_activation
from magwrite.serial_log import StructuredSerialLogger
from magwrite.run_clock import RunClock
from magwrite.sha256 import sha256_file
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import DISPLAY_ERROR, FrameParser
from magwrite.uc8151_adapter import UC8151DisplayAdapter
from magwrite.viewport_renderer import render_viewport

START = "/magwrite_editor_display.started"
COMPLETE = "/magwrite_editor_display.complete"
EDITOR_DISPLAY_MODE = "MAGTAG_EDITOR_DISPLAY"
MAX_VIEWPORTS = 75
MAX_FRAMES = 150
MAX_STATUS_FRAMES = 150
MAX_PARTIAL_REFRESHES = 40
EXPECTED_DRIVER_SHA256 = (
    "A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E"
)


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


logger = StructuredSerialLogger()
validate_physical_test_activation(config, config.PHYSICAL_TEST_MODE)
if not (
    getattr(config, "ENABLE_UART_RECEIVER", False)
    and getattr(config, "ENABLE_UART_STATUS_TX", False)
    and config.PHYSICAL_TEST_MODE == EDITOR_DISPLAY_MODE
    and getattr(config, "EDITOR_DISPLAY_TEST_MODE", "DISABLED") == EDITOR_DISPLAY_MODE
):
    raise RuntimeError("MagTag editor display gate not armed")
if not config.UART_RX_PIN_ALIAS or not config.UART_TX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if sha256_file("/uc8151.py") != EXPECTED_DRIVER_SHA256:
    raise RuntimeError("UC8151 driver hash mismatch")
if exists(START) or exists(COMPLETE):
    raise RuntimeError("MagTag editor display guard exists")

supervisor.runtime.autoreload = False
with open(START, "w") as handle:
    handle.write("claimed\n")

import board
import busio

uart = busio.UART(
    tx=getattr(board, config.UART_TX_PIN_ALIAS),
    rx=getattr(board, config.UART_RX_PIN_ALIAS),
    baudrate=config.UART_BAUD,
    timeout=0,
    receiver_buffer_size=256,
)
display = UC8151DisplayAdapter(config, config.PHYSICAL_TEST_MODE)
display.initialize()
parser = FrameParser()
outbox = StatusQueue(config.UART_STATUS_QUEUE_CAPACITY)
scheduler = AckDisplayScheduler(
    parser, display, render_viewport, outbox, time.monotonic
)
clock = RunClock(
    time.monotonic,
    getattr(config, "EDITOR_ARMING_TIMEOUT_SECONDS", 900),
    config.EDITOR_TEST_TIMEOUT_SECONDS,
)
inflight_started = None
bytes_received = 0
bytes_sent = 0
result = "FAIL"
reason = None
logger({"event": "editor_display_ready", "rx_alias": config.UART_RX_PIN_ALIAS,
        "tx_alias": config.UART_TX_PIN_ALIAS, "baud": config.UART_BAUD})

try:
    while True:
        chunks = []
        available = min(uart.in_waiting, config.UART_READ_BUDGET)
        while available:
            chunk = uart.read(available)
            if chunk:
                chunks.append(chunk)
                bytes_received += len(chunk)
            available = min(uart.in_waiting, config.UART_READ_BUDGET)
        before = scheduler.inflight
        scheduler.service(chunks)
        if (
            parser.crc_failures
            or parser.version_failures
            or parser.type_failures
            or parser.oversized
            or parser.buffer_overflows
        ):
            raise RuntimeError("fatal UART input parser integrity failure")
        after = scheduler.inflight
        if before is None and after is not None:
            inflight_started = after[2]
        if not clock.running and scheduler.last_input_sequence:
            logger({"event": "editor_run_clock_started",
                    "arming_wait_seconds": round(clock.start_run(), 3)})
        while len(outbox):
            kind, sequence, revision, frame = outbox.pop()
            written = uart.write(frame)
            if written != len(frame):
                raise RuntimeError("short UART status write")
            bytes_sent += written
            logger({"event": "editor_status_sent", "message_type": kind,
                    "sequence": sequence, "revision": revision})
        if display.is_busy() and inflight_started is not None and (
            time.monotonic() - inflight_started
            > config.UART_DISPLAY_BUSY_TIMEOUT_SECONDS
        ):
            raise RuntimeError("display busy timeout")
        if scheduler.accepted_count > MAX_VIEWPORTS:
            raise RuntimeError("viewport limit exceeded")
        if scheduler.last_input_sequence and scheduler.last_input_sequence > MAX_FRAMES:
            raise RuntimeError("input frame limit exceeded")
        if outbox.frames_sent > MAX_STATUS_FRAMES:
            raise RuntimeError("status frame limit exceeded")
        if scheduler.refresh_count > MAX_PARTIAL_REFRESHES + 1:
            raise RuntimeError("refresh limit exceeded")
        if scheduler.test_complete_sent and len(outbox) == 0:
            result = "PASS"
            break
        expiry = clock.expired()
        if expiry:
            raise RuntimeError(expiry)
        time.sleep(0.002)
except Exception as error:
    reason = str(error)
    try:
        outbox.offer(DISPLAY_ERROR, scheduler.latest_revision, {
            "code": 1,
            "inflight_revision": (
                scheduler.inflight[0].revision if scheduler.inflight else 0
            ),
            "latest_received_revision": scheduler.latest_revision,
            "displayed_revision": scheduler.displayed_revision,
            "reason": reason,
        })
        item = outbox.pop()
        if item:
            uart.write(item[3])
    except Exception:
        pass

summary = {
    "event": "editor_display_test_summary",
    "result": result, "stop_reason": reason,
    "bytes_received": bytes_received, "bytes_sent": bytes_sent,
    "viewport_frames_received": scheduler.accepted_count,
    "viewport_frames_rendered": scheduler.rendered_count,
    "viewport_frames_superseded": scheduler.superseded_count,
    "status_frames_sent": outbox.frames_sent,
    "status_queue_maximum_depth": outbox.maximum_depth,
    "discarded_prefix_bytes": parser.bytes_discarded_before_magic,
    "resynchronization_events": parser.resynchronization_events,
    "maximum_discarded_prefix": parser.maximum_discarded_prefix,
    "parser_rejections": parser.rejected,
    "crc_failures": parser.crc_failures,
    "latest_received_revision": scheduler.latest_revision,
    "displayed_revision": scheduler.displayed_revision,
    "refreshes": scheduler.refresh_count,
    "full_refreshes": sum(1 for item in scheduler.completions if item[2]),
    "partial_refreshes": sum(1 for item in scheduler.completions if not item[2]),
    "refresh_durations_ms": [item[1] for item in scheduler.completions],
    "timeouts": 1 if reason and "timeout" in reason else 0,
}
logger(summary)
with open(COMPLETE if result == "PASS" else START, "w") as handle:
    handle.write(json.dumps(summary))
try:
    storage.remount("/", readonly=True)
except RuntimeError as error:
    logger({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
