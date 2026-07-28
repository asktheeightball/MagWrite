"""One-shot full-duplex UART acknowledgement sender and verifier."""

import json
import os
import storage
import supervisor
import time

import config
from magwrite_transport.ack_tracker import AckTracker
from magwrite_transport.ack_viewports import ack_test_messages
from magwrite_transport.diagnostics import log
from magwrite_transport.protocol import (
    END_OF_TEST, HELLO, TEST_COMPLETE, VIEWPORT, FrameParser, crc32, encode_frame,
)

START = "/magwrite_uart_ack_tx.started"
COMPLETE = "/magwrite_uart_ack_tx.complete"


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


if not (
    config.ENABLE_BIDIRECTIONAL_UART_TEST
    and config.BIDIRECTIONAL_UART_TEST_MODE == "FRUITJAM_UART_ACK_TX"
):
    raise RuntimeError("bidirectional Fruit Jam UART gate not armed")
if not config.UART_TX_PIN_ALIAS or not config.UART_RX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if exists(START) or exists(COMPLETE):
    raise RuntimeError("bidirectional Fruit Jam UART guard exists")

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
parser = FrameParser()
tracker = AckTracker(
    config.UART_ACK_TRACKER_CAPACITY,
    time.monotonic(),
    config.STATUS_HELLO_TIMEOUT_SECONDS,
    config.FRAME_ACCEPTED_TIMEOUT_SECONDS,
    config.REFRESH_STARTED_TIMEOUT_SECONDS,
    config.REFRESH_COMPLETED_TIMEOUT_SECONDS,
    config.DISPLAY_CAUGHT_UP_TIMEOUT_SECONDS,
)
messages = ack_test_messages()
sequence = 0
bytes_sent = 0
bytes_received = 0
viewport_frames_sent = 0
started = time.monotonic()
result = "FAIL"
reason = None
next_index = 0
scenario_three_sent = False
end_sent = False
status_counts = {}
log({"event": "uart_ack_tx_ready", "tx_alias": config.UART_TX_PIN_ALIAS,
     "rx_alias": config.UART_RX_PIN_ALIAS, "baud": config.UART_BAUD})
time.sleep(config.STARTUP_DELAY_SECONDS)


def send(item):
    global sequence, bytes_sent, viewport_frames_sent
    kind, revision, payload = item
    sequence += 1
    frame = encode_frame(kind, sequence, revision, payload)
    if uart.write(frame) != len(frame):
        raise RuntimeError("short UART input write")
    bytes_sent += len(frame)
    if kind == VIEWPORT:
        viewport_frames_sent += 1
        tracker.sent(revision, sequence, crc32(payload), time.monotonic())
    log({"event": "uart_input_sent", "message_type": kind,
         "sequence": sequence, "revision": revision})


try:
    send(messages[0])
    next_index = 1
    while True:
        available = min(uart.in_waiting, config.UART_READ_BUDGET)
        while available:
            chunk = uart.read(available)
            if chunk:
                bytes_received += len(chunk)
                parser.feed(chunk)
            available = min(uart.in_waiting, config.UART_READ_BUDGET)
        while True:
            frame = parser.pop()
            if frame is None:
                break
            fields = tracker.apply(frame, time.monotonic())
            status_counts[frame.message_type] = status_counts.get(
                frame.message_type, 0
            ) + 1
            log({"event": "uart_status_received", "message_type": frame.message_type,
                 "sequence": frame.sequence, "revision": frame.revision,
                 "fields": fields})
        if (
            parser.crc_failures
            or parser.version_failures
            or parser.type_failures
            or parser.oversized
            or parser.buffer_overflows
        ):
            raise RuntimeError("fatal UART status parser integrity failure")

        # Scenario 1 is the HELLO exchange. Scenario 2 is one exact lifecycle.
        if tracker.hello and next_index == 1:
            send(messages[next_index])
            next_index += 1
        first = tracker.find(1)
        if first is not None and first.displayed and not scenario_three_sent:
            # Scenario 3 deliberately coalesces revisions 2..5.
            for index in range(2, 6):
                send(messages[index])
            next_index = 6
            scenario_three_sent = True
        fifth = tracker.find(5)
        if fifth is not None and fifth.displayed and next_index == 6:
            send(messages[6])
            next_index = 7
        sixth = tracker.find(6)
        if sixth is not None and sixth.displayed and not end_sent:
            send(messages[7])
            end_sent = True
        if tracker.final_complete and end_sent:
            result = "PASS"
            break
        tracker.check_timeouts(time.monotonic())
        if time.monotonic() - started > config.UART_ACK_TEST_TIMEOUT_SECONDS:
            raise RuntimeError("bidirectional test timeout")
        time.sleep(0.002)
except Exception as error:
    reason = str(error)

summary = {
    "event": "bidirectional_uart_test_summary",
    "result": result, "stop_reason": reason,
    "bytes_sent": bytes_sent, "bytes_received": bytes_received,
    "input_frames_sent": sequence,
    "status_sequence_gaps": tracker.status_sequence_gaps,
    "status_duplicates": tracker.status_duplicates,
    "status_stale": tracker.status_stale,
    "displayed_revision": tracker.final_displayed_revision,
    "final_hash": tracker.final_hash,
    "test_complete": tracker.final_complete,
    "viewport_frames_sent": viewport_frames_sent,
    "frame_accepted_received": status_counts.get(6, 0),
    "refresh_started_received": status_counts.get(7, 0),
    "refresh_completed_received": status_counts.get(8, 0),
    "display_caught_up_received": status_counts.get(9, 0),
    "final_transmitted_revision": tracker.latest_sent_revision,
    "final_displayed_revision": tracker.final_displayed_revision,
    "discarded_prefix_bytes": parser.bytes_discarded_before_magic,
    "resynchronizations": parser.resynchronization_events,
    "status_frames_rejected": parser.rejected,
    "crc_failures": parser.crc_failures,
    "timeouts": 1 if reason and "timeout" in reason else 0,
}
log(summary)
with open(COMPLETE if result == "PASS" else START, "w") as handle:
    handle.write(json.dumps(summary))
try:
    storage.remount("/", readonly=True)
except RuntimeError as error:
    log({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
