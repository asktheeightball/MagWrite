"""The repeatable development runtime, and what separates it from a harness.

Every guarded harness in this repository exists to produce evidence once, and
pays for that with a one-shot guard, a filesystem it remounts away from the
host, disabled autoreload, and certification ceilings. The development runtime
exists to be started and stopped all day, so it must have none of those. This
file asserts the absence, because an absence is exactly the kind of property
that gets quietly reintroduced by a later copy-paste.

The device-entry assertions are static because these modules import ``board``
and ``busio`` and cannot be imported on the host. That is the same defect class
that blocked two prior physical attempts — device-entry code the host suite
never reached — so every line the runtime adds there is asserted here.
"""

import ast
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAGTAG = os.path.join(ROOT, "magtag")
sys.path.insert(0, MAGTAG)
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from magwrite.display_adapter import (
    ACTIVATION_MODES, APPROVED_TEST_MODES, DEV_DISPLAY_MODE,
    validate_physical_test_activation,
)

FRUITJAM_MODE = "FRUITJAM_DEV_RUNTIME"
MAGTAG_MODE = "MAGTAG_DEV_DISPLAY"

FRUITJAM_ENTRY = ("fruitjam", "dev_runtime.py")
MAGTAG_ENTRY = ("magtag", "dev_display_runtime.py")
DEV_ENTRIES = (FRUITJAM_ENTRY, MAGTAG_ENTRY)

# Every guard that exists on either board. The development runtime may not
# create, delete, read, check, or even name one of them.
EVERY_GUARD = (
    "/magwrite_refresh_test_20.started", "/magwrite_refresh_test_20.complete",
    "/magwrite_refresh_test_50.started", "/magwrite_refresh_test_50.complete",
    "/magwrite_refresh_test_100.started", "/magwrite_refresh_test_100.complete",
    "/magwrite_single_line_typing.started",
    "/magwrite_single_line_typing.complete",
    "/magwrite_uart_tx.started", "/magwrite_uart_tx.complete",
    "/magwrite_uart_rx.started", "/magwrite_uart_rx.complete",
    "/magwrite_uart_ack_tx.started", "/magwrite_uart_ack_tx.complete",
    "/magwrite_uart_ack_rx.started", "/magwrite_uart_ack_rx.complete",
    "/magwrite_editor_integration.started",
    "/magwrite_editor_integration.complete",
    "/magwrite_editor_display.started", "/magwrite_editor_display.complete",
    "/magwrite_usb_keyboard.started", "/magwrite_usb_keyboard.complete",
    "/magwrite_usb_keyboard_display.started",
    "/magwrite_usb_keyboard_display.complete",
    # Consumed by the abandoned V1 responsiveness attempt. Retired, never
    # deleted, and never to be reused.
    "/magwrite_v1_responsiveness.started",
    "/magwrite_v1_responsiveness.complete",
    "/magwrite_v1_responsiveness_display.started",
    "/magwrite_v1_responsiveness_display.complete",
)


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


def code(*parts):
    """The module's executable body, with its docstring and comments removed.

    These runtimes are documented largely by what they refuse to do, so their
    prose necessarily names ``storage.remount``, ``autoreload``, ``.started``
    and the rest. An assertion that those never appear must therefore look at
    the code, not the file, or explaining the design would break the test that
    enforces it.
    """
    tree = ast.parse(read(*parts))
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        tree.body.pop(0)
    return ast.unparse(tree)


class DisabledByDefaultTest(unittest.TestCase):
    """A runtime that is repeatable must still be off until it is asked for."""

    def test_the_fruitjam_activation_pair_ships_disabled(self):
        source = read("fruitjam", "config.py")
        self.assertIn("ENABLE_DEV_RUNTIME = False", source)
        self.assertIn('DEV_RUNTIME_MODE = "DISABLED"', source)

    def test_the_magtag_activation_ships_disabled(self):
        source = read("magtag", "config.py")
        self.assertIn('DEV_DISPLAY_RUNTIME_MODE = "DISABLED"', source)
        self.assertIn("ENABLE_PHYSICAL_DISPLAY = False", source)
        self.assertIn('PHYSICAL_TEST_MODE = "DISABLED"', source)

    def test_the_shipped_configs_refuse_the_runtime_as_loaded(self):
        import config as magtag_config
        self.assertEqual(magtag_config.DEV_DISPLAY_RUNTIME_MODE, "DISABLED")
        self.assertFalse(magtag_config.ENABLE_PHYSICAL_DISPLAY)
        with self.assertRaises(RuntimeError):
            validate_physical_test_activation(magtag_config, MAGTAG_MODE)

    def test_both_entry_points_require_their_full_activation_pair(self):
        fruitjam = read(*FRUITJAM_ENTRY)
        self.assertIn("ENABLE_DEV_RUNTIME", fruitjam)
        self.assertIn("DEV_RUNTIME_MODE", fruitjam)
        self.assertIn("development runtime is not enabled", fruitjam)
        magtag = read(*MAGTAG_ENTRY)
        self.assertIn("validate_physical_test_activation", magtag)
        self.assertIn("ENABLE_UART_RECEIVER", magtag)
        self.assertIn("ENABLE_UART_STATUS_TX", magtag)
        self.assertIn("DEV_DISPLAY_RUNTIME_MODE", magtag)
        self.assertIn("development display runtime is not enabled", magtag)

    def test_every_gate_is_checked_before_any_hardware_is_touched(self):
        fruitjam = read(*FRUITJAM_ENTRY)
        self.assertLess(
            fruitjam.index("is not enabled"), fruitjam.index("import board")
        )
        self.assertLess(
            fruitjam.index("is not enabled"), fruitjam.index("busio.UART")
        )
        magtag = read(*MAGTAG_ENTRY)
        self.assertLess(
            magtag.index("driver hash mismatch"), magtag.index("import board")
        )
        self.assertLess(
            magtag.index("is not enabled"), magtag.index("busio.UART")
        )

    def test_the_magtag_still_pins_the_verified_display_driver(self):
        from magwrite.sha256 import sha256_file
        source = read(*MAGTAG_ENTRY)
        digest = sha256_file(os.path.join(MAGTAG, "uc8151.py"))
        self.assertIn(digest, source)


class NoOneShotGuardTest(unittest.TestCase):
    """The single most important difference, asserted from several angles."""

    def test_neither_runtime_names_any_guard_path(self):
        for parts in DEV_ENTRIES:
            source = code(*parts)
            for guard in EVERY_GUARD:
                self.assertNotIn(guard, source, "%s / %s" % (parts[-1], guard))

    def test_neither_runtime_declares_a_guard_of_its_own(self):
        """Not merely "no existing guard" — no guard-shaped path at all.

        Read from the string constants rather than the text, because
        ``session.complete`` and ``'filesystem_remounted'`` are attribute and
        key names that a naive substring search would mistake for guards.
        """
        for parts in DEV_ENTRIES:
            tree = ast.parse(read(*parts))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant):
                    continue
                if not isinstance(node.value, str):
                    continue
                text = node.value
                if "\n" in text:            # a docstring, not a path
                    continue
                if text.endswith(".py"):   # the pinned driver, read not written
                    continue
                self.assertFalse(
                    text.startswith("/") or text.endswith(".started")
                    or text.endswith(".complete"),
                    "%s declares a guard-shaped path %r" % (parts[-1], text),
                )
            self.assertNotIn("START =", code(*parts), parts[-1])
            self.assertNotIn("COMPLETE =", code(*parts), parts[-1])

    def test_neither_runtime_writes_deletes_or_stats_any_file(self):
        for parts in DEV_ENTRIES:
            source = code(*parts)
            self.assertNotIn("os.remove", source, parts[-1])
            self.assertNotIn("os.unlink", source, parts[-1])
            self.assertNotIn("os.stat", source, parts[-1])
            self.assertNotIn("import os", source, parts[-1])
            # A builtin open(), as opposed to backend.open() or display.open().
            self.assertIsNone(re.search(r"(?<![.\w])open\(", source), parts[-1])

    def test_neither_runtime_refuses_a_rerun(self):
        """The harness rerun refusal is precisely what must not be copied."""
        for parts in DEV_ENTRIES:
            source = code(*parts)
            self.assertNotIn("guard exists", source, parts[-1])
            self.assertNotIn("exists(START)", source, parts[-1])
            self.assertNotIn("def exists(", source, parts[-1])

    def test_repeated_starts_are_possible_because_nothing_is_consumed(self):
        """A start consumes no resource, so nothing bounds how many there are.

        Restated as an executable fact rather than a comment: the union of every
        name either runtime writes to persistent storage is empty.
        """
        written = set()
        for parts in DEV_ENTRIES:
            tree = ast.parse(read(*parts))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "open":
                        written.add(ast.dump(node))
        self.assertEqual(written, set())

    def test_the_guarded_harnesses_still_own_their_guards_unchanged(self):
        """Retiring a phase must not disturb a completed milestone's record."""
        owners = {
            "/magwrite_usb_keyboard.started": (
                "fruitjam", "hardware_usb_keyboard_test.py"),
            "/magwrite_usb_keyboard_display.started": (
                "magtag", "hardware_usb_keyboard_display_test.py"),
            "/magwrite_editor_integration.started": (
                "fruitjam", "hardware_editor_test.py"),
            "/magwrite_editor_display.started": (
                "magtag", "hardware_editor_display_test.py"),
            "/magwrite_uart_tx.started": ("fruitjam", "code.py"),
        }
        for guard, parts in owners.items():
            self.assertIn(guard, read(*parts), guard)


class FilesystemControlTest(unittest.TestCase):
    """The host keeps CIRCUITPY, which is what makes the loop repeatable."""

    def test_neither_runtime_remounts_the_filesystem(self):
        for parts in DEV_ENTRIES:
            source = code(*parts)
            self.assertNotIn("import storage", source, parts[-1])
            # A remount call, not the "filesystem_remounted": False it reports.
            self.assertIsNone(re.search(r"\bremount\s*\(", source), parts[-1])

    def test_neither_runtime_disables_autoreload(self):
        """Autoreload left on is how a saved file restarts the runtime."""
        for parts in DEV_ENTRIES:
            source = code(*parts)
            self.assertNotIn("import supervisor", source, parts[-1])
            self.assertNotIn("autoreload", source, parts[-1])

    def test_the_fruitjam_boot_gate_does_not_arm_the_development_mode(self):
        boot = read("fruitjam", "boot.py")
        self.assertNotIn("DEV_RUNTIME", boot)
        self.assertNotIn(FRUITJAM_MODE, boot)

    def test_the_boot_gate_still_arms_exactly_the_guarded_modes(self):
        """Guarded modes need a writable filesystem; development modes must not.

        The boot tuple and ``APPROVED_TEST_MODES`` are asserted equal so neither
        can drift, which is the defect that left a board unable to persist its
        guard mid-run in an earlier phase.
        """
        tree = ast.parse(read("magtag", "hardware_test_boot.py"))
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and any(
                isinstance(op, ast.In) for op in node.ops
            ):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Tuple):
                        found.append(tuple(
                            element.value for element in comparator.elts
                            if isinstance(element, ast.Constant)
                        ))
        self.assertEqual(len(found), 1)
        self.assertEqual(sorted(found[0]), sorted(APPROVED_TEST_MODES))
        self.assertNotIn(DEV_DISPLAY_MODE, found[0])

    def test_the_development_mode_is_activatable_but_not_guarded(self):
        self.assertIn(DEV_DISPLAY_MODE, ACTIVATION_MODES)
        self.assertNotIn(DEV_DISPLAY_MODE, APPROVED_TEST_MODES)
        self.assertEqual(DEV_DISPLAY_MODE, MAGTAG_MODE)

    def test_an_unapproved_mode_is_still_refused(self):
        class Config:
            HARDWARE_COMPATIBILITY_DECISION = "COMPATIBLE"
            DISPLAY_CONTROLLER = "UC8151D"
            ENABLE_PHYSICAL_DISPLAY = True
        with self.assertRaises(RuntimeError):
            validate_physical_test_activation(Config, "MAGTAG_NOT_A_MODE")
        self.assertTrue(
            validate_physical_test_activation(Config, DEV_DISPLAY_MODE)
        )


class ConstructionFailureTest(unittest.TestCase):
    """A failure must be reported, and must leave the board usable."""

    def test_construction_is_fenced_off_and_reported(self):
        for parts, event in (
            (FRUITJAM_ENTRY, "dev_runtime_construction_failed"),
            (MAGTAG_ENTRY, "dev_display_construction_failed"),
        ):
            source = read(*parts)
            self.assertIn(event, source, parts[-1])
            self.assertIn("except Exception as construction_error", source,
                          parts[-1])

    def test_the_failure_record_states_that_nothing_was_trapped(self):
        for parts in DEV_ENTRIES:
            source = read(*parts)
            failure = source.split("construction_failed")[1].split("\n\n")[0]
            self.assertIn('"filesystem_remounted": False', failure, parts[-1])
            self.assertIn('"guard_written": False', failure, parts[-1])

    def test_a_construction_failure_cannot_trap_the_filesystem(self):
        """There is no remount anywhere, so no failure path can leave one on."""
        for parts in DEV_ENTRIES:
            self.assertNotIn("readonly=", code(*parts), parts[-1])

    def test_the_run_loop_is_only_entered_when_construction_succeeded(self):
        self.assertIn("if session is not None:", read(*FRUITJAM_ENTRY))
        self.assertIn("if display is not None:", read(*MAGTAG_ENTRY))

    def test_a_failure_still_reaches_the_stopped_record(self):
        """The stop record is outside the guarded block, so it always prints."""
        for parts, event in (
            (FRUITJAM_ENTRY, "dev_runtime_stopped"),
            (MAGTAG_ENTRY, "dev_display_stopped"),
        ):
            source = read(*parts)
            tree = ast.parse(source)
            top_level = []
            for node in tree.body:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    top_level.append(ast.dump(node))
            self.assertTrue(
                any(event in dumped for dumped in top_level),
                "%s must log %s at module level" % (parts[-1], event),
            )


class CleanStopTest(unittest.TestCase):
    """Stopping must leave a state the next start can simply use."""

    def test_the_stop_record_declares_a_restartable_board(self):
        for parts in DEV_ENTRIES:
            source = read(*parts)
            self.assertIn('"restartable": True', source, parts[-1])
            self.assertIn('"guard_written": False', source, parts[-1])
            self.assertIn('"filesystem_remounted": False', source, parts[-1])

    def test_the_operator_stop_control_is_the_application_key(self):
        from magwrite_transport.hid_keymap import (
            CONTROL_FINISH, CONTROL_USAGES, FINISH_USAGES, USAGE_APPLICATION,
            USAGE_ESCAPE,
        )
        self.assertEqual(USAGE_APPLICATION, 0x65)
        self.assertEqual(CONTROL_USAGES[USAGE_APPLICATION], CONTROL_FINISH)
        self.assertEqual(CONTROL_USAGES[USAGE_ESCAPE], CONTROL_FINISH)
        self.assertIn(USAGE_APPLICATION, FINISH_USAGES)
        self.assertIn("0x65", read(*FRUITJAM_ENTRY))
        self.assertIn('"stop_key": "APPLICATION"', read(*FRUITJAM_ENTRY))

    def test_a_console_interrupt_is_a_stop_rather_than_a_fault(self):
        for parts in DEV_ENTRIES:
            self.assertIn("except KeyboardInterrupt:", read(*parts), parts[-1])

    def test_the_magtag_serves_session_after_session_without_a_reset(self):
        source = read(*MAGTAG_ENTRY)
        self.assertIn("def new_session()", source)
        self.assertIn("dev_display_awaiting_next_session", source)
        # Rebuilt rather than carried over, because revisions restart at zero.
        self.assertGreater(source.count("new_session()"), 2)

    def test_the_magtag_runtime_enforces_no_certification_ceiling(self):
        source = code(*MAGTAG_ENTRY)
        for ceiling in (
            "MAX_VIEWPORTS", "MAX_FRAMES", "MAX_STATUS_FRAMES",
            "MAX_PARTIAL_REFRESHES", "RunClock", "limit exceeded",
        ):
            self.assertNotIn(ceiling, source, ceiling)

    def test_the_magtag_runtime_keeps_the_real_hardware_bound(self):
        """The busy timeout is a fault detector, not a certification budget."""
        source = read(*MAGTAG_ENTRY)
        self.assertIn("UART_DISPLAY_BUSY_TIMEOUT_SECONDS", source)
        self.assertIn("display busy timeout", source)

    def test_neither_runtime_claims_a_pass_or_a_fail(self):
        for parts in DEV_ENTRIES:
            source = code(*parts)
            self.assertNotIn("'PASS'", source, parts[-1])
            self.assertNotIn("'FAIL'", source, parts[-1])
            self.assertNotIn("result ==", source, parts[-1])

    def test_the_magtag_refresh_history_cannot_accumulate(self):
        """Drained every pass, so an open-ended session grows nothing."""
        source = read(*MAGTAG_ENTRY)
        self.assertIn("while scheduler.completions:", source)
        self.assertIn("scheduler.completions.pop(0)", source)
        self.assertIn("class RefreshStats", source)


class DispatcherTest(unittest.TestCase):
    """The dev branch returns, so it has to be terminal on its own."""

    def test_both_dispatchers_route_the_development_mode_first(self):
        fruitjam = read("fruitjam", "code.py")
        self.assertIn("ENABLE_DEV_RUNTIME", fruitjam)
        self.assertIn(FRUITJAM_MODE, fruitjam)
        self.assertIn("import dev_runtime", fruitjam)
        magtag = read("magtag", "code.py")
        self.assertIn("DEV_DISPLAY_RUNTIME_MODE", magtag)
        self.assertIn(MAGTAG_MODE, magtag)
        self.assertIn("import dev_display_runtime", magtag)

    def test_the_development_branch_never_falls_through_to_a_harness(self):
        """Falling through would try to claim a guard consumed months ago."""
        for parts, imported in (
            (("fruitjam", "code.py"), "dev_runtime"),
            (("magtag", "code.py"), "dev_display_runtime"),
        ):
            tree = ast.parse(read(*parts))
            branch = None
            for node in ast.walk(tree):
                if not isinstance(node, ast.If):
                    continue
                for statement in node.body:
                    if isinstance(statement, ast.Import) and any(
                        alias.name == imported for alias in statement.names
                    ):
                        branch = node.body
            self.assertIsNotNone(branch, parts[-1])
            self.assertIsInstance(branch[-1], ast.While, parts[-1])
            self.assertIs(branch[-1].test.value, True, parts[-1])

    def test_the_dispatchers_still_refuse_when_nothing_is_armed(self):
        self.assertIn("physical_test_refused", read("magtag", "code.py"))
        self.assertIn("uart_tx_refused", read("fruitjam", "code.py"))


class AdaptivePacingTest(unittest.TestCase):
    """The pacing and keyboard work from fbed96f must survive intact."""

    def test_the_runtime_builds_the_adaptive_pacer_from_config(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("from magwrite_transport.pacing import DisplayPacer", source)
        self.assertIn("pacer=DisplayPacer(", source)
        for name in (
            "USB_KEYBOARD_COALESCE_SECONDS", "USB_KEYBOARD_QUIET_SECONDS",
            "USB_KEYBOARD_CAUGHT_UP_MIN_SEND_SECONDS",
            "USB_KEYBOARD_SUSTAINED_MIN_SEND_SECONDS",
        ):
            self.assertIn("config." + name, source, name)

    def test_the_runtime_uses_the_device_keyboard_layout(self):
        self.assertIn("layout=config.USB_KEYBOARD_LAYOUT", read(*FRUITJAM_ENTRY))
        self.assertIn('USB_KEYBOARD_LAYOUT = "AUTO"', read("fruitjam", "config.py"))

    def test_the_runtime_keeps_the_passive_latency_recorder(self):
        """Useful in ordinary development; it decides nothing, so it stays."""
        self.assertIn("latency=LatencyRecorder()", read(*FRUITJAM_ENTRY))

    def test_the_config_values_the_board_loads_construct_a_valid_pacer(self):
        from magwrite_transport.keyboard_layout import resolve
        from magwrite_transport.pacing import DisplayPacer
        values = {}
        for line in read("fruitjam", "config.py").splitlines():
            if line.startswith(("USB_KEYBOARD_", "DEV_RUNTIME_")) and "=" in line:
                name, _, raw = line.partition("=")
                try:
                    values[name.strip()] = ast.literal_eval(raw.strip())
                except (SyntaxError, ValueError):
                    pass
        pacer = DisplayPacer(
            coalesce_seconds=values["USB_KEYBOARD_COALESCE_SECONDS"],
            quiet_seconds=values["USB_KEYBOARD_QUIET_SECONDS"],
            caught_up_min_send_seconds=values[
                "USB_KEYBOARD_CAUGHT_UP_MIN_SEND_SECONDS"
            ],
            sustained_min_send_seconds=values[
                "USB_KEYBOARD_SUSTAINED_MIN_SEND_SECONDS"
            ],
        )
        self.assertFalse(pacer.due(0.0, busy=False))
        self.assertIsNotNone(resolve(values["USB_KEYBOARD_LAYOUT"], None))
        self.assertGreater(values["DEV_RUNTIME_IDLE_TIMEOUT_SECONDS"], 0)
        self.assertGreater(values["DEV_RUNTIME_SESSION_TIMEOUT_SECONDS"], 0)

    def test_a_development_session_is_given_more_room_than_a_bounded_run(self):
        values = {}
        for line in read("fruitjam", "config.py").splitlines():
            if "=" in line and not line.startswith("#"):
                name, _, raw = line.partition("=")
                try:
                    values[name.strip()] = ast.literal_eval(raw.strip())
                except (SyntaxError, ValueError):
                    pass
        self.assertGreater(
            values["DEV_RUNTIME_IDLE_TIMEOUT_SECONDS"],
            values["USB_KEYBOARD_IDLE_TIMEOUT_SECONDS"],
        )
        self.assertGreater(
            values["DEV_RUNTIME_SESSION_TIMEOUT_SECONDS"],
            values["USB_KEYBOARD_SESSION_TIMEOUT_SECONDS"],
        )


class CertificationCeilingTest(unittest.TestCase):
    """Ceilings became parameters; the guarded harnesses keep the old values."""

    def test_the_session_defaults_are_still_the_authorised_ceilings(self):
        from magwrite_transport.live_session import (
            MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES,
        )
        from keyboard_simulator import KeyboardLink
        session = KeyboardLink().session
        self.assertEqual(session.max_viewport_frames, MAX_VIEWPORT_FRAMES)
        self.assertEqual(session.max_protocol_frames, MAX_PROTOCOL_FRAMES)
        self.assertEqual(MAX_VIEWPORT_FRAMES, 100)
        self.assertEqual(MAX_PROTOCOL_FRAMES, 200)

    def test_the_guarded_harness_passes_no_ceiling_and_so_keeps_the_default(self):
        source = read("fruitjam", "hardware_usb_keyboard_test.py")
        self.assertNotIn("max_viewport_frames", source)
        self.assertNotIn("max_protocol_frames", source)
        # It still enforces both in its own loop, exactly as verified.
        self.assertIn("viewport frame limit exceeded", source)
        self.assertIn("input frame limit exceeded", source)

    def test_the_default_ceiling_is_still_enforced(self):
        from magwrite_transport.live_session import (
            LiveSessionError, LiveTypingSession,
        )

        class DeadAdapter:
            ready = False
            finish_requested = False
            queue_overflows = 0

            def poll(self, now):
                return 0

        session = LiveTypingSession(
            lambda: 0.0, lambda record: None, adapter=DeadAdapter(),
        )
        with self.assertRaises(LiveSessionError):
            for _ in range(session.max_protocol_frames + 1):
                session._emit(1, 0, b"x")

    def test_the_development_runtime_raises_both_ceilings(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("max_viewport_frames=DEV_MAX_VIEWPORT_FRAMES", source)
        self.assertIn("max_protocol_frames=DEV_MAX_PROTOCOL_FRAMES", source)
        self.assertIn("max_events=config.DEV_RUNTIME_MAX_EVENTS", source)

    def test_the_raised_ceilings_are_bounded_rather_than_absent(self):
        """An unbounded counter on a microcontroller is still a bug."""
        values = {}
        for line in read(*FRUITJAM_ENTRY).splitlines():
            if line.startswith("DEV_MAX_") and "=" in line:
                name, _, raw = line.partition("=")
                values[name.strip()] = ast.literal_eval(raw.strip())
        from magwrite_transport.live_session import (
            MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES,
        )
        self.assertGreater(values["DEV_MAX_VIEWPORT_FRAMES"], MAX_VIEWPORT_FRAMES)
        self.assertGreater(values["DEV_MAX_PROTOCOL_FRAMES"], MAX_PROTOCOL_FRAMES)
        for value in values.values():
            self.assertIsInstance(value, int)
            self.assertLess(value, 10 ** 7)

    def test_the_runtime_does_not_re_enforce_a_ceiling_in_its_own_loop(self):
        source = code(*FRUITJAM_ENTRY)
        self.assertNotIn("viewport frame limit exceeded", source)
        self.assertNotIn("input frame limit exceeded", source)


class UnchangedBehaviourTest(unittest.TestCase):
    """Raising the ceilings must change nothing else about a session.

    The same scripted keyboard run is played twice — once with the authorised
    ceilings and once with the development ones — and every observable outcome
    is compared. Anything the ceilings could have perturbed (the document, the
    revisions, the hash, the frame and event counts, the pacing decisions) is in
    the summary, so an equal summary is the claim.
    """

    @classmethod
    def setUpClass(cls):
        from keyboard_simulator import KeyboardLink
        from test_live_session import full_script
        # Paced at roughly 60 WPM rather than instantly, so the run actually
        # exercises the pacing regimes and produces frames worth comparing:
        # an unpaced script coalesces into two frames and would compare nothing.
        options = {
            "typing_interval_seconds": KeyboardLink.HUMAN_REPORT_INTERVAL_SECONDS
        }
        cls.default = KeyboardLink(
            full_script(), **options
        ).run().session.summary("PASS")
        cls.development = KeyboardLink(
            full_script(),
            max_viewport_frames=100000,
            max_protocol_frames=200000,
            **options
        ).run().session.summary("PASS")

    def test_the_comparison_is_wide_enough_to_mean_something(self):
        self.assertGreater(self.default["viewport_frames_sent"], 20)
        self.assertGreater(self.default["events_processed"], 100)

    def test_the_document_is_identical(self):
        self.assertEqual(
            self.development["final_document_text"],
            self.default["final_document_text"],
        )
        self.assertGreater(len(self.default["final_document_text"]), 100)

    def test_the_revision_and_hash_reconciliation_is_identical(self):
        for field in (
            "document_revision", "final_viewport_revision",
            "final_transmitted_revision", "final_displayed_revision",
            "final_hash", "test_complete",
        ):
            self.assertEqual(
                self.development[field], self.default[field], field
            )
        self.assertTrue(self.default["test_complete"])
        self.assertEqual(
            self.default["final_transmitted_revision"],
            self.default["final_displayed_revision"],
        )

    def test_the_keyboard_and_editor_behaviour_is_identical(self):
        for field in (
            "events_generated", "events_processed", "events_rejected",
            "queue_overflows", "maximum_queue_depth",
            "final_document_lines", "final_document_characters",
            "final_cursor_row", "final_cursor_column",
        ):
            self.assertEqual(
                self.development[field], self.default[field], field
            )

    def test_the_uart_transport_behaviour_is_identical(self):
        for field in (
            "input_frames_sent", "bytes_sent", "bytes_received",
            "viewport_frames_sent", "viewport_frames_accepted",
            "crc_failures", "status_frames_rejected", "status_sequence_gaps",
            "status_duplicates", "resynchronization_events",
            "frame_accepted_received", "refresh_started_received",
            "refresh_completed_received", "display_caught_up_received",
        ):
            self.assertEqual(
                self.development[field], self.default[field], field
            )
        self.assertEqual(self.default["crc_failures"], 0)

    def test_the_adaptive_pacing_decisions_are_identical_and_still_adaptive(self):
        for field in (
            "pacing_onset_sends", "pacing_caught_up_sends",
            "pacing_sustained_sends", "pacing_forced_sends",
            "pacing_maximum_pending_seconds",
        ):
            self.assertEqual(
                self.development[field], self.default[field], field
            )
        # Still adaptive rather than a single fixed interval: the paced run
        # shows the onset send and a long tail of sustained-regime sends, and
        # the catch-up floor is a genuinely shorter, separate interval.
        from magwrite_transport import pacing
        self.assertEqual(self.default["pacing_onset_sends"], 1)
        self.assertGreater(self.default["pacing_sustained_sends"], 0)
        self.assertEqual(
            self.default["pacing_caught_up_min_send_seconds"],
            pacing.CAUGHT_UP_MIN_SEND_SECONDS,
        )
        self.assertEqual(
            self.default["pacing_sustained_min_send_seconds"],
            pacing.SUSTAINED_MIN_SEND_SECONDS,
        )
        self.assertLess(
            self.default["pacing_caught_up_min_send_seconds"],
            self.default["pacing_sustained_min_send_seconds"],
        )

    def test_the_latency_recorder_still_observes_without_deciding(self):
        self.assertEqual(
            self.development["latency_sends"], self.default["latency_sends"]
        )
        self.assertEqual(
            self.default["latency_sends"], self.default["viewport_frames_sent"]
        )


class RetirementTest(unittest.TestCase):
    """What the responsiveness certification phase left behind, and what went."""

    RETIRED = (
        ("fruitjam", "hardware_v1_responsiveness_test.py"),
        ("magtag", "hardware_v1_responsiveness_display_test.py"),
        ("host-tests", "test_v1_responsiveness_gate.py"),
    )

    SOURCE_TREES = ("fruitjam", "magtag", "host-tests", "tools")

    def test_the_certification_entry_points_are_gone(self):
        for parts in self.RETIRED:
            self.assertFalse(
                os.path.exists(os.path.join(ROOT, *parts)), "/".join(parts)
            )

    def test_no_responsiveness_activation_mode_survives_in_any_source(self):
        for tree in self.SOURCE_TREES:
            for base, _dirs, names in os.walk(os.path.join(ROOT, tree)):
                if "__pycache__" in base:
                    continue
                for name in names:
                    # This file names the retired modes in order to forbid them.
                    if not name.endswith(".py") or name == os.path.basename(__file__):
                        continue
                    path = os.path.join(base, name)
                    with open(path, "r", encoding="utf-8") as handle:
                        source = handle.read()
                    for token in (
                        "V1_RESPONSIVENESS",
                        "FRUITJAM_V1_RESPONSIVENESS",
                        "MAGTAG_V1_RESPONSIVENESS_DISPLAY",
                    ):
                        self.assertNotIn(token, source, path)

    def test_the_shared_work_worth_keeping_survived(self):
        """Pacing and the passive recorder are useful outside certification."""
        from magwrite_transport import latency, pacing
        self.assertTrue(hasattr(latency, "LatencyRecorder"))
        self.assertTrue(hasattr(pacing, "DisplayPacer"))
        self.assertTrue(os.path.exists(
            os.path.join(ROOT, "host-tests", "test_latency.py")
        ))

    def test_the_abandoned_guards_are_recorded_as_burned(self):
        """They exist on the boards and must never be reused or deleted."""
        for guard in (
            "/magwrite_v1_responsiveness.started",
            "/magwrite_v1_responsiveness_display.started",
        ):
            self.assertIn(guard, EVERY_GUARD)
            for parts in DEV_ENTRIES:
                self.assertNotIn(guard, read(*parts), parts[-1])


class HostSafetyTest(unittest.TestCase):
    """CircuitPython-only imports must stay out of anything the host loads."""

    FORBIDDEN = (
        "board", "busio", "storage", "supervisor", "displayio", "digitalio",
        "usb.core", "usb_host", "microcontroller",
    )

    HOST_SAFE_MODULES = (
        "hid_keymap.py", "hid_keyboard.py", "keyboard_repeat.py",
        "keyboard_layout.py", "pacing.py", "latency.py", "live_session.py",
        "usb_device_state.py", "usb_hid_descriptors.py",
        "usb_keyboard_adapter.py",
    )

    def test_the_shared_modules_stay_free_of_hardware_imports(self):
        for name in self.HOST_SAFE_MODULES:
            source = read("fruitjam", "magwrite_transport", name)
            for module in self.FORBIDDEN:
                self.assertNotIn("import " + module, source, name)

    def test_the_shared_modules_import_under_cpython(self):
        from magwrite_transport import latency, live_session, pacing
        self.assertTrue(hasattr(live_session, "LiveTypingSession"))
        self.assertTrue(hasattr(pacing, "DisplayPacer"))
        self.assertTrue(hasattr(latency, "LatencyRecorder"))

    def test_the_device_entry_points_keep_hardware_imports_after_the_gate(self):
        """They are device-only by design, so the gate must precede the import."""
        for parts in DEV_ENTRIES:
            tree = ast.parse(read(*parts))
            first_raise = None
            first_hardware = None
            for node in tree.body:
                if first_raise is None and isinstance(node, ast.If):
                    if any(isinstance(item, ast.Raise) for item in node.body):
                        first_raise = node.lineno
                if first_hardware is None and isinstance(node, ast.Import):
                    if any(alias.name in ("board", "busio")
                           for alias in node.names):
                        first_hardware = node.lineno
            self.assertIsNotNone(first_raise, parts[-1])
            self.assertIsNotNone(first_hardware, parts[-1])
            self.assertLess(first_raise, first_hardware, parts[-1])

    def test_no_hardware_module_is_loaded_by_ordinary_collection(self):
        for name in ("board", "busio", "storage", "supervisor", "usb"):
            self.assertNotIn(name, sys.modules, name)

    def test_both_runtimes_are_syntactically_valid_python(self):
        for parts in DEV_ENTRIES:
            ast.parse(read(*parts))


if __name__ == "__main__":
    unittest.main()
