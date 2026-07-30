"""V1.6: the minimum standalone workflow.

Everything here is a property of the device a writer switches on by connecting
one power cable — no console, no host-mounted volume, no operator, and nothing to
press before it works. The V1.5 device was a bench rig that happened to run the
product; these tests are the difference.

Four of them exist because the corresponding failure would have been a device
that does not work rather than a test that goes red:

* a board switched on before its keyboard was plugged in gave up after thirty
  seconds and latched, so that keyboard was never seen again;
* the idle bound ended a session after half an hour of a writer thinking, and
  the session ending left a panel nothing but the reset button could move;
* Escape at the main menu ended the session outright — one keystroke that
  switches the device off, and no keystroke that switches it back on;
* a stored document the editor refused took the whole runtime down during
  construction, and the empty editor left behind would have been checkpointed
  over the writer's real document by the next threshold.

The device-entry assertions are static for the reason the rest of this suite's
are: ``dev_runtime`` and ``dev_display_runtime`` import ``board`` and cannot be
imported on the host.
"""

import ast
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAGTAG = os.path.join(ROOT, "magtag")
sys.path.insert(0, MAGTAG)
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from fake_filesystem import FakeFileSystem
from keyboard_simulator import (
    FakeKeyboardBackend, KeyboardLink, finish, press_kind, type_characters,
)
from magwrite.display_adapter import (
    ACTIVATION_MODES, APPROVED_TEST_MODES, STANDALONE_DISPLAY_MODE,
)
from magwrite.startup_screens import (
    fault_screen, starting_screen, waiting_screen,
)
from magwrite.viewport_message import ViewportMessage
from magwrite.viewport_renderer import render_viewport
from magwrite_transport.document_store import DocumentStore
from magwrite_transport.editor import ENTER, MultilineEditor
from magwrite_transport.journal import Snapshot
from magwrite_transport.live_session import (
    KEYBOARD_ABSENT_INDICATOR, LiveTypingSession,
)
from magwrite_transport.persistence import ACTION_NONE, PersistenceController
from magwrite_transport.shell import STATE_ERROR, STATE_MAIN_MENU, Shell
from magwrite_transport.shell_viewport import NO_KEYBOARD, menu_payload
from magwrite_transport.usb_device_state import (
    ERROR, NO_DEVICE, READY, UsbDeviceState,
)
from magwrite_transport.usb_hid_descriptors import (
    EndpointInitializationError, UsbKeyboardDisconnected, UsbKeyboardNotFound,
)
from magwrite_transport.usb_keyboard_adapter import (
    UsbKeyboardAdapter, UsbKeyboardAdapterError,
)
from magwrite_transport.editor import BoundedEventQueue

FRUITJAM_ENTRY = ("fruitjam", "dev_runtime.py")
MAGTAG_ENTRY = ("magtag", "dev_display_runtime.py")


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


def decode(payload):
    return ViewportMessage.decode(1, payload)


class LateKeyboardBackend(FakeKeyboardBackend):
    """Nothing on the port until ``available_at``, then an ordinary keyboard."""

    def __init__(self, available_at, clock, **options):
        FakeKeyboardBackend.__init__(self, clock=clock, **options)
        self.available_at = available_at
        self.refusals = 0

    def open(self):
        if self.clock() < self.available_at:
            self.refusals += 1
            raise UsbKeyboardNotFound("no device on the USB host port")
        return FakeKeyboardBackend.open(self)


class KeyboardAttemptBudgetTest(unittest.TestCase):
    """The bound that made "no keyboard yet" permanent."""

    def test_the_bounded_budget_still_latches_for_a_harness(self):
        state = UsbDeviceState(0.0, None, retry_interval=1.0, max_attempts=3)
        now = 0.0
        for _ in range(3):
            self.assertTrue(state.retry_due(now))
            state.begin_attempt(now)
            state.not_found(now)
            now += 1.0
        self.assertTrue(state.exhausted)
        self.assertEqual(state.state, ERROR)
        self.assertFalse(state.retry_due(now + 1000.0))

    def test_an_unbounded_budget_never_latches(self):
        state = UsbDeviceState(0.0, None, retry_interval=1.0, max_attempts=None)
        now = 0.0
        for _ in range(500):
            self.assertTrue(state.retry_due(now))
            state.begin_attempt(now)
            state.not_found(now)
            now += 1.0
        self.assertFalse(state.exhausted)
        self.assertEqual(state.state, NO_DEVICE)
        self.assertTrue(state.retry_due(now))

    def test_the_rate_bound_is_untouched_by_an_unbounded_budget(self):
        """Unbounded in count is not unbounded in work. Still one per second."""
        state = UsbDeviceState(0.0, None, retry_interval=1.0, max_attempts=None)
        state.begin_attempt(0.0)
        state.not_found(0.0)
        self.assertFalse(state.retry_due(0.5))
        self.assertFalse(state.retry_due(0.99))
        self.assertTrue(state.retry_due(1.0))

    def test_a_keyboard_plugged_in_late_still_opens(self):
        log = []
        backend = FakeKeyboardBackend(open_error=UsbKeyboardNotFound("none"))
        adapter = UsbKeyboardAdapter(
            backend, BoundedEventQueue(16), log.append,
            state=UsbDeviceState(0.0, log.append, retry_interval=1.0,
                                 max_attempts=None),
        )
        now = 0.0
        for _ in range(120):                       # twice the old budget
            adapter.connect(now)
            now += 1.0
        self.assertFalse(adapter.ready)
        backend.open_error = None                  # the writer plugs it in
        self.assertTrue(adapter.connect(now))
        self.assertTrue(adapter.ready)
        self.assertEqual(adapter.state.state, READY)

    def test_a_bounded_adapter_would_have_missed_it(self):
        """The defect, stated as the test that would have caught it."""
        backend = FakeKeyboardBackend(open_error=UsbKeyboardNotFound("none"))
        adapter = UsbKeyboardAdapter(
            backend, BoundedEventQueue(16), lambda record: None,
            max_open_attempts=30,
        )
        now = 0.0
        for _ in range(120):
            adapter.connect(now)
            now += 1.0
        backend.open_error = None
        self.assertFalse(adapter.connect(now))
        self.assertFalse(adapter.ready)


class OptionalKeyboardTest(unittest.TestCase):
    """An unusable or vanished keyboard is a degraded mode, not a stop."""

    def adapter(self, backend, optional):
        return UsbKeyboardAdapter(
            backend, BoundedEventQueue(16), lambda record: None,
            optional=optional, max_open_attempts=None,
        )

    def test_an_unusable_device_is_fatal_for_a_harness(self):
        backend = FakeKeyboardBackend(
            open_error=EndpointInitializationError("no usable boot keyboard")
        )
        with self.assertRaises(UsbKeyboardAdapterError):
            self.adapter(backend, optional=False).connect(0.0)

    def test_an_unusable_device_is_survivable_for_the_appliance(self):
        backend = FakeKeyboardBackend(
            open_error=EndpointInitializationError("no usable boot keyboard")
        )
        adapter = self.adapter(backend, optional=True)
        self.assertFalse(adapter.connect(0.0))
        self.assertFalse(adapter.ready)
        self.assertEqual(adapter.open_failures, 1)
        # And a real keyboard put in the same port afterwards is still found.
        backend.open_error = None
        self.assertTrue(adapter.connect(2.0))
        self.assertTrue(adapter.ready)

    def test_a_read_failure_is_a_disconnect_rather_than_a_stop(self):
        class HostileBackend(FakeKeyboardBackend):
            def read_report(self):
                raise EndpointInitializationError("transfer stalled")

        backend = HostileBackend()
        fatal = self.adapter(backend, optional=False)
        fatal.connect(0.0)
        with self.assertRaises(UsbKeyboardAdapterError):
            fatal.poll(0.0)

        backend = HostileBackend()
        adapter = self.adapter(backend, optional=True)
        adapter.connect(0.0)
        self.assertEqual(adapter.poll(0.0), 0)
        self.assertFalse(adapter.ready)
        self.assertEqual(adapter.read_failures, 1)

    def test_an_unplugged_keyboard_clears_its_held_keys(self):
        backend = FakeKeyboardBackend(disconnect_after=0)
        adapter = self.adapter(backend, optional=True)
        adapter.connect(0.0)
        adapter.poll(0.0)
        self.assertFalse(adapter.ready)
        self.assertGreaterEqual(adapter.translator.resets, 1)


class UnboundedRunTest(unittest.TestCase):
    """The bounds that ended a run, and have no meaning on an appliance."""

    def session(self, **options):
        return LiveTypingSession(
            lambda: self.now, lambda record: None,
            adapter=FakeKeyboardBackend(), **options
        )

    def setUp(self):
        self.now = 0.0

    def test_no_timeout_fires_when_both_are_none(self):
        link = KeyboardLink(
            reports=[], idle_timeout_seconds=None,
            session_timeout_seconds=None,
        )
        link.run_until(5.0)
        # Then jump the clock far past both retired bounds and keep servicing.
        link.clock.now += 86400.0
        for _ in range(20):
            link.step()
        self.assertFalse(link.session.complete)
        self.assertIsNone(link.session.stop_reason)

    def test_the_bounded_session_still_gives_up(self):
        link = KeyboardLink(
            reports=[], idle_timeout_seconds=5.0, session_timeout_seconds=None,
        )
        link.run_until(1.0)
        link.clock.now += 3600.0
        with self.assertRaises(Exception) as raised:
            for _ in range(20):
                link.step()
        self.assertIn("idle timeout", str(raised.exception))

    def test_none_frame_bounds_are_not_enforced(self):
        link = KeyboardLink(
            reports=type_characters("standalone"),
            max_viewport_frames=None, max_protocol_frames=None,
            idle_timeout_seconds=None, session_timeout_seconds=None,
        )
        link.run_until(20.0)
        self.assertGreater(link.session.viewport_frames_sent, 0)
        self.assertIn("standalone", link.session.editor.text)

    def test_the_verified_ceilings_are_still_the_defaults(self):
        """A harness that passes nothing keeps exactly what it was verified with."""
        from magwrite_transport.live_session import (
            MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES,
        )
        session = LiveTypingSession(
            lambda: 0.0, lambda record: None, adapter=FakeKeyboardBackend(),
        )
        self.assertEqual(session.max_viewport_frames, MAX_VIEWPORT_FRAMES)
        self.assertEqual(session.max_protocol_frames, MAX_PROTOCOL_FRAMES)
        self.assertEqual(session.idle_timeout_seconds, 600.0)


class TypingBeforeThePanelAnswersTest(unittest.TestCase):
    """A writer who is keen must not be able to switch the device off."""

    def link(self, characters):
        return KeyboardLink(
            reports=type_characters(characters),
            idle_timeout_seconds=None, session_timeout_seconds=None,
            shell=Shell(allow_exit=False), show_keyboard_state=True,
            # The panel is not powered for the first nine seconds, which is what
            # a measured cold boot actually took.
            display_ready_at=9.0, typing_interval_seconds=0.01,
        )

    def test_a_sentence_typed_into_a_booting_device_does_not_end_it(self):
        link = self.link(
            "the quick brown fox jumps over the lazy dog, again and again "
            "and again and again and again and again and again and again "
            "and again and again and again and again and again and again"
        )
        link.run_until(40.0)
        self.assertFalse(link.session.complete)
        self.assertGreater(link.session.hello_attempts, 1)
        self.assertGreater(link.session.keystrokes_dropped_waiting, 0)

    def test_what_was_queued_before_the_panel_is_still_applied(self):
        link = self.link("early")
        link.run_until(40.0)
        self.assertEqual(link.session.keystrokes_dropped_waiting, 0)
        self.assertFalse(link.session.complete)
        # Those keystrokes were typed at the menu, where they are correctly
        # ignored -- the point here is only that none of them was lost to a
        # queue that overflowed, and that the session is still running.
        self.assertGreater(link.session.shell_events, 0)

    def test_the_drop_is_named_once_rather_than_swallowed(self):
        link = self.link("x" * 200)
        link.run_until(40.0)
        named = link.events("live_input_dropped_waiting_for_display")
        self.assertEqual(len(named), 1)
        self.assertIn("queue_capacity", named[0])

    def test_an_overflow_after_the_panel_answers_is_still_fatal(self):
        """Only the wait is forgiving. A full queue while live is a real fault."""
        link = KeyboardLink(
            reports=type_characters("hello"), idle_timeout_seconds=None,
            session_timeout_seconds=None, shell=Shell(allow_exit=False),
        )
        link.run_until(2.0)
        self.assertEqual(link.session.phase, "LIVE")
        link.session.adapter.queue_overflows += 1
        with self.assertRaises(Exception) as raised:
            link.session._poll_keyboard = lambda now: (_ for _ in ()).throw(
                UsbKeyboardAdapterError("keyboard input queue overflow"))
            link.session.service()
        self.assertIn("queue overflow", str(raised.exception))


class NoStopOnAnApplianceTest(unittest.TestCase):
    """There is no gesture that switches the device off."""

    def test_back_at_the_menu_stops_a_bench_session(self):
        shell = Shell()
        self.assertTrue(shell.allow_exit)
        shell.back()
        self.assertTrue(shell.exiting)

    def test_back_at_the_menu_does_nothing_on_an_appliance(self):
        shell = Shell(allow_exit=False)
        for _ in range(5):
            shell.back()
        self.assertEqual(shell.state, STATE_MAIN_MENU)
        self.assertFalse(shell.exiting)
        self.assertEqual(shell.exits_refused, 5)

    def test_back_still_leaves_every_other_state(self):
        """Refusing the stop must not turn Escape into a dead key."""
        shell = Shell(allow_exit=False)
        shell.enter()                                   # JOURNAL -> editor
        shell.back()
        self.assertEqual(shell.state, STATE_MAIN_MENU)
        shell.fault("something")
        self.assertEqual(shell.state, STATE_ERROR)
        shell.back()
        self.assertEqual(shell.state, STATE_MAIN_MENU)

    def test_a_whole_escape_session_never_ends(self):
        link = KeyboardLink(
            reports=press_kind(ENTER) + type_characters("hello")
            + finish() + finish() + finish(),
            idle_timeout_seconds=None, session_timeout_seconds=None,
            shell=Shell(allow_exit=False), typing_interval_seconds=0.1,
        )
        link.run_until(30.0)
        self.assertFalse(link.session.complete)
        self.assertEqual(link.session.shell.state, STATE_MAIN_MENU)
        # And the words survived every one of those presses.
        self.assertIn("hello", link.session.editor.text)


class VisibleKeyboardStateTest(unittest.TestCase):
    """With no console, the panel is the only place this can be said."""

    def test_the_menu_says_so_in_words(self):
        shell = Shell()
        shell.note_keyboard_state(False)
        screen = decode(menu_payload(shell, "r", KEYBOARD_ABSENT_INDICATOR))
        self.assertIn(NO_KEYBOARD, screen.lines)
        self.assertTrue(screen.status.endswith(KEYBOARD_ABSENT_INDICATOR))
        # Every menu item is still on the panel; the notice took the spare row.
        for _mode, label in shell.items:
            self.assertTrue(any(label in line for line in screen.lines), label)

    def test_a_working_keyboard_says_nothing_at_all(self):
        shell = Shell()
        with_keyboard = decode(menu_payload(shell, "r"))
        self.assertNotIn(NO_KEYBOARD, with_keyboard.lines)
        self.assertFalse(with_keyboard.status.endswith(
            KEYBOARD_ABSENT_INDICATOR))

    def test_every_notice_character_is_drawable(self):
        """The defect this repeats: an indicator with no glyph raised KeyError."""
        shell = Shell()
        shell.note_keyboard_state(False)
        for screen in (
            decode(menu_payload(shell, "!", KEYBOARD_ABSENT_INDICATOR)),
            decode(menu_payload(shell, "x", KEYBOARD_ABSENT_INDICATOR)),
        ):
            render_viewport(screen)

    def test_the_status_field_still_fits_with_both_indicators(self):
        editor = MultilineEditor()
        from magwrite_transport.editor_viewport import EditorViewport
        viewport = EditorViewport()
        for _ in range(40):
            editor.note_visible_change()
        window = viewport.window(editor)
        text = viewport.status_text(editor, window, "r",
                                    KEYBOARD_ABSENT_INDICATOR)
        from magwrite.viewport_message import MAX_STATUS
        self.assertLessEqual(len(text), MAX_STATUS)
        self.assertTrue(text.endswith("r " + KEYBOARD_ABSENT_INDICATOR))

    def test_the_payload_is_unchanged_when_the_state_is_not_shown(self):
        """Off by default, so every measured payload and CRC-32 stays reachable."""
        quiet = KeyboardLink(reports=type_characters("ab") + finish())
        loud = KeyboardLink(reports=type_characters("ab") + finish(),
                            show_keyboard_state=True)
        quiet.run()
        loud.run()
        self.assertEqual(quiet.session.last_sent_payload,
                         loud.session.last_sent_payload)

    def test_a_late_keyboard_becomes_available_without_a_restart(self):
        """The physical check's last step, in simulation.

        No keyboard at power-on: the device reaches the menu and says so. The
        keyboard is connected afterwards, and writing works — with no reset, no
        power cycle, and no operator.
        """
        link = KeyboardLink(
            backend=None, reports=[], idle_timeout_seconds=None,
            session_timeout_seconds=None, show_keyboard_state=True,
            shell=Shell(allow_exit=False),
        )
        backend = LateKeyboardBackend(
            available_at=4.0, clock=link.clock,
            reports=type_characters("late") + press_kind(ENTER),
            interval_seconds=0.1,
        )
        link.backend = backend
        link.adapter.backend = backend
        link.adapter.state = UsbDeviceState(
            0.0, link.log, retry_interval=0.25, max_attempts=None)

        link.run_until(3.0)
        self.assertFalse(link.adapter.ready)
        self.assertGreater(backend.refusals, 1)
        menu = decode(link.session.last_sent_payload)
        self.assertIn(NO_KEYBOARD, menu.lines)

        link.run_until(30.0)
        self.assertTrue(link.adapter.ready)
        self.assertEqual(link.session.shell.keyboard_ready, True)
        self.assertIsNone(link.session.keyboard_indicator)
        self.assertFalse(link.session.complete)


class RefusedRestoreTest(unittest.TestCase):
    """A document the editor will not hold must not cost the writer anything."""

    def store(self, text):
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root="/sd/magwrite")
        store.open()
        store.checkpoint(Snapshot(1, 0, 0, text))
        return filesystem, store

    def session(self, snapshot, store, shell=None):
        controller = PersistenceController(store, 0.0, lambda record: None)
        session = LiveTypingSession(
            lambda: 0.0, lambda record: None, adapter=FakeKeyboardBackend(),
            persistence=controller, shell=shell,
        )
        return session, controller, session.restore(snapshot)

    def oversized(self):
        editor = MultilineEditor()
        return "z" * (editor.max_chars + 1)

    def test_an_acceptable_document_still_restores(self):
        _filesystem, store = self.store("ordinary words")
        shell = Shell(allow_exit=False)
        session, controller, restored = self.session(
            Snapshot(1, 0, 14, "ordinary words"), store, shell)
        self.assertTrue(restored)
        self.assertEqual(session.editor.text, "ordinary words")
        self.assertFalse(controller.held)

    def test_a_refused_document_does_not_raise(self):
        _filesystem, store = self.store("ordinary words")
        session, _controller, restored = self.session(
            Snapshot(1, 0, 0, self.oversized()), store, Shell(allow_exit=False))
        self.assertFalse(restored)
        self.assertEqual(session.restore_failures, 1)

    def test_a_refused_document_leaves_the_editor_empty_and_the_card_alone(self):
        filesystem, store = self.store("the writer's real work")
        before = dict(filesystem.files)
        session, controller, _restored = self.session(
            Snapshot(1, 0, 0, self.oversized()), store, Shell(allow_exit=False))
        self.assertEqual(session.editor.text, "")
        self.assertTrue(controller.held)
        # The one thing that must never happen: the empty editor written over it.
        self.assertEqual(controller.service(1e6, session.editor), ACTION_NONE)
        self.assertEqual(controller.save_now(1e6, session.editor), ACTION_NONE)
        recovered = DocumentStore(filesystem, root="/sd/magwrite").open()
        self.assertEqual(recovered.snapshot.text, "the writer's real work")
        # Byte-for-byte: not one file on the card was written, renamed, or
        # removed by any part of the failed start.
        self.assertEqual(before, filesystem.files)

    def test_the_writer_lands_on_a_screen_they_can_leave(self):
        _filesystem, store = self.store("kept")
        shell = Shell(allow_exit=False)
        session, _controller, _restored = self.session(
            Snapshot(1, 0, 0, self.oversized()), store, shell)
        self.assertEqual(shell.state, STATE_ERROR)
        self.assertTrue(shell.error_reason)
        screen = decode(session._build_viewport()[1])
        self.assertIn("WORK IS KEPT", screen.lines)
        render_viewport(screen)
        shell.back()
        self.assertEqual(shell.state, STATE_MAIN_MENU)

    def test_opening_a_document_releases_the_hold(self):
        _filesystem, store = self.store("kept")
        shell = Shell(allow_exit=False)
        session, controller, _restored = self.session(
            Snapshot(1, 0, 0, self.oversized()), store, shell)
        self.assertTrue(controller.held)

        class Opening:
            document_id = "d0001"
            kind = "DRAFT"
            title = "DRAFT 1"
            text = "a new start"
            created = True

            def cursor(self):
                return 0, 0

        self.assertTrue(session._adopt_document(Opening()))
        self.assertFalse(controller.held)
        self.assertEqual(session.editor.text, "a new start")

    def test_a_held_controller_reports_the_reason_rather_than_a_card_fault(self):
        _filesystem, store = self.store("kept")
        controller = PersistenceController(store, 0.0, lambda record: None)
        controller.hold_writes("document too long")
        self.assertEqual(controller.error, "document too long")
        self.assertEqual(controller.summary()["write_hold"], "document too long")
        controller.release_writes()
        self.assertIsNone(controller.write_hold)


class MagTagStartupScreenTest(unittest.TestCase):
    """The panel is the only thing that can speak while the link is down."""

    def test_every_screen_encodes_and_draws(self):
        for screen in (starting_screen(), waiting_screen(),
                       fault_screen("SD_SCK in use")):
            round_tripped = ViewportMessage.decode(0, screen.encode())
            self.assertEqual(round_tripped.lines, screen.lines)
            render_viewport(screen)

    def test_a_screen_carries_no_state_this_board_does_not_own(self):
        for screen in (starting_screen(), waiting_screen()):
            self.assertEqual(screen.revision, 0)
            self.assertEqual(screen.cursor_row, 0)
            self.assertEqual(screen.cursor_column, 0)

    def test_the_two_waiting_screens_say_different_things(self):
        self.assertNotEqual(starting_screen().lines, waiting_screen().lines)
        self.assertNotEqual(starting_screen().status, waiting_screen().status)

    def test_a_fault_screen_survives_an_unrenderable_exception_message(self):
        screen = fault_screen("SD_SCK in use — check é wiring @@@ " + "x" * 200)
        render_viewport(screen)
        self.assertLessEqual(len(screen.lines), 5)

    def test_a_fault_screen_tells_the_writer_what_to_do(self):
        self.assertIn("DISCONNECT POWER, RETRY", fault_screen("boom").lines)


class StandaloneActivationTest(unittest.TestCase):
    """The default is the appliance, on both boards, with nothing armed."""

    def test_the_fruitjam_ships_standalone_enabled(self):
        source = read("fruitjam", "config.py")
        self.assertIn("ENABLE_STANDALONE = True", source)
        self.assertIn('STANDALONE_MODE = "FRUITJAM_STANDALONE"', source)
        self.assertIn("ENABLE_DEV_RUNTIME = False", source)

    def test_the_magtag_ships_standalone_enabled(self):
        source = read("magtag", "config.py")
        self.assertIn("ENABLE_STANDALONE = True", source)
        self.assertIn('STANDALONE_DISPLAY_MODE = "MAGTAG_STANDALONE"', source)
        self.assertIn('DEV_DISPLAY_RUNTIME_MODE = "DISABLED"', source)

    def test_the_standalone_mode_is_activatable_but_never_guarded(self):
        self.assertIn(STANDALONE_DISPLAY_MODE, ACTIVATION_MODES)
        self.assertNotIn(STANDALONE_DISPLAY_MODE, APPROVED_TEST_MODES)

    def test_neither_boot_gate_remounts_for_the_standalone_mode(self):
        """No guard is written, so no filesystem is taken from the host."""
        for parts in (("magtag", "hardware_test_boot.py"),
                      ("fruitjam", "boot.py")):
            self.assertNotIn(STANDALONE_DISPLAY_MODE, read(*parts), parts[-1])
            self.assertNotIn("FRUITJAM_STANDALONE", read(*parts), parts[-1])

    def test_both_dispatchers_reach_the_runtime_by_default(self):
        for parts, mode, module in (
            (("fruitjam", "code.py"), "FRUITJAM_STANDALONE", "dev_runtime"),
            (("magtag", "code.py"), "MAGTAG_STANDALONE", "dev_display_runtime"),
        ):
            source = read(*parts)
            self.assertIn("ENABLE_STANDALONE", source, parts[-1])
            self.assertIn(mode, source, parts[-1])
            self.assertIn("import " + module, source, parts[-1])

    def test_an_armed_harness_still_wins_over_the_default(self):
        """Arming a harness is still how a board is put on the bench."""
        source = read("fruitjam", "code.py")
        self.assertLess(
            source.index("FRUITJAM_USB_KEYBOARD"),
            source.index("FRUITJAM_STANDALONE"),
        )
        self.assertLess(
            source.index("FRUITJAM_EDITOR_INTEGRATION"),
            source.index("FRUITJAM_STANDALONE"),
        )
        # The one-shot UART TX harness is module-level code rather than an
        # import, so the standalone branch guards against it explicitly.
        standalone = source.split("FRUITJAM_STANDALONE")[1].split("elif")[0]
        self.assertIn("FRUITJAM_UART_VIEWPORT_TX", standalone)

    def test_the_standalone_bounds_are_all_removed_deliberately(self):
        source = read("fruitjam", "config.py")
        for name in (
            "STANDALONE_IDLE_TIMEOUT_SECONDS", "STANDALONE_SESSION_TIMEOUT_SECONDS",
            "STANDALONE_MAX_EVENTS", "STANDALONE_MAX_VIEWPORT_FRAMES",
            "STANDALONE_MAX_PROTOCOL_FRAMES", "STANDALONE_KEYBOARD_OPEN_ATTEMPTS",
        ):
            self.assertIn(name + " = None", source, name)

    def test_the_appliance_has_no_stop_and_says_so(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("ALLOW_EXIT = False", source)
        self.assertIn('"stop_from"] = "MAIN_MENU" if ALLOW_EXIT else "NOWHERE"',
                      source)

    def test_the_profile_is_reported_in_every_lifecycle_record(self):
        for parts, events in (
            (FRUITJAM_ENTRY, ("dev_runtime_ready", "dev_runtime_stopped")),
            (MAGTAG_ENTRY, ("dev_display_ready", "dev_display_stopped")),
        ):
            source = read(*parts)
            for event in events:
                record = source.split('"event": "%s"' % event)[1]
                record = record.split("})")[0]
                self.assertIn('"profile"', record, event)

    def test_the_magtag_wait_constant_is_mirrored_not_duplicated(self):
        import config as magtag_config
        source = read(*MAGTAG_ENTRY)
        declared = None
        for line in source.splitlines():
            if line.startswith("DEFAULT_STARTUP_WAIT_SECONDS"):
                declared = ast.literal_eval(line.partition("=")[2].strip())
        self.assertIsNotNone(declared)
        self.assertEqual(
            magtag_config.STANDALONE_DISPLAY_WAIT_SECONDS, declared)

    def test_the_magtag_draws_before_it_reads_and_only_when_idle(self):
        source = read(*MAGTAG_ENTRY)
        # The panel is constructed before the UART, which is what makes a wiring
        # fault something the writer can see.
        self.assertLess(source.index("UC8151DisplayAdapter"),
                        source.index("busio.UART"))
        self.assertIn("draw_local(starting_screen()", source)
        waiting = source.split("waiting_screen_drawn\n")[1].split(
            "draw_local(waiting_screen()")[0]
        for guard in ("scheduler.pending is None",
                      "scheduler.inflight is None",
                      "scheduler.ready_to_start is None",
                      "not display.is_busy()"):
            self.assertIn(guard, waiting, guard)


if __name__ == "__main__":
    unittest.main()
