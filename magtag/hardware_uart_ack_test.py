"""One-shot full-duplex UART acknowledgement and display feasibility test."""

import json
import hashlib
import os
import storage
import supervisor
import time

import config
from magwrite.ack_scheduler import AckDisplayScheduler
from magwrite.display_adapter import validate_physical_test_activation
from magwrite.serial_log import StructuredSerialLogger
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import DISPLAY_ERROR, FrameParser
from magwrite.uc8151_adapter import UC8151DisplayAdapter
from magwrite.viewport_renderer import render_viewport

START = "/magwrite_uart_ack_rx.started"
COMPLETE = "/magwrite_uart_ack_rx.complete"
MAX_VIEWPORTS = 50
MAX_FRAMES = 100
MAX_PARTIAL_REFRESHES = 30
EXPECTED_DRIVER_SHA256 = (
    "A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E"
)


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(256)
            if not chunk:
                break
            digest.update(chunk)
    return "".join("%02X" % value for value in digest.digest())


logger = StructuredSerialLogger()
validate_physical_test_activation(config, config.PHYSICAL_TEST_MODE)
if not (
    config.ENABLE_UART_RECEIVER
    and config.ENABLE_UART_STATUS_TX
    and config.UART_TEST_MODE == "MAGTAG_UART_ACK_RX"
    and config.BIDIRECTIONAL_UART_TEST_MODE == "MAGTAG_UART_ACK_RX"
):
    raise RuntimeError("bidirectional MagTag UART gate not armed")
if not config.UART_RX_PIN_ALIAS or not config.UART_TX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if sha256_file("/uc8151.py") != EXPECTED_DRIVER_SHA256:
    raise RuntimeError("UC8151 driver hash mismatch")
if exists(START) or exists(COMPLETE):
    raise RuntimeError("bidirectional MagTag UART guard exists")

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
started = time.monotonic()
inflight_started = None
bytes_received = 0
bytes_sent = 0
result = "FAIL"
reason = None
logger({"event": "uart_ack_rx_ready", "rx_alias": config.UART_RX_PIN_ALIAS,
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
        while len(outbox):
            kind, sequence, revision, frame = outbox.pop()
            written = uart.write(frame)
            if written != len(frame):
                raise RuntimeError("short UART status write")
            bytes_sent += written
            logger({"event": "uart_status_sent", "message_type": kind,
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
        if scheduler.refresh_count > MAX_PARTIAL_REFRESHES + 1:
            raise RuntimeError("refresh limit exceeded")
        if scheduler.test_complete_sent and len(outbox) == 0:
            result = "PASS"
            break
        if time.monotonic() - started > config.UART_ACK_TEST_TIMEOUT_SECONDS:
            raise RuntimeError("bidirectional test timeout")
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
    "event": "bidirectional_uart_receiver_summary",
    "result": result, "stop_reason": reason,
    "bytes_received": bytes_received, "bytes_sent": bytes_sent,
    "accepted": scheduler.accepted_count, "rendered": scheduler.rendered_count,
    "superseded": scheduler.superseded_count,
    "refreshes": scheduler.refresh_count,
    "displayed_revision": scheduler.displayed_revision,
    "latest_revision": scheduler.latest_revision,
    "discarded_prefix_bytes": parser.bytes_discarded_before_magic,
    "resynchronizations": parser.resynchronization_events,
    "parser_rejections": parser.rejected,
    "crc_failures": parser.crc_failures,
    "status_queue_maximum_depth": outbox.maximum_depth,
    "viewport_frames_received": scheduler.accepted_count,
    "viewport_frames_accepted": scheduler.accepted_count,
    "viewport_frames_rendered": scheduler.rendered_count,
    "viewport_frames_superseded": scheduler.superseded_count,
    "status_frames_sent": outbox.frames_sent,
    "bytes_discarded_before_magic": parser.bytes_discarded_before_magic,
    "latest_received_revision": scheduler.latest_revision,
    "partial_refreshes": sum(1 for item in scheduler.completions if not item[2]),
    "full_refreshes": sum(1 for item in scheduler.completions if item[2]),
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
