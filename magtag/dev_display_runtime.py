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

The four buttons — V1.5
-----------------------

The MagTag's front buttons became the product's primary shell controls, and they
change nothing about what this board is allowed to know. It debounces four GPIOs,
gives each accepted press an ordinal, and sends a normalized ``MENU`` / ``UP`` /
``DOWN`` / ``SELECT`` action over the return UART. It does not know what state the
shell is in, which item is selected, or what any action will do; the Fruit Jam
owns all of that and every button frame is a request, never an instruction.

Button frames share the bounded status outbox with display acknowledgements
rather than getting a channel of their own, so the two cannot starve each other:
the scheduler already refuses to begin a refresh until the outbox has drained,
and a button frame is the same fourteen-byte header, CRC-32, and sequence number
as every acknowledgement. Headroom is reserved in the outbox for the
acknowledgements a refresh in flight is about to need, and a press that would eat
into it is dropped and counted rather than allowed to stall the panel.

A pin the board does not expose is a **reported degraded mode**: the display runs
and the keyboard still drives the shell. It is never a refusal to start, because
a writer with a working keyboard and a broken bezel should still be able to
write.
"""

import time

import config
from magwrite.ack_scheduler import AckDisplayScheduler
from magwrite.buttons import (
    ACTION_CODES, DOWN, MENU, SELECT, UP, ButtonPad,
)
from magwrite.display_adapter import validate_physical_test_activation
from magwrite.serial_log import StructuredSerialLogger
from magwrite.sha256 import sha256_file
from magwrite.startup_screens import (
    fault_screen, starting_screen, waiting_screen,
)
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import BUTTON_EVENT, DISPLAY_ERROR, FrameParser
from magwrite.uc8151_adapter import UC8151DisplayAdapter
from magwrite.viewport_renderer import render_viewport

DEV_DISPLAY_MODE = "MAGTAG_DEV_DISPLAY"
STANDALONE_DISPLAY_MODE = "MAGTAG_STANDALONE"
PROFILE_STANDALONE = "STANDALONE"
PROFILE_DEVELOPMENT = "DEVELOPMENT"
# How long the panel says only "STARTING" before it says it is *waiting*. Set
# above the 9.05 s a measured cold boot took, so an ordinary start never spends a
# refresh on it: seeing this screen means the writer board is taking longer than
# it ever has, which is the one startup fact worth acting on.
DEFAULT_STARTUP_WAIT_SECONDS = 15.0
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


def _select_profile():
    """Which of the two runtime profiles this board's config asks for.

    The development profile is checked first because it is the one that has to be
    *asked* for: it ships disabled, and a board that has been deliberately armed
    for the bench must not be quietly handed the appliance instead. Standalone is
    the fall-through, which is what makes it the default.
    """
    if (
        config.PHYSICAL_TEST_MODE == DEV_DISPLAY_MODE
        and getattr(config, "DEV_DISPLAY_RUNTIME_MODE", "DISABLED")
            == DEV_DISPLAY_MODE
    ):
        return PROFILE_DEVELOPMENT
    if (
        getattr(config, "ENABLE_STANDALONE", False)
        and config.PHYSICAL_TEST_MODE == STANDALONE_DISPLAY_MODE
        and getattr(config, "STANDALONE_DISPLAY_MODE", "DISABLED")
            == STANDALONE_DISPLAY_MODE
    ):
        return PROFILE_STANDALONE
    return None


PROFILE = _select_profile()
if PROFILE is None or not (
    getattr(config, "ENABLE_UART_RECEIVER", False)
    and getattr(config, "ENABLE_UART_STATUS_TX", False)
):
    raise RuntimeError("no MagTag display runtime is enabled")
STARTUP_WAIT_SECONDS = getattr(
    config, "STANDALONE_DISPLAY_WAIT_SECONDS", DEFAULT_STARTUP_WAIT_SECONDS)
if not config.UART_RX_PIN_ALIAS or not config.UART_TX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if sha256_file("/uc8151.py") != EXPECTED_DRIVER_SHA256:
    raise RuntimeError("UC8151 driver hash mismatch")

import board
import busio
import digitalio

# The four front buttons, in the order ``config`` names them. Active low with an
# internal pull-up on this board, which is why ``pressed`` is an inversion.
BUTTON_ALIASES = (
    (MENU, "BUTTON_MENU_PIN_ALIAS"),
    (UP, "BUTTON_UP_PIN_ALIAS"),
    (DOWN, "BUTTON_DOWN_PIN_ALIAS"),
    (SELECT, "BUTTON_SELECT_PIN_ALIAS"),
)
# Kept free in the bounded outbox for the acknowledgements a refresh in flight is
# about to need. A button must never be the reason the panel stops reporting.
BUTTON_OUTBOX_HEADROOM = 4


def build_button_pad(logger):
    """Claim the four button pins. Returns ``(pad, pins, detail)``.

    Never raises. A missing alias, a pin already claimed by the firmware, or a
    board that does not have these names all produce ``(None, (), reason)`` and a
    session that runs without buttons.
    """
    if not getattr(config, "ENABLE_MAGTAG_BUTTONS", False):
        return None, (), "buttons disabled in config"
    pins = []
    buttons = []
    try:
        for action, setting in BUTTON_ALIASES:
            alias = getattr(config, setting, None)
            if not alias:
                raise ValueError("no pin alias for the " + action + " button")
            pin = digitalio.DigitalInOut(getattr(board, alias))
            pin.direction = digitalio.Direction.INPUT
            pin.pull = digitalio.Pull.UP
            pins.append(pin)
            # Bound late on purpose: ``pin`` is rebound each iteration, so the
            # reader has to close over this button's own object rather than the
            # loop variable.
            buttons.append((action, (lambda held: lambda: not held.value)(pin)))
        pad = ButtonPad(
            buttons,
            debounce_seconds=config.BUTTON_DEBOUNCE_SECONDS,
            minimum_interval_seconds=config.BUTTON_MINIMUM_INTERVAL_SECONDS,
        )
    except Exception as button_error:  # noqa: BLE001 - degraded, not fatal
        for pin in pins:
            try:
                pin.deinit()
            except Exception:
                pass
        detail = str(button_error)
        logger({"event": "dev_display_buttons_unavailable", "detail": detail,
                "keyboard_navigation_unaffected": True})
        return None, (), detail
    logger({
        "event": "dev_display_buttons_ready",
        "actions": [action for action, _ in BUTTON_ALIASES],
        "aliases": [getattr(config, setting) for _, setting in BUTTON_ALIASES],
        "debounce_seconds": config.BUTTON_DEBOUNCE_SECONDS,
        "minimum_interval_seconds": config.BUTTON_MINIMUM_INTERVAL_SECONDS,
    })
    return pad, tuple(pins), None


uart = None
display = None
error = None


def draw_local(screen, name, full=False):
    """Draw one of this board's own startup screens. Never raises. V1.6.

    A screen that cannot be drawn must not be the reason a panel that could have
    drawn a document does not run, so every failure here is reported and stepped
    over.
    """
    if display is None:
        return False
    try:
        display.begin_refresh(render_viewport(screen), full=full)
        display.wait_until_idle(config.UART_DISPLAY_BUSY_TIMEOUT_SECONDS)
    except Exception as screen_error:  # noqa: BLE001 - reported, not swallowed
        logger({"event": "display_startup_screen_failed", "screen": name,
                "detail": str(screen_error)})
        return False
    logger({"event": "display_startup_screen", "screen": name})
    return True


# The display is constructed *first*, ahead of the UART, and that order is the
# whole of why a wiring fault is now visible. Standalone has no console, so a
# failure the panel could have shown and did not is a failure nobody sees.
#
# Fenced off from the serve loop for the same reason as on the Fruit Jam: the
# filesystem was never remounted, so a construction failure leaves the board
# writable, autoreloading, and restartable without safe mode.
try:
    display = UC8151DisplayAdapter(config, config.PHYSICAL_TEST_MODE)
    display.initialize()
except Exception as construction_error:  # noqa: BLE001 - reported, not swallowed
    error = str(construction_error)
    display = None
    logger({"event": "dev_display_construction_failed", "detail": error,
            "stage": "display", "filesystem_remounted": False,
            "guard_written": False})

if display is not None:
    # Before a single byte is read. Both boards cold boot together under one-cable
    # power, so this is what the writer looks at while the Fruit Jam is mounting a
    # card and restoring their document -- work it cannot report over a link that
    # is not up yet. ``full`` because this is the first image of the session and
    # the panel has no differential state to trust.
    draw_local(starting_screen(), "STARTING", full=True)
    try:
        uart = busio.UART(
            tx=getattr(board, config.UART_TX_PIN_ALIAS),
            rx=getattr(board, config.UART_RX_PIN_ALIAS),
            baudrate=config.UART_BAUD,
            timeout=0,
            receiver_buffer_size=256,
        )
    except Exception as construction_error:  # noqa: BLE001 - reported, not swallowed
        error = str(construction_error)
        logger({"event": "dev_display_construction_failed", "detail": error,
                "stage": "uart", "filesystem_remounted": False,
                "guard_written": False})
        draw_local(fault_screen(error), "FAULT")

sessions = 0
buttons = None
button_detail = None
if display is not None and uart is not None:
    # After the display, and outside its try: a board that cannot claim its
    # buttons is still a board that can draw, and the writer still has a
    # keyboard. Degraded, reported, and started anyway.
    buttons, button_pins, button_detail = build_button_pad(logger)
    logger({"event": "dev_display_ready", "profile": PROFILE,
            "mode": config.PHYSICAL_TEST_MODE,
            "rx_alias": config.UART_RX_PIN_ALIAS,
            "tx_alias": config.UART_TX_PIN_ALIAS, "baud": config.UART_BAUD,
            "startup_wait_seconds": STARTUP_WAIT_SECONDS,
            "buttons": buttons is not None, "button_detail": button_detail})

    def new_session():
        parser = FrameParser()
        outbox = StatusQueue(config.UART_STATUS_QUEUE_CAPACITY)
        scheduler = AckDisplayScheduler(
            parser, display, render_viewport, outbox, time.monotonic,
        )
        return parser, outbox, scheduler, RefreshStats()

    parser, outbox, scheduler, stats = new_session()
    inflight_started = None
    # V1.6. The one local screen the serve loop may draw, and it may draw it
    # once. Anything the Fruit Jam sends supersedes it permanently.
    started_waiting_at = time.monotonic()
    waiting_screen_drawn = False
    bytes_received = 0
    bytes_sent = 0
    buttons_sent = 0
    buttons_dropped = 0
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
            if buttons is not None:
                # Polled before the scheduler runs, so a press taken this pass
                # leaves on this pass's outbox drain rather than waiting a lap.
                for action, ordinal, pressed_ms in buttons.poll(time.monotonic()):
                    if len(outbox) >= outbox.capacity - BUTTON_OUTBOX_HEADROOM:
                        buttons_dropped += 1
                        logger({"event": "dev_display_button_dropped",
                                "action": action, "ordinal": ordinal,
                                "outbox_depth": len(outbox)})
                        continue
                    outbox.offer(BUTTON_EVENT, scheduler.displayed_revision, {
                        "action_code": ACTION_CODES[action],
                        "ordinal": ordinal,
                        "pressed_ms": pressed_ms,
                    })
                    buttons_sent += 1
                    logger({"event": "dev_display_button_pressed",
                            "action": action, "ordinal": ordinal})
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
            if (
                not waiting_screen_drawn
                and scheduler.last_input_sequence is None
                and scheduler.pending is None
                and scheduler.ready_to_start is None
                and scheduler.inflight is None
                and not display.is_busy()
                and time.monotonic() - started_waiting_at > STARTUP_WAIT_SECONDS
            ):
                # Nothing has arrived on the link at all -- not even a handshake --
                # for longer than a cold boot has ever taken. Say so, once. Every
                # condition above is a guarantee that the panel is idle and the
                # scheduler owns no frame, so this can never cut across a refresh
                # the writer's words are in.
                waiting_screen_drawn = True
                draw_local(waiting_screen(), "WAITING")
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
                    "button_frames_sent": buttons_sent,
                    "button_frames_dropped": buttons_dropped,
                }
                summary.update(stats.describe())
                if buttons is not None:
                    summary.update(buttons.summary())
                logger(summary)
                # Ready for the next Fruit Jam start with no reset and no guard
                # to clear. Revisions restart from zero, so the parser and
                # scheduler are rebuilt rather than carried over.
                parser, outbox, scheduler, stats = new_session()
                inflight_started = None
                started_waiting_at = time.monotonic()
                waiting_screen_drawn = False
                bytes_received = 0
                bytes_sent = 0
                buttons_sent = 0
                buttons_dropped = 0
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
        # V1.6. The Fruit Jam is told over UART, which is exactly the channel a
        # transport fault may have taken away, so the panel is told too. On a
        # standalone device this is the only report that reaches anybody.
        try:
            display.wait_until_idle(config.UART_DISPLAY_BUSY_TIMEOUT_SECONDS)
        except Exception:
            pass
        draw_local(fault_screen(error), "FAULT")

# No guard is written, no evidence file is produced, and nothing is remounted:
# the next start needs no cleanup, no deletion, and no safe mode.
logger({"event": "dev_display_stopped", "detail": error, "profile": PROFILE,
        "sessions_served": sessions, "restartable": True,
        "guard_written": False, "filesystem_remounted": False,
        "buttons": buttons is not None, "button_detail": button_detail,
        "button_presses": None if buttons is None else buttons.presses,
        "button_bounces_rejected": (
            None if buttons is None else buttons.bounces_rejected),
        "button_repeats_suppressed": (
            None if buttons is None else buttons.repeats_suppressed)})
