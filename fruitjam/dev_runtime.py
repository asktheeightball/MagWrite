"""The MagWrite runtime on the Fruit Jam, in either of its two profiles.

This is **not** a physical-verification harness. It is the product path:

    keyboard -> authoritative Fruit Jam editor -> UART -> MagTag

``STANDALONE`` is the shipped default from V1.6 — the writing appliance, started
by connecting one USB-C cable, with no console, no host-mounted volume, no
operator, and no stop. ``DEVELOPMENT`` is the same runtime on a bench with two
consoles, opted into with ``ENABLE_DEV_RUNTIME``.

The profile changes six things and nothing else, all of them decided in one block
below: the idle, session, event, viewport-frame, and protocol-frame bounds, and
whether the back gesture at the main menu is a stop. The appliance is not a
reduced build — it is the same editor, shell, storage, transport, and buttons,
with the bounds that exist to end a *run* removed. See ``docs/STANDALONE.md``.

The file keeps its name, and so do its diagnostics. ``dev_runtime_ready``,
``dev_runtime_session_summary``, and ``dev_runtime_stopped`` are the vocabulary
every physical evidence file in this repository is written in, and renaming them
would make the record harder to read to make a filename tidier. What the console
says instead is which profile it is running, in the ready line and in the summary.

The everyday way to bring the known-working product path up on the bench:

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

Under the shell, added in V1.3, that gesture means **back**: from V1.5 it
checkpoints the document and lands directly on the main menu, and pressed again
there it is the clean stop it has always been. With ``ENABLE_SHELL`` off it stops
immediately from anywhere, exactly as it did before. Ctrl-S saves immediately in
either case. After a clean stop the board is immediately restartable: press
reset, press Ctrl-D at the REPL, or just save a file over USB.

The **MagTag's four buttons** are the primary shell controls from V1.5, over the
return UART this runtime already had: menu, up, down, select. The keyboard keeps
every shell key it had as a fallback, but nothing in the product flow needs it —
a writer navigates with their thumbs and types with their hands.

Under one-cable power the **start order is gone**. The MagTag is fed from a Fruit
Jam USB-A host port, which carries no 5 V while the Fruit Jam is held in reset, so
"start the MagTag first" is not an instruction that can be followed: both boards
cold boot together and the Fruit Jam usually wins, having no e-paper panel to
initialise. The handshake therefore waits. It is re-sent every
``DISPLAY_HANDSHAKE_RETRY_SECONDS`` until the panel answers, logging
``live_waiting_for_display`` while it does, and a restored document sits
untouched throughout. One unanswered HELLO is no longer a stopped session.

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
from magwrite_transport.live_session import (
    HELLO_RETRY_SECONDS, LiveTypingSession,
)
from magwrite_transport.pacing import DisplayPacer
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE, VERSION
from magwrite_transport.shell import Shell

DEV_RUNTIME_MODE = "FRUITJAM_DEV_RUNTIME"
STANDALONE_MODE = "FRUITJAM_STANDALONE"
PROFILE_STANDALONE = "STANDALONE"
PROFILE_DEVELOPMENT = "DEVELOPMENT"

# Development sessions are operator-paced and open-ended, so the transport
# budgets are raised far above the certification ceilings rather than removed:
# an unbounded counter on a microcontroller is still a bug, just a slower one.
DEV_MAX_VIEWPORT_FRAMES = 100000
DEV_MAX_PROTOCOL_FRAMES = 200000


def _select_profile():
    """Which of the two profiles this board's config asks for.

    Development is checked first because it is the one that has to be *asked*
    for: it ships disabled, and a board deliberately armed for the bench must not
    be quietly handed the appliance instead. Standalone is the fall-through,
    which is what makes it the default.
    """
    if (
        getattr(config, "ENABLE_DEV_RUNTIME", False)
        and getattr(config, "DEV_RUNTIME_MODE", "DISABLED") == DEV_RUNTIME_MODE
    ):
        return PROFILE_DEVELOPMENT
    if (
        getattr(config, "ENABLE_STANDALONE", False)
        and getattr(config, "STANDALONE_MODE", "DISABLED") == STANDALONE_MODE
    ):
        return PROFILE_STANDALONE
    return None


PROFILE = _select_profile()
STANDALONE = PROFILE == PROFILE_STANDALONE
if PROFILE is None:
    raise RuntimeError("no Fruit Jam runtime is enabled")

# The profile's whole effect, in one place. Everything below this block is
# identical for both, which is the point: the appliance is not a reduced build of
# the bench rig, it is the same code with the bounds that end a *run* removed and
# the stop that ends a *session* taken away.
if STANDALONE:
    IDLE_TIMEOUT_SECONDS = getattr(
        config, "STANDALONE_IDLE_TIMEOUT_SECONDS", None)
    SESSION_TIMEOUT_SECONDS = getattr(
        config, "STANDALONE_SESSION_TIMEOUT_SECONDS", None)
    MAX_EVENTS = getattr(config, "STANDALONE_MAX_EVENTS", None)
    MAX_VIEWPORT_FRAMES = getattr(config, "STANDALONE_MAX_VIEWPORT_FRAMES", None)
    MAX_PROTOCOL_FRAMES = getattr(config, "STANDALONE_MAX_PROTOCOL_FRAMES", None)
    KEYBOARD_OPEN_ATTEMPTS = getattr(
        config, "STANDALONE_KEYBOARD_OPEN_ATTEMPTS", None)
    # No keyboard is a degraded mode with a panel that says so, never a stop.
    KEYBOARD_OPTIONAL = True
    # There is no stop to take on a device with one power cable.
    ALLOW_EXIT = False
else:
    IDLE_TIMEOUT_SECONDS = config.DEV_RUNTIME_IDLE_TIMEOUT_SECONDS
    SESSION_TIMEOUT_SECONDS = config.DEV_RUNTIME_SESSION_TIMEOUT_SECONDS
    MAX_EVENTS = config.DEV_RUNTIME_MAX_EVENTS
    MAX_VIEWPORT_FRAMES = DEV_MAX_VIEWPORT_FRAMES
    MAX_PROTOCOL_FRAMES = DEV_MAX_PROTOCOL_FRAMES
    KEYBOARD_OPEN_ATTEMPTS = getattr(
        config, "STANDALONE_KEYBOARD_OPEN_ATTEMPTS", None)
    KEYBOARD_OPTIONAL = True
    ALLOW_EXIT = True

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
        shell = Shell(log=log, allow_exit=ALLOW_EXIT)
    session = LiveTypingSession(
        time.monotonic, log,
        adapter_factory=lambda queue: UsbKeyboardAdapter(
            backend, queue, log,
            poll_budget=config.USB_KEYBOARD_POLL_BUDGET,
            max_events=MAX_EVENTS,
            layout=config.USB_KEYBOARD_LAYOUT,
            now=time.monotonic(),
            max_open_attempts=KEYBOARD_OPEN_ATTEMPTS,
            optional=KEYBOARD_OPTIONAL,
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
        # One-cable power: the MagTag hangs off a Fruit Jam USB-A port, so it
        # cannot be started first and both boards come up together. The
        # handshake is retried at this interval until the panel answers, rather
        # than failed after one attempt.
        # ``getattr`` with the module's own default rather than a direct read: a
        # board whose config.py predates this setting must still start by itself,
        # which is the entire point of the phase. It would be perverse for the
        # fix for "the device does not switch on" to refuse to switch on.
        hello_retry_seconds=getattr(
            config, "DISPLAY_HANDSHAKE_RETRY_SECONDS", HELLO_RETRY_SECONDS),
        idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
        session_timeout_seconds=SESSION_TIMEOUT_SECONDS,
        max_viewport_frames=MAX_VIEWPORT_FRAMES,
        max_protocol_frames=MAX_PROTOCOL_FRAMES,
        # The writer has no console, so "is there a keyboard" has to be
        # answerable from the panel: one character in every status field, and a
        # line on the main menu.
        show_keyboard_state=True,
        persistence=persistence,
        shell=shell,
        # V1.4. ``None`` on a degraded card, which is a supported mode: the four
        # menu items then route into the one document exactly as they did in
        # V1.3, and the writer is told NO CARD rather than misled.
        library=persistence.library,
    )
    if persistence.recovery is not None and persistence.recovery.recovered:
        # The catalogue entry travels with the snapshot, so the restored session
        # comes back in the mode the document belongs to rather than in whatever
        # the menu was pointing at -- the one gap V1.3 recorded and deferred.
        session.restore(persistence.recovery.snapshot, persistence.document_entry)
    elif shell is not None:
        # Nothing survived, so the writer was not writing. Open at the menu.
        shell.restore(False)
except Exception as construction_error:  # noqa: BLE001 - reported, not swallowed
    error = str(construction_error)
    log({"event": "dev_runtime_construction_failed", "detail": error,
         "filesystem_remounted": False, "guard_written": False})

if session is not None:
    ready = {"event": "dev_runtime_ready", "profile": PROFILE,
             "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
             "session_timeout_seconds": SESSION_TIMEOUT_SECONDS,
             "tx_alias": config.UART_TX_PIN_ALIAS,
             "rx_alias": config.UART_RX_PIN_ALIAS, "baud": config.UART_BAUD,
             "startup_delay_seconds": config.STARTUP_DELAY_SECONDS,
             "display_handshake_retry_seconds": session.hello_retry_seconds,
             "display_handshake": "RETRIES_UNTIL_READY",
             "keyboard_layout": config.USB_KEYBOARD_LAYOUT,
             "stop_key": "ESCAPE", "stop_key_alternate": "APPLICATION",
             "save_key": "CTRL-S"}
    ready.update(mount_result.summary())
    ready["save_state"] = persistence.state
    if shell is None:
        ready["stop_from"] = "ANYWHERE"
    else:
        # The same gesture and the same keys. Under the shell it means back, so
        # the stop is the one taken at the root; inside a document it checkpoints
        # and returns to the menu instead of ending the session.
        ready.update(shell.summary())
        ready["stop_from"] = "MAIN_MENU" if ALLOW_EXIT else "NOWHERE"
        ready["back_key"] = "ESCAPE"
        # V1.5. Reported at startup so the console says, before a single press,
        # which control surface the operator should expect to work.
        ready["buttons"] = "MAGTAG_MENU_UP_DOWN_SELECT"
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
     "profile": PROFILE, "restartable": True, "guard_written": False,
     "filesystem_remounted": False})
