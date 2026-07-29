"""Repeatable MagWrite development runtime on the Fruit Jam.

This is **not** a physical-verification harness. It is the everyday way to bring
the known-working product path up on the bench:

    wired USB keyboard -> authoritative Fruit Jam editor -> UART -> MagTag

Everything that runs is the same host-tested code the verified milestone used:
the same ``LiveTypingSession``, editor, layout, viewport builder, protocol, and
acknowledgement tracker, with the adaptive pacer and the TH40 keyboard layout.
The Fruit Jam stays authoritative for the document, the cursor, and both
revisions; the MagTag stays display-only.

What is deliberately absent, and why
------------------------------------

The guarded harnesses in this repository exist to produce evidence *once*. That
is why they claim a one-shot ``.started`` guard, refuse to run a second time,
remount the filesystem read-write so the guard can be persisted, disable
autoreload, and end by trapping the board in a sleep loop. Every one of those is
correct for a certification run and wrong for development, where the whole point
is to start the thing, watch it, change something, and start it again.

So this runtime:

* creates, deletes, and checks **no** guard file of any kind;
* never calls ``storage.remount``, so CIRCUITPY stays writable by the host and
  saving a file is all it takes to restart;
* leaves ``supervisor.runtime.autoreload`` alone, for the same reason;
* claims no PASS or FAIL and produces no evidence file — it prints ordinary
  bounded diagnostics and a session summary;
* lifts the certification frame ceilings, which exist to bound a one-shot run.

The one-shot harnesses are untouched and stay available for the next real
verification milestone.

Press the Application (menu) key, HID usage ``0x65``, to stop cleanly. Escape
also stops, but the EPOMAKER TH40 can only reach it through an Fn layer that
switches the keyboard out of USB mode, so Application is the usable control.
After a clean stop the board is immediately restartable: press reset, press
Ctrl-D at the REPL, or just save a file over USB.
"""

import time

import config
from magwrite_transport.diagnostics import log
from magwrite_transport.latency import LatencyRecorder
from magwrite_transport.live_session import LiveTypingSession
from magwrite_transport.pacing import DisplayPacer
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE, VERSION

DEV_RUNTIME_MODE = "FRUITJAM_DEV_RUNTIME"

# Development sessions are operator-paced and open-ended, so the transport
# budgets are raised far above the certification ceilings rather than removed:
# an unbounded counter on a microcontroller is still a bug, just a slower one.
DEV_MAX_VIEWPORT_FRAMES = 100000
DEV_MAX_PROTOCOL_FRAMES = 200000

if not (
    getattr(config, "ENABLE_DEV_RUNTIME", False)
    and getattr(config, "DEV_RUNTIME_MODE", "DISABLED") == DEV_RUNTIME_MODE
):
    raise RuntimeError("Fruit Jam development runtime is not enabled")
if not config.UART_TX_PIN_ALIAS or not config.UART_RX_PIN_ALIAS:
    raise RuntimeError("both confirmed UART pin aliases are required")
if VERSION != 1 or MAX_PAYLOAD_SIZE != 192:
    raise RuntimeError("protocol constants do not match the verified wire format")

# Imported only after the gate, and only here: importing them is what makes this
# file undiagnosable on the host, so nothing above this line may need them.
import board
import busio

from magwrite_transport.usb_host_backend import UsbHostKeyboardBackend
from magwrite_transport.usb_keyboard_adapter import UsbKeyboardAdapter

uart = None
session = None
result = "STOPPED"
error = None

# Construction is fenced off from the run loop because the two fail for
# different reasons and want different reporting. Either way the filesystem was
# never remounted, so a failure here leaves the board exactly as the host found
# it: writable, autoreloading, and restartable without safe mode.
try:
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
            max_events=config.DEV_RUNTIME_MAX_EVENTS,
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
        idle_timeout_seconds=config.DEV_RUNTIME_IDLE_TIMEOUT_SECONDS,
        session_timeout_seconds=config.DEV_RUNTIME_SESSION_TIMEOUT_SECONDS,
        max_viewport_frames=DEV_MAX_VIEWPORT_FRAMES,
        max_protocol_frames=DEV_MAX_PROTOCOL_FRAMES,
    )
except Exception as construction_error:  # noqa: BLE001 - reported, not swallowed
    error = str(construction_error)
    log({"event": "dev_runtime_construction_failed", "detail": error,
         "filesystem_remounted": False, "guard_written": False})

if session is not None:
    log({"event": "dev_runtime_ready", "tx_alias": config.UART_TX_PIN_ALIAS,
         "rx_alias": config.UART_RX_PIN_ALIAS, "baud": config.UART_BAUD,
         "startup_delay_seconds": config.STARTUP_DELAY_SECONDS,
         "keyboard_layout": config.USB_KEYBOARD_LAYOUT,
         "stop_key": "APPLICATION"})
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
            time.sleep(0.002)
        result = "COMPLETE"
    except KeyboardInterrupt:
        # Ctrl-C at the console is a legitimate development stop, not a fault.
        result = "INTERRUPTED"
    except Exception as run_error:  # noqa: BLE001 - reported, not swallowed
        error = str(run_error)
        result = "ERROR"
        session.stop_reason = error

    summary = session.summary(result)
    summary["event"] = "dev_runtime_session_summary"
    log(summary)

# No guard is written, no evidence file is produced, and nothing is remounted:
# the next start needs no cleanup, no deletion, and no safe mode.
log({"event": "dev_runtime_stopped", "result": result, "detail": error,
     "restartable": True, "guard_written": False,
     "filesystem_remounted": False})
