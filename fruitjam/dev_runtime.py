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

Escape, HID usage ``0x29``, is the finish gesture; Keyboard Application, ``0x65``,
is the same control for boards whose Escape is only on an Fn layer. On the
EPOMAKER TH40 used for this phase it is Escape that works -- two sessions on
2026-07-29 confirmed that its Application-labelled key sends a modifier with no
usage byte, so nothing reaches the board. See ``docs/DEVELOPMENT_RUNTIME.md``.

Under the shell, added in V1.3, that gesture means **back**: it leaves the editor
through the save screen, and pressed again at the main menu it is the clean stop
it has always been. With ``ENABLE_SHELL`` off it stops immediately from anywhere,
exactly as it did before. Ctrl-S saves immediately in either case. After a clean
stop the board is immediately restartable: press reset, press Ctrl-D at the REPL,
or just save a file over USB.

Persistence, added in V1.2, does not compromise any of the above. The microSD
card is a separate filesystem from CIRCUITPY, so mounting it needs no
``storage.remount``: the host keeps the drive writable, autoreload stays on, and
saving a file still restarts the board. A missing or unmountable card is a
reported degraded mode, never a refusal to start -- the editor runs and the panel
shows ``X`` rather than pretending to save.
"""

import time

import config
from magwrite_transport.diagnostics import log
from magwrite_transport.latency import LatencyRecorder
from magwrite_transport.live_session import LiveTypingSession
from magwrite_transport.pacing import DisplayPacer
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE, VERSION
from magwrite_transport.shell import Shell

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
import digitalio
import storage as storage_module

from magwrite_transport.storage_bringup import bring_up
from magwrite_transport.usb_host_backend import UsbHostKeyboardBackend
from magwrite_transport.usb_keyboard_adapter import UsbKeyboardAdapter

try:
    import sdcardio
except ImportError:  # pragma: no cover - build without the SD driver
    # Reported through the ordinary degraded path rather than raised: a firmware
    # build without sdcardio is a card that cannot be mounted, which the runtime
    # already knows how to survive.
    sdcardio = None

uart = None
session = None
result = "STOPPED"
error = None
persistence = None
mount_result = None
shell = None

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
    # Persistence is brought up before the session so a recovered document can be
    # loaded into the editor the session is about to start driving. It cannot
    # raise: an absent, unformatted, or unmountable card returns a controller
    # with no store, and the editor runs exactly as it did before V1.2.
    #
    # Note this needs no ``storage.remount``. The card is a separate filesystem
    # from CIRCUITPY, so persistence does not cost the development runtime its
    # defining property: the host keeps the drive writable and saving a file
    # still restarts the board.
    persistence, mount_result = bring_up(
        config, time.monotonic(), log, board_module=board, sdcardio=sdcardio,
        storage_module=storage_module, busio=busio, digitalio=digitalio,
    )
    # The shell is constructed before the session so the session opens with a
    # screen already decided. It owns no document and no store: it decides where
    # the writer is and where input goes, and the one editor below outlives every
    # transition it makes.
    if getattr(config, "ENABLE_SHELL", False):
        shell = Shell(log=log)
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
        persistence=persistence,
        shell=shell,
    )
    if persistence.recovery is not None and persistence.recovery.recovered:
        session.restore(persistence.recovery.snapshot)
    elif shell is not None:
        # Nothing survived, so the writer was not writing. Open at the menu.
        shell.restore(False)
except Exception as construction_error:  # noqa: BLE001 - reported, not swallowed
    error = str(construction_error)
    log({"event": "dev_runtime_construction_failed", "detail": error,
         "filesystem_remounted": False, "guard_written": False})

if session is not None:
    ready = {"event": "dev_runtime_ready", "tx_alias": config.UART_TX_PIN_ALIAS,
             "rx_alias": config.UART_RX_PIN_ALIAS, "baud": config.UART_BAUD,
             "startup_delay_seconds": config.STARTUP_DELAY_SECONDS,
             "keyboard_layout": config.USB_KEYBOARD_LAYOUT,
             "stop_key": "ESCAPE", "stop_key_alternate": "APPLICATION",
             "save_key": "CTRL-S"}
    ready.update(mount_result.summary())
    ready["save_state"] = persistence.state
    if shell is None:
        ready["stop_from"] = "ANYWHERE"
    else:
        # The same gesture and the same keys. Under the shell it means back, so
        # the stop is the one taken at the root; inside a document it leaves the
        # editor through the save screen instead of ending the session.
        ready.update(shell.summary())
        ready["stop_from"] = "MAIN_MENU"
        ready["back_key"] = "ESCAPE"
    log(ready)
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
