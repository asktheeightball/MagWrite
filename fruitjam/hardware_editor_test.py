"""One-shot authoritative Fruit Jam multiline editor over bidirectional UART.

The Fruit Jam owns the document, the line structure, the cursor, the layout,
the editor revisions, and the complete semantic viewport. This module owns UART
bytes and guards only; every scheduling, editing, and layout decision lives in
the host-tested ``magwrite_transport.editor_session`` module.
"""

import json
import os
import storage
import supervisor
import time

import config
from magwrite_transport.diagnostics import log
from magwrite_transport.editor_scenarios import (
    MAX_EDITOR_INPUT_FRAMES, MAX_EDITOR_VIEWPORT_FRAMES,
)
from magwrite_transport.editor_session import EditorSession
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE, VERSION

START = "/magwrite_editor_integration.started"
COMPLETE = "/magwrite_editor_integration.complete"
EDITOR_MODE = "FRUITJAM_EDITOR_INTEGRATION"


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


if not (
    getattr(config, "ENABLE_EDITOR_INTEGRATION_TEST", False)
    and getattr(config, "EDITOR_INTEGRATION_TEST_MODE", "DISABLED") == EDITOR_MODE
):
    raise RuntimeError("Fruit Jam editor gate not armed")
if not config.UART_TX_PIN_ALIAS or not config.UART_RX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if VERSION != 1 or MAX_PAYLOAD_SIZE != 192:
    raise RuntimeError("protocol constants do not match the verified wire format")
if exists(START) or exists(COMPLETE):
    raise RuntimeError("Fruit Jam editor guard exists")

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
session = EditorSession(
    time.monotonic, log,
    timeout_seconds=config.EDITOR_TEST_TIMEOUT_SECONDS,
    queue_capacity=config.EDITOR_EVENT_QUEUE_CAPACITY,
    tracker_capacity=config.EDITOR_ACK_TRACKER_CAPACITY,
)
result = "FAIL"
log({"event": "editor_test_ready", "tx_alias": config.UART_TX_PIN_ALIAS,
     "rx_alias": config.UART_RX_PIN_ALIAS, "baud": config.UART_BAUD,
     "startup_delay_seconds": config.STARTUP_DELAY_SECONDS})
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
        if session.viewport_frames_sent > MAX_EDITOR_VIEWPORT_FRAMES:
            raise RuntimeError("viewport frame limit exceeded")
        if session.frame_sequence > MAX_EDITOR_INPUT_FRAMES:
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
