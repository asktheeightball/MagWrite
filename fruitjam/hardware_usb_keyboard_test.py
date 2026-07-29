"""One-shot live USB HID keyboard typing session on the Fruit Jam.

This entry point owns UART bytes, USB host construction, and guards only. Every
scheduling, HID translation, editing, layout, viewport, and acknowledgement
decision lives in host-tested modules, so the identical logic runs under CPython.

The Fruit Jam stays authoritative for the document, the cursor, the layout, and
both revisions. The MagTag stays display-only. Neither the editor, the layout,
the viewport builder, nor the UART protocol is modified by this phase: only the
input source changes, from a scripted producer to a real keyboard.

Press Escape on the real keyboard to finish the run.
"""

import json
import os
import storage
import supervisor
import time

import config
from magwrite_transport.diagnostics import log
from magwrite_transport.live_session import (
    MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES, LiveTypingSession,
)
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE, VERSION
from magwrite_transport.usb_host_backend import UsbHostKeyboardBackend
from magwrite_transport.usb_keyboard_adapter import UsbKeyboardAdapter

START = "/magwrite_usb_keyboard.started"
COMPLETE = "/magwrite_usb_keyboard.complete"
USB_KEYBOARD_MODE = "FRUITJAM_USB_KEYBOARD"


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


if not (
    getattr(config, "ENABLE_USB_KEYBOARD_TEST", False)
    and getattr(config, "USB_KEYBOARD_TEST_MODE", "DISABLED") == USB_KEYBOARD_MODE
):
    raise RuntimeError("Fruit Jam USB keyboard gate not armed")
if not config.UART_TX_PIN_ALIAS or not config.UART_RX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if VERSION != 1 or MAX_PAYLOAD_SIZE != 192:
    raise RuntimeError("protocol constants do not match the verified wire format")
if exists(START) or exists(COMPLETE):
    raise RuntimeError("Fruit Jam USB keyboard guard exists")

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
backend = UsbHostKeyboardBackend(
    log, read_timeout_ms=config.USB_KEYBOARD_READ_TIMEOUT_MS
)
session = LiveTypingSession(
    time.monotonic, log,
    adapter_factory=lambda queue: UsbKeyboardAdapter(
        backend, queue, log,
        poll_budget=config.USB_KEYBOARD_POLL_BUDGET,
        max_events=config.USB_KEYBOARD_MAX_EVENTS,
        now=time.monotonic(),
    ),
    queue_capacity=config.USB_KEYBOARD_QUEUE_CAPACITY,
    tracker_capacity=config.USB_KEYBOARD_ACK_TRACKER_CAPACITY,
    min_send_seconds=config.USB_KEYBOARD_MIN_SEND_SECONDS,
    idle_timeout_seconds=config.USB_KEYBOARD_IDLE_TIMEOUT_SECONDS,
    session_timeout_seconds=config.USB_KEYBOARD_SESSION_TIMEOUT_SECONDS,
)
result = "FAIL"
log({"event": "usb_keyboard_test_ready", "tx_alias": config.UART_TX_PIN_ALIAS,
     "rx_alias": config.UART_RX_PIN_ALIAS, "baud": config.UART_BAUD,
     "startup_delay_seconds": config.STARTUP_DELAY_SECONDS,
     "finish_key": "ESCAPE"})
time.sleep(config.STARTUP_DELAY_SECONDS)

try:
    while not session.complete:
        available = min(uart.in_waiting, config.UART_READ_BUDGET)
        while available:
            session.feed(uart.read(available))
            available = min(uart.in_waiting, config.UART_READ_BUDGET)
        session.service()
        for frame in session.take_outbound():
            if uart.write(frame) != len(frame):
                raise RuntimeError("short UART input write")
        if session.viewport_frames_sent > MAX_VIEWPORT_FRAMES:
            raise RuntimeError("viewport frame limit exceeded")
        if session.frame_sequence > MAX_PROTOCOL_FRAMES:
            raise RuntimeError("input frame limit exceeded")
        time.sleep(0.002)
    result = "PASS"
except Exception as error:
    session.stop_reason = str(error)

summary = session.summary(result)
log(summary)
with open(COMPLETE if result == "PASS" else START, "w") as handle:
    handle.write(json.dumps(summary))
try:
    storage.remount("/", readonly=True)
except RuntimeError as error:
    log({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
