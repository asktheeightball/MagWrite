"""V1 phase 1: measured responsiveness and keyboard verification on the Fruit Jam.

A **sibling** of ``hardware_usb_keyboard_test.py``, deliberately not a change to
it. That harness is the artifact of a completed, physically verified milestone;
its guards exist on the board and must stay byte-identical. This phase gets its
own activation pair, its own guard family, and its own evidence files, so
nothing it does can touch the completed milestone's record.

Everything that actually runs is the same host-tested code: the same
``LiveTypingSession``, the same editor, layout, viewport, protocol, and
acknowledgement modules. Only three things differ:

* the adaptive pacer from ``pacing`` replaces the fixed send interval;
* the device keyboard layout from ``keyboard_layout`` is selected from the USB
  descriptor, so the TH40's apostrophe usage is translated correctly;
* ``LatencyRecorder`` measures the keypress-to-visible chain, passively.

Press the Application (menu) key on the real keyboard to finish the run. Escape
also finishes, but on the TH40 it is only reachable through an Fn layer that
switches the keyboard out of USB mode, so Application is the usable control.
"""

import json
import os
import storage
import supervisor
import time

import config
from magwrite_transport.diagnostics import log
from magwrite_transport.latency import LatencyRecorder
from magwrite_transport.live_session import (
    MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES, LiveTypingSession,
)
from magwrite_transport.pacing import DisplayPacer
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE, VERSION
from magwrite_transport.usb_host_backend import UsbHostKeyboardBackend
from magwrite_transport.usb_keyboard_adapter import UsbKeyboardAdapter

START = "/magwrite_v1_responsiveness.started"
COMPLETE = "/magwrite_v1_responsiveness.complete"
V1_RESPONSIVENESS_MODE = "FRUITJAM_V1_RESPONSIVENESS"

# Guards belonging to the completed USB-keyboard milestone. Named here only so
# the refusal below is explicit and so a reader can see they are never written.
COMPLETED_MILESTONE_GUARDS = (
    "/magwrite_usb_keyboard.started",
    "/magwrite_usb_keyboard.complete",
)


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


if not (
    getattr(config, "ENABLE_V1_RESPONSIVENESS_TEST", False)
    and getattr(config, "V1_RESPONSIVENESS_TEST_MODE", "DISABLED")
    == V1_RESPONSIVENESS_MODE
):
    raise RuntimeError("Fruit Jam V1 responsiveness gate not armed")
if not config.UART_TX_PIN_ALIAS or not config.UART_RX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if VERSION != 1 or MAX_PAYLOAD_SIZE != 192:
    raise RuntimeError("protocol constants do not match the verified wire format")
if exists(START) or exists(COMPLETE):
    raise RuntimeError("Fruit Jam V1 responsiveness guard exists")
# The completed milestone's guards are expected to be present and are left
# exactly as they are. Their presence is never a reason to refuse this run, and
# their absence is never a reason to proceed differently.

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
        layout=config.USB_KEYBOARD_LAYOUT,
        now=time.monotonic(),
    ),
    queue_capacity=config.USB_KEYBOARD_QUEUE_CAPACITY,
    tracker_capacity=config.USB_KEYBOARD_ACK_TRACKER_CAPACITY,
    pacer=DisplayPacer(
        coalesce_seconds=config.USB_KEYBOARD_COALESCE_SECONDS,
        quiet_seconds=config.USB_KEYBOARD_QUIET_SECONDS,
        caught_up_min_send_seconds=(
            config.USB_KEYBOARD_CAUGHT_UP_MIN_SEND_SECONDS
        ),
        sustained_min_send_seconds=(
            config.USB_KEYBOARD_SUSTAINED_MIN_SEND_SECONDS
        ),
    ),
    latency=LatencyRecorder(),
    idle_timeout_seconds=config.V1_RESPONSIVENESS_IDLE_TIMEOUT_SECONDS,
    session_timeout_seconds=config.V1_RESPONSIVENESS_SESSION_TIMEOUT_SECONDS,
)
result = "FAIL"
log({"event": "v1_responsiveness_ready", "tx_alias": config.UART_TX_PIN_ALIAS,
     "rx_alias": config.UART_RX_PIN_ALIAS, "baud": config.UART_BAUD,
     "startup_delay_seconds": config.STARTUP_DELAY_SECONDS,
     "keyboard_layout": config.USB_KEYBOARD_LAYOUT,
     "finish_key": "APPLICATION"})
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
summary["event"] = "v1_responsiveness_test_summary"
log(summary)
with open(COMPLETE if result == "PASS" else START, "w") as handle:
    handle.write(json.dumps(summary))
try:
    storage.remount("/", readonly=True)
except RuntimeError as error:
    log({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
