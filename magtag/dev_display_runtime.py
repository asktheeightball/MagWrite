"""Repeatable display-only MagTag terminal for the development runtime.

The counterpart to ``fruitjam/dev_runtime.py``, and **not** a physical
verification harness. The MagTag's role is unchanged and stays display-only: it
never edits, corrects, persists, scrolls, or reinterprets the document. It
bounds-checks and renders the semantic viewport the Fruit Jam supplies, and
reports frame acceptance, refresh start, refresh completion, and the displayed
revision over the return UART.

What is deliberately absent, and why
------------------------------------

The guarded harnesses claim a one-shot ``.started`` guard, refuse a second run,
depend on ``hardware_test_boot.py`` having remounted the filesystem read-write,
disable autoreload, enforce certification ceilings on viewports, frames, status
frames and partial refreshes, run against a two-phase certification clock, and
end by trapping the board. All of that is right for producing evidence once and
wrong for development.

So this runtime:

* creates, deletes, and checks **no** guard file;
* never calls ``storage.remount`` — ``MAGTAG_DEV_DISPLAY`` is intentionally
  absent from the boot remount gate, so CIRCUITPY stays writable by the host;
* leaves ``supervisor.runtime.autoreload`` alone, so saving a file restarts it;
* claims no PASS or FAIL and enforces no certification ceiling;
* serves session after session: when the Fruit Jam finishes one, the parser and
  scheduler are rebuilt and the panel is ready for the next start, with no
  reset, no guard deletion, and no safe mode.

The one hardware bound that is kept is the display busy timeout. That one is not
a certification budget; it catches a panel that never reports itself idle, which
is a real fault at any time.

Refresh timings are drained into a small running aggregate every pass rather
than accumulated, so nothing grows with session length and the scheduler's
bounded completion history can never fill.
"""

import time

import config
from magwrite.ack_scheduler import AckDisplayScheduler
from magwrite.display_adapter import validate_physical_test_activation
from magwrite.serial_log import StructuredSerialLogger
from magwrite.sha256 import sha256_file
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import DISPLAY_ERROR, FrameParser
from magwrite.uc8151_adapter import UC8151DisplayAdapter
from magwrite.viewport_renderer import render_viewport

DEV_DISPLAY_MODE = "MAGTAG_DEV_DISPLAY"
EXPECTED_DRIVER_SHA256 = (
    "A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E"
)


class RefreshStats:
    """Running count, minimum, maximum and mean, with no sample list."""

    def __init__(self):
        self.count = 0
        self.full = 0
        self.partial = 0
        self.stale = 0
        self.partial_minimum_ms = None
        self.partial_maximum_ms = None
        self.partial_total_ms = 0

    def add(self, duration_ms, full, stale):
        self.count += 1
        if stale:
            self.stale += 1
        if full:
            self.full += 1
            return
        self.partial += 1
        self.partial_total_ms += duration_ms
        if self.partial_minimum_ms is None or duration_ms < self.partial_minimum_ms:
            self.partial_minimum_ms = duration_ms
        if self.partial_maximum_ms is None or duration_ms > self.partial_maximum_ms:
            self.partial_maximum_ms = duration_ms

    def describe(self):
        return {
            "refreshes": self.count,
            "full_refreshes": self.full,
            "partial_refreshes": self.partial,
            "stale_renders": self.stale,
            "partial_refresh_minimum_ms": self.partial_minimum_ms,
            "partial_refresh_maximum_ms": self.partial_maximum_ms,
            "partial_refresh_mean_ms": (
                self.partial_total_ms / self.partial if self.partial else None
            ),
        }


logger = StructuredSerialLogger()
validate_physical_test_activation(config, config.PHYSICAL_TEST_MODE)
if not (
    getattr(config, "ENABLE_UART_RECEIVER", False)
    and getattr(config, "ENABLE_UART_STATUS_TX", False)
    and config.PHYSICAL_TEST_MODE == DEV_DISPLAY_MODE
    and getattr(config, "DEV_DISPLAY_RUNTIME_MODE", "DISABLED") == DEV_DISPLAY_MODE
):
    raise RuntimeError("MagTag development display runtime is not enabled")
if not config.UART_RX_PIN_ALIAS or not config.UART_TX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if sha256_file("/uc8151.py") != EXPECTED_DRIVER_SHA256:
    raise RuntimeError("UC8151 driver hash mismatch")

import board
import busio

uart = None
display = None
error = None

# Fenced off from the serve loop for the same reason as on the Fruit Jam: the
# filesystem was never remounted, so a construction failure leaves the board
# writable, autoreloading, and restartable without safe mode.
try:
    uart = busio.UART(
        tx=getattr(board, config.UART_TX_PIN_ALIAS),
        rx=getattr(board, config.UART_RX_PIN_ALIAS),
        baudrate=config.UART_BAUD,
        timeout=0,
        receiver_buffer_size=256,
    )
    display = UC8151DisplayAdapter(config, config.PHYSICAL_TEST_MODE)
    display.initialize()
except Exception as construction_error:  # noqa: BLE001 - reported, not swallowed
    error = str(construction_error)
    logger({"event": "dev_display_construction_failed", "detail": error,
            "filesystem_remounted": False, "guard_written": False})

sessions = 0
if display is not None:
    logger({"event": "dev_display_ready",
            "rx_alias": config.UART_RX_PIN_ALIAS,
            "tx_alias": config.UART_TX_PIN_ALIAS, "baud": config.UART_BAUD})

    def new_session():
        parser = FrameParser()
        outbox = StatusQueue(config.UART_STATUS_QUEUE_CAPACITY)
        scheduler = AckDisplayScheduler(
            parser, display, render_viewport, outbox, time.monotonic,
        )
        return parser, outbox, scheduler, RefreshStats()

    parser, outbox, scheduler, stats = new_session()
    inflight_started = None
    bytes_received = 0
    bytes_sent = 0
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
            # Drained every pass so the bounded completion history cannot fill
            # and nothing accumulates over an open-ended development session.
            while scheduler.completions:
                _revision, duration_ms, full, stale = scheduler.completions.pop(0)
                stats.add(duration_ms, full, stale)
            while len(outbox):
                kind, sequence, revision, frame = outbox.pop()
                written = uart.write(frame)
                if written != len(frame):
                    raise RuntimeError("short UART status write")
                bytes_sent += written
                logger({"event": "dev_display_status_sent", "message_type": kind,
                        "sequence": sequence, "revision": revision})
            if display.is_busy() and inflight_started is not None and (
                time.monotonic() - inflight_started
                > config.UART_DISPLAY_BUSY_TIMEOUT_SECONDS
            ):
                raise RuntimeError("display busy timeout")
            if scheduler.test_complete_sent and len(outbox) == 0:
                sessions += 1
                summary = {
                    "event": "dev_display_session_summary",
                    "session": sessions,
                    "bytes_received": bytes_received,
                    "bytes_sent": bytes_sent,
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
                }
                summary.update(stats.describe())
                logger(summary)
                # Ready for the next Fruit Jam start with no reset and no guard
                # to clear. Revisions restart from zero, so the parser and
                # scheduler are rebuilt rather than carried over.
                parser, outbox, scheduler, stats = new_session()
                inflight_started = None
                bytes_received = 0
                bytes_sent = 0
                logger({"event": "dev_display_awaiting_next_session",
                        "sessions_served": sessions})
            time.sleep(0.002)
    except KeyboardInterrupt:
        # Ctrl-C at the console is a legitimate development stop, not a fault.
        error = None
    except Exception as run_error:  # noqa: BLE001 - reported, not swallowed
        error = str(run_error)
        try:
            outbox.offer(DISPLAY_ERROR, scheduler.latest_revision, {
                "code": 1,
                "inflight_revision": (
                    scheduler.inflight[0].revision if scheduler.inflight else 0
                ),
                "latest_received_revision": scheduler.latest_revision,
                "displayed_revision": scheduler.displayed_revision,
                "reason": error,
            })
            item = outbox.pop()
            if item:
                uart.write(item[3])
        except Exception:
            pass

# No guard is written, no evidence file is produced, and nothing is remounted:
# the next start needs no cleanup, no deletion, and no safe mode.
logger({"event": "dev_display_stopped", "detail": error,
        "sessions_served": sessions, "restartable": True,
        "guard_written": False, "filesystem_remounted": False})
