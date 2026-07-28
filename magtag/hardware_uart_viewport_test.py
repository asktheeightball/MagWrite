"""One-shot, receive-only Fruit Jam UART viewport physical test."""

import json
import os
import storage
import supervisor
import time

import config
from magwrite.display_adapter import validate_physical_test_activation
from magwrite.serial_log import StructuredSerialLogger
from magwrite.transport_scheduler import TransportScheduler, TransportStopped
from magwrite.uart_protocol import END_OF_TEST, FrameParser
from magwrite.uart_receiver import UartReceiver
from magwrite.uc8151_adapter import UC8151DisplayAdapter, UPSTREAM_COMMIT
from magwrite.viewport_renderer import render_viewport

START = "/magwrite_uart_rx.started"
COMPLETE = "/magwrite_uart_rx.complete"
MAX_PARTIAL_REFRESHES = 30
EXPECTED_DRIVER_SHA256 = "A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E"


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


logger = StructuredSerialLogger()
logger({"event": "uart_rx_boot", "display_enabled": config.ENABLE_PHYSICAL_DISPLAY,
        "receiver_enabled": config.ENABLE_UART_RECEIVER,
        "physical_mode": config.PHYSICAL_TEST_MODE, "uart_mode": config.UART_TEST_MODE,
        "driver_commit": UPSTREAM_COMMIT})
validate_physical_test_activation(config, config.PHYSICAL_TEST_MODE)
if not config.ENABLE_UART_RECEIVER or config.UART_TEST_MODE != "MAGTAG_UART_VIEWPORT_RX":
    raise RuntimeError("UART receiver refused: explicit gate not armed")
if config.PHYSICAL_TEST_MODE != "MAGTAG_UART_VIEWPORT_RX":
    raise RuntimeError("UART receiver refused: physical mode mismatch")
if not config.UART_RX_PIN_ALIAS:
    raise RuntimeError("UART_RX_PIN_ALIAS must be physically confirmed")
if exists(START) or exists(COMPLETE):
    raise RuntimeError("UART RX guard exists")

supervisor.runtime.autoreload = False
with open(START, "w") as handle:
    handle.write("claimed\n")

import board
import busio

uart = busio.UART(tx=None, rx=getattr(board, config.UART_RX_PIN_ALIAS),
                  baudrate=config.UART_BAUD, timeout=0, receiver_buffer_size=256)
display = UC8151DisplayAdapter(config, config.PHYSICAL_TEST_MODE)
display.initialize()
parser = FrameParser()
receiver = UartReceiver(logger)
scheduler = TransportScheduler(parser, receiver, display, render_viewport)
logger({"event": "uart_rx_waiting", "expected": "HELLO",
        "baud": config.UART_BAUD, "rx_alias": config.UART_RX_PIN_ALIAS,
        "driver_sha256": EXPECTED_DRIVER_SHA256})
started = time.monotonic()
last_waiting_log = started
inflight_started = None
partial_durations = []
full_duration = None
bytes_received = 0
result = "INCONCLUSIVE"
reason = None

try:
    while True:
        if not receiver.hello_received and time.monotonic() - last_waiting_log >= 1:
            logger({"event": "uart_rx_waiting", "expected": "HELLO",
                    "baud": config.UART_BAUD, "rx_alias": config.UART_RX_PIN_ALIAS})
            last_waiting_log = time.monotonic()
        chunks = []
        available = min(uart.in_waiting, config.UART_READ_BUDGET)
        while available:
            chunk = uart.read(available)
            if chunk:
                chunks.append(chunk)
                bytes_received += len(chunk)
            available = min(uart.in_waiting, config.UART_READ_BUDGET)
        before = scheduler.inflight_revision
        if before is not None and not display.is_busy():
            duration = int((time.monotonic() - inflight_started) * 1000)
            if scheduler.rendered == 1:
                full_duration = duration
            else:
                partial_durations.append(duration)
            logger({"event": "viewport_refresh_completed", "revision": before,
                    "duration_ms": duration})
        scheduler.service(chunks)
        after = scheduler.inflight_revision
        if after is not None and after != before:
            inflight_started = time.monotonic()
            logger({"event": "viewport_refresh_started", "revision": after,
                    "mode": "full" if scheduler.rendered == 1 else "partial"})
        if display.is_busy() and inflight_started and time.monotonic() - inflight_started > 20:
            raise TransportStopped("display busy timeout")
        if scheduler.rendered - 1 > MAX_PARTIAL_REFRESHES:
            raise TransportStopped("partial refresh limit exceeded")
        if parser.buffer_overflows or parser.oversized or parser.version_failures or parser.type_failures:
            raise TransportStopped("fatal transport integrity failure")
        if parser.crc_failures > 2:
            raise TransportStopped("CRC failure limit exceeded")
        if receiver.stale:
            raise TransportStopped("unexpected backward sequence or stale revision")
        if receiver.end_received and scheduler.inflight_revision is None:
            if scheduler.displayed_revision != receiver.expected_final_revision:
                raise TransportStopped("final displayed revision mismatch")
            if receiver.viewport_frames != receiver.expected_viewport_count:
                raise TransportStopped("viewport count mismatch")
            if receiver.final_hash_valid is not True:
                raise TransportStopped("final viewport hash mismatch")
            result = "PASS"
            break
        if time.monotonic() - started > 60:
            raise TransportStopped("test timeout")
        time.sleep(0.002)
except Exception as error:
    result = "FAIL"
    reason = str(error)

summary = {
    "event": "uart_viewport_test_summary", "result": result, "stop_reason": reason,
    "bytes_received": bytes_received, "frames_received": receiver.frames_valid + parser.rejected,
    "frames_valid": receiver.frames_valid, "frames_rejected": parser.rejected,
    "crc_failures": parser.crc_failures, "sequence_gaps": receiver.sequence_gaps,
    "viewport_frames_received": receiver.viewport_frames,
    "viewport_frames_rendered": scheduler.rendered,
    "viewport_frames_superseded": receiver.superseded,
    "latest_received_revision": receiver.latest_revision,
    "displayed_revision": scheduler.displayed_revision,
    "partial_refreshes": max(0, scheduler.rendered - 1),
    "full_refreshes": 1 if scheduler.rendered else 0,
    "timeouts": 1 if reason and "timeout" in reason else 0,
    "final_hash": receiver.expected_final_hash,
    "initial_full_duration_ms": full_duration,
    "partial_durations_ms": partial_durations,
}
logger(summary)
if result == "PASS":
    with open(COMPLETE, "w") as handle:
        handle.write(json.dumps(summary))
else:
    with open(START, "w") as handle:
        handle.write(json.dumps(summary))
try:
    storage.remount("/", readonly=True)
except RuntimeError as error:
    logger({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
