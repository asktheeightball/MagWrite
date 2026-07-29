"""Device-entry, activation, guard, and host-safety coverage for this phase.

Both prior physical blockers occurred in device-entry code the host suite never
reached: a boot remount gate that never armed the new mode, and a run clock that
charged the operator's arming wait to the test budget. Every device-entry path
this phase adds is therefore asserted here, statically where it cannot be
imported and behaviourally where it can.
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
    APPROVED_TEST_MODES, USB_KEYBOARD_DISPLAY_MODE,
)

FRUITJAM_MODE = "FRUITJAM_USB_KEYBOARD"
MAGTAG_MODE = "MAGTAG_USB_KEYBOARD_DISPLAY"

FRUITJAM_ENTRY = ("fruitjam", "hardware_usb_keyboard_test.py")
MAGTAG_ENTRY = ("magtag", "hardware_usb_keyboard_display_test.py")

NEW_GUARDS = (
    "/magwrite_usb_keyboard.started",
    "/magwrite_usb_keyboard.complete",
    "/magwrite_usb_keyboard_display.started",
    "/magwrite_usb_keyboard_display.complete",
)

# Every guard that existed before this phase. None may be reused, renamed, read,
# written, or removed by the USB keyboard test.
PRIOR_GUARDS = (
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
)

EXPECTED_DRIVER_SHA256 = (
    "A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E"
)


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


class ActivationDefaultTest(unittest.TestCase):
    def test_fruitjam_usb_keyboard_activation_is_disabled_by_default(self):
        source = read("fruitjam", "config.py")
        self.assertIn("ENABLE_USB_KEYBOARD_TEST = False", source)
        self.assertIn('USB_KEYBOARD_TEST_MODE = "DISABLED"', source)

    def test_magtag_activation_is_disabled_by_default(self):
        source = read("magtag", "config.py")
        self.assertIn("ENABLE_PHYSICAL_DISPLAY = False", source)
        self.assertIn("ENABLE_UART_RECEIVER = False", source)
        self.assertIn("ENABLE_UART_STATUS_TX = False", source)
        self.assertIn('PHYSICAL_TEST_MODE = "DISABLED"', source)
        self.assertIn('USB_KEYBOARD_DISPLAY_TEST_MODE = "DISABLED"', source)

    def test_the_shipped_configs_refuse_the_run_as_loaded(self):
        import config as magtag_config
        self.assertFalse(magtag_config.ENABLE_PHYSICAL_DISPLAY)
        self.assertEqual(magtag_config.PHYSICAL_TEST_MODE, "DISABLED")
        self.assertEqual(
            magtag_config.USB_KEYBOARD_DISPLAY_TEST_MODE, "DISABLED"
        )

    def test_the_fruitjam_entry_point_requires_every_gate(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("ENABLE_USB_KEYBOARD_TEST", source)
        self.assertIn("USB_KEYBOARD_TEST_MODE", source)
        self.assertIn("USB keyboard gate not armed", source)
        self.assertIn("UART_TX_PIN_ALIAS", source)
        self.assertIn("UART_RX_PIN_ALIAS", source)
        self.assertIn("VERSION != 1 or MAX_PAYLOAD_SIZE != 192", source)

    def test_the_magtag_entry_point_requires_every_gate(self):
        source = read(*MAGTAG_ENTRY)
        for gate in (
            "validate_physical_test_activation", "ENABLE_UART_RECEIVER",
            "ENABLE_UART_STATUS_TX", "USB_KEYBOARD_DISPLAY_TEST_MODE",
            "USB keyboard display gate not armed",
        ):
            self.assertIn(gate, source)

    def test_every_gate_is_checked_before_any_hardware_is_touched(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertLess(
            source.index("gate not armed"), source.index("busio.UART")
        )
        self.assertLess(
            source.index("gate not armed"),
            source.index("UsbHostKeyboardBackend("),
        )
        magtag = read(*MAGTAG_ENTRY)
        self.assertLess(
            magtag.index("driver hash mismatch"), magtag.index("busio.UART")
        )

    def test_the_usb_keyboard_mode_is_an_approved_magtag_display_mode(self):
        self.assertIn(USB_KEYBOARD_DISPLAY_MODE, APPROVED_TEST_MODES)
        self.assertEqual(USB_KEYBOARD_DISPLAY_MODE, MAGTAG_MODE)

    def test_both_dispatchers_route_the_new_mode(self):
        fruitjam = read("fruitjam", "code.py")
        self.assertIn("ENABLE_USB_KEYBOARD_TEST", fruitjam)
        self.assertIn(FRUITJAM_MODE, fruitjam)
        self.assertIn("import hardware_usb_keyboard_test", fruitjam)
        magtag = read("magtag", "code.py")
        self.assertIn("USB_KEYBOARD_DISPLAY_TEST_MODE", magtag)
        self.assertIn(MAGTAG_MODE, magtag)
        self.assertIn("import hardware_usb_keyboard_display_test", magtag)

    def test_the_fruitjam_boot_remount_is_gated_on_the_new_mode(self):
        boot = read("fruitjam", "boot.py")
        self.assertIn("ENABLE_USB_KEYBOARD_TEST", boot)
        self.assertIn(FRUITJAM_MODE, boot)

    def test_the_dispatcher_still_refuses_when_nothing_is_armed(self):
        self.assertIn("physical_test_refused", read("magtag", "code.py"))
        self.assertIn("uart_tx_refused", read("fruitjam", "code.py"))


class BootRemountGateTest(unittest.TestCase):
    """``hardware_test_boot.py`` ships as the MagTag ``/boot.py``.

    It cannot be imported on the host because it calls ``storage.remount``, so
    the armed mode tuple is read statically. This is the exact defect class that
    blocked the first editor attempt: a mode approved by the display adapter but
    missing here boots read-only, and the harness then dies writing its
    ``.started`` guard before it ever reaches the panel.
    """

    def boot_modes(self):
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
        self.assertEqual(len(found), 1, "expected exactly one armed mode tuple")
        return found[0]

    def test_the_boot_gate_arms_the_usb_keyboard_display_mode(self):
        self.assertIn(MAGTAG_MODE, self.boot_modes())

    def test_the_boot_gate_still_covers_every_approved_mode(self):
        self.assertEqual(sorted(self.boot_modes()), sorted(APPROVED_TEST_MODES))


class GuardTest(unittest.TestCase):
    def test_the_four_new_guards_are_declared(self):
        fruitjam = read(*FRUITJAM_ENTRY)
        self.assertIn('START = "/magwrite_usb_keyboard.started"', fruitjam)
        self.assertIn('COMPLETE = "/magwrite_usb_keyboard.complete"', fruitjam)
        magtag = read(*MAGTAG_ENTRY)
        self.assertIn(
            'START = "/magwrite_usb_keyboard_display.started"', magtag
        )
        self.assertIn(
            'COMPLETE = "/magwrite_usb_keyboard_display.complete"', magtag
        )

    def test_the_new_guards_are_independent_of_every_prior_guard(self):
        for guard in NEW_GUARDS:
            self.assertNotIn(guard, PRIOR_GUARDS)

    def test_the_new_entry_points_touch_no_prior_guard(self):
        for part in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*part)
            for guard in PRIOR_GUARDS:
                self.assertNotIn(guard, source, guard)

    def test_prior_guards_are_still_declared_by_their_owners(self):
        owners = {
            "/magwrite_refresh_test_20.started": (
                "magtag", "hardware_refresh_test.py"),
            "/magwrite_single_line_typing.started": (
                "magtag", "magwrite", "single_line.py"),
            "/magwrite_uart_tx.started": ("fruitjam", "code.py"),
            "/magwrite_uart_rx.started": (
                "magtag", "hardware_uart_viewport_test.py"),
            "/magwrite_uart_ack_tx.started": (
                "fruitjam", "hardware_uart_ack_test.py"),
            "/magwrite_uart_ack_rx.started": (
                "magtag", "hardware_uart_ack_test.py"),
            "/magwrite_editor_integration.started": (
                "fruitjam", "hardware_editor_test.py"),
            "/magwrite_editor_display.started": (
                "magtag", "hardware_editor_display_test.py"),
        }
        for guard, part in owners.items():
            self.assertIn(guard, read(*part), guard)

    def test_a_rerun_is_blocked_once_either_guard_exists(self):
        for part in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*part)
            self.assertIn("if exists(START) or exists(COMPLETE):", source)
            self.assertIn("guard exists", source)

    def test_neither_entry_point_deletes_a_guard_or_retries(self):
        for part in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*part)
            self.assertNotIn("os.remove", source)
            self.assertNotIn("os.unlink", source)

    def test_a_failed_run_keeps_the_started_guard_and_writes_no_complete(self):
        for part in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            self.assertIn(
                'open(COMPLETE if result == "PASS" else START, "w")', read(*part)
            )

    def test_the_guard_is_claimed_before_any_hardware_construction(self):
        for part in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*part)
            self.assertLess(
                source.index('open(START, "w")'), source.index("busio.UART")
            )


class RunClockTest(unittest.TestCase):
    """The arming wait must keep its own bound; this broke attempt 1 before."""

    def test_the_magtag_entry_point_uses_the_two_phase_run_clock(self):
        source = read(*MAGTAG_ENTRY)
        self.assertIn("RunClock(", source)
        self.assertIn("USB_KEYBOARD_ARMING_TIMEOUT_SECONDS", source)
        self.assertIn("USB_KEYBOARD_DISPLAY_TIMEOUT_SECONDS", source)
        self.assertIn("clock.start_run()", source)

    def test_the_run_clock_only_starts_on_the_first_received_frame(self):
        source = read(*MAGTAG_ENTRY)
        self.assertIn(
            "if not clock.running and scheduler.last_input_sequence:", source
        )

    def test_the_arming_bound_is_generous_and_separate_from_the_run_bound(self):
        import config as magtag_config
        self.assertGreaterEqual(
            magtag_config.USB_KEYBOARD_ARMING_TIMEOUT_SECONDS, 900
        )
        self.assertGreaterEqual(
            magtag_config.USB_KEYBOARD_DISPLAY_TIMEOUT_SECONDS, 1200
        )

    def test_a_live_run_is_given_a_larger_budget_than_the_scripted_run(self):
        import config as magtag_config
        self.assertGreater(
            magtag_config.USB_KEYBOARD_DISPLAY_TIMEOUT_SECONDS,
            magtag_config.EDITOR_TEST_TIMEOUT_SECONDS,
        )


class PhysicalLimitTest(unittest.TestCase):
    def test_both_devices_declare_the_same_authorised_ceilings(self):
        from magwrite_transport.live_session import (
            MAX_PARTIAL_REFRESHES, MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES,
        )
        magtag = read(*MAGTAG_ENTRY)
        self.assertIn("MAX_VIEWPORTS = %d" % MAX_VIEWPORT_FRAMES, magtag)
        self.assertIn("MAX_FRAMES = %d" % MAX_PROTOCOL_FRAMES, magtag)
        self.assertIn("MAX_STATUS_FRAMES = %d" % MAX_PROTOCOL_FRAMES, magtag)
        self.assertIn(
            "MAX_PARTIAL_REFRESHES = %d" % MAX_PARTIAL_REFRESHES, magtag
        )

    def test_the_completion_history_fits_every_authorised_refresh(self):
        """51 completions are possible, so a 32-entry history would overflow."""
        from magwrite_transport.live_session import MAX_PARTIAL_REFRESHES
        magtag = read(*MAGTAG_ENTRY)
        self.assertIn("COMPLETION_CAPACITY = 64", magtag)
        self.assertIn("completion_capacity=COMPLETION_CAPACITY", magtag)
        self.assertGreater(64, MAX_PARTIAL_REFRESHES + 1)

    def test_the_ack_tracker_can_hold_every_authorised_viewport(self):
        import config as magtag_config       # noqa: F401  (magtag path first)
        from magwrite_transport.live_session import (
            ACK_TRACKER_CAPACITY, MAX_VIEWPORT_FRAMES,
        )
        self.assertGreaterEqual(ACK_TRACKER_CAPACITY, MAX_VIEWPORT_FRAMES)

    def test_the_fruitjam_config_matches_the_session_defaults(self):
        from magwrite_transport.live_session import (
            ACK_TRACKER_CAPACITY, EVENT_QUEUE_CAPACITY, MAX_KEYBOARD_EVENTS,
            MIN_SEND_SECONDS,
        )
        source = read("fruitjam", "config.py")
        self.assertIn("USB_KEYBOARD_MAX_EVENTS = %d" % MAX_KEYBOARD_EVENTS, source)
        self.assertIn(
            "USB_KEYBOARD_ACK_TRACKER_CAPACITY = %d" % ACK_TRACKER_CAPACITY,
            source,
        )
        self.assertIn(
            "USB_KEYBOARD_QUEUE_CAPACITY = %d" % EVENT_QUEUE_CAPACITY, source
        )
        self.assertIn(
            "USB_KEYBOARD_MIN_SEND_SECONDS = %s" % MIN_SEND_SECONDS, source
        )

    def test_transmission_is_paced_to_the_panel_not_to_the_typing_rate(self):
        """Sending faster than a refresh only makes frames the MagTag drops."""
        from magwrite_transport.live_session import (
            MAX_PARTIAL_REFRESHES, MAX_PROTOCOL_FRAMES, MIN_SEND_SECONDS,
        )
        self.assertGreaterEqual(MIN_SEND_SECONDS, 2.0)
        # 500 events at 60 WPM is about 100 s of continuous typing. That must fit
        # the *binding* ceiling, which is partial refreshes rather than frames,
        # and must leave room in the status-frame budget at four statuses each.
        expected_frames = 100.0 / MIN_SEND_SECONDS
        self.assertLess(expected_frames, MAX_PARTIAL_REFRESHES)
        self.assertLess(expected_frames * 4, MAX_PROTOCOL_FRAMES)

    def test_the_refresh_ceiling_is_documented_as_the_binding_one(self):
        source = read("fruitjam", "magwrite_transport", "live_session.py")
        self.assertIn("binding", source)
        self.assertIn("binding", read("docs", "FRUITJAM_USB_KEYBOARD_TEST.md"))

    def test_the_entry_point_enforces_both_ceilings_in_its_own_loop(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("viewport frame limit exceeded", source)
        self.assertIn("input frame limit exceeded", source)


class EvidenceTest(unittest.TestCase):
    DOC = ("docs", "FRUITJAM_USB_KEYBOARD_TEST.md")
    CAPTURES = (
        ("docs", "FRUITJAM_USB_KEYBOARD_SERIAL.jsonl"),
        ("docs", "MAGTAG_USB_KEYBOARD_DISPLAY_SERIAL.jsonl"),
    )
    PROBE_CAPTURE = ("docs", "FRUITJAM_USB_KEYBOARD_PROBE.jsonl")

    def test_the_evidence_document_declares_a_status_up_front(self):
        source = read(*self.DOC)
        header = source.split("##")[0]
        self.assertRegex(header, r"\*\*Status: (NOT RUN|PASS|FAIL|INCONCLUSIVE)")

    def test_the_document_records_the_observed_device_identity(self):
        source = read(*self.DOC)
        for observed in (
            "0x36B0", "0x3002", "RDMCTMZT", "Wireless 2.4G Dongle",
            "adafruit_fruit_jam", "10.2.1", "detach_kernel_driver",
            "boot-protocol keyboard",
        ):
            self.assertIn(observed, source, observed)

    def test_the_document_records_the_real_configuration_descriptor(self):
        """The descriptor in the evidence must be the tested one, byte for byte."""
        from keyboard_simulator import REAL_CONFIGURATION_DESCRIPTOR
        source = read(*self.DOC).replace("\n", "")
        expected = "".join("%02X" % b for b in REAL_CONFIGURATION_DESCRIPTOR)
        self.assertIn(expected, source)

    def test_the_document_never_claims_an_untested_pass(self):
        """A PASS may only be claimed alongside a captured TEST_COMPLETE.

        The PASS criteria require ``TEST_COMPLETE``, so a results section that
        claims PASS while no capture contains it would be fabricated evidence.

        The unguarded probe is the one deliberate exception. It is read-only,
        arms nothing, and can never produce a ``TEST_COMPLETE``, so demanding
        one of it is meaningless. It pays for the exemption by having to state
        plainly that it is not a physical attempt and created no guard, which
        is exactly the claim that would be dishonest if it were untrue.
        """
        results = read(*self.DOC).split("## Results")[1]
        for section in re.split(r"\n### ", results):
            if "**PASS**" not in section:
                continue
            if section.startswith("Unguarded"):
                self.assertIn("not a physical attempt", section)
                self.assertIn("created no guard", section)
                continue
            captured = "".join(read(*parts) for parts in self.CAPTURES)
            self.assertIn("test_complete\": true", captured.replace("'", '"'))

    def test_a_probe_pass_is_never_mistaken_for_an_attempt(self):
        """The probe exemption must not become a way to smuggle in an attempt."""
        results = read(*self.DOC).split("## Results")[1]
        for heading in re.findall(r"### Unguarded[^\n]*", results):
            self.assertNotRegex(heading, r"(?i)attempt", heading)

    def test_every_results_attempt_carries_an_explicit_verdict(self):
        results = read(*self.DOC).split("## Results")[1]
        for heading in re.findall(r"### Attempt [^\n]*", results):
            self.assertRegex(heading, r"(PASS|FAIL|INCONCLUSIVE)", heading)

    def test_both_captures_are_parseable_jsonl(self):
        import json
        for parts in self.CAPTURES:
            lines = [
                line for line in read(*parts).splitlines() if line.strip()
            ]
            self.assertTrue(lines, parts)
            for line in lines:
                record = json.loads(line)
                self.assertIsInstance(record, dict, parts)
                self.assertIn("event", record, parts)

    def test_the_probe_capture_is_parseable_jsonl(self):
        import json
        lines = [
            line for line in read(*self.PROBE_CAPTURE).splitlines()
            if line.strip()
        ]
        self.assertTrue(lines)
        for line in lines:
            record = json.loads(line)
            self.assertIsInstance(record, dict)
            self.assertIn("event", record)

    def test_the_probe_capture_is_the_real_wired_keyboard(self):
        """The wired-keyboard claim must rest on the wired keyboard's own records."""
        probe = read(*self.PROBE_CAPTURE)
        self.assertIn('"product_id":"304E"', probe)
        self.assertIn('"product":"EPOMAKER TH40"', probe)
        self.assertIn('"nonzero_reports":735', probe)

    def test_the_probe_capture_retains_the_receiver_failure(self):
        """Re-testing the receiver must not erase that it failed again."""
        probe = read(*self.PROBE_CAPTURE)
        self.assertIn('"product":"Wireless 2.4G Dongle"', probe)
        self.assertIn("dongle_90s_after_ground_reseat", probe)

    def test_the_captures_are_the_real_observed_device(self):
        """The recorded capture must be from the device the doc describes."""
        fruitjam = read(*self.CAPTURES[0])
        self.assertIn('"vendor_id":"36B0"', fruitjam)
        self.assertIn('"product_id":"3002"', fruitjam)
        self.assertIn('"protocol":"boot_keyboard"', fruitjam)

    def test_the_document_states_the_scenarios_and_the_finish_key(self):
        source = read(*self.DOC)
        self.assertIn("MAGWRITE USB KEYBOARD TEST", source)
        self.assertIn("Hello, MagWrite! It's working.", source)
        self.assertIn("TODAY I WROTE A JORUNAL ENTRY", source)
        self.assertIn("TODAY I WROTE A JOURNAL ENTRY", source)
        self.assertIn("Escape", source)


class HostSafetyTest(unittest.TestCase):
    FORBIDDEN = (
        "board", "busio", "storage", "supervisor", "displayio", "digitalio",
        "usb.core", "usb_host", "microcontroller",
    )

    HOST_SAFE_MODULES = (
        "hid_keymap.py", "hid_keyboard.py", "keyboard_repeat.py",
        "usb_device_state.py", "usb_hid_descriptors.py",
        "usb_keyboard_adapter.py", "live_session.py",
    )

    def test_no_keyboard_module_imports_hardware_at_module_level(self):
        for name in self.HOST_SAFE_MODULES:
            source = read("fruitjam", "magwrite_transport", name)
            for module in self.FORBIDDEN:
                self.assertNotIn("import " + module, source, name)

    def test_the_backend_imports_usb_core_lazily_not_at_module_level(self):
        source = read("fruitjam", "magwrite_transport", "usb_host_backend.py")
        self.assertNotIn("\nimport usb", source)
        self.assertIn("def _load_usb_core", source)
        self.assertIn("    try:\n        import usb.core as usb_core", source)

    def test_the_backend_module_is_importable_on_the_host(self):
        from magwrite_transport import usb_host_backend
        self.assertTrue(hasattr(usb_host_backend, "UsbHostKeyboardBackend"))

    def test_no_hardware_module_is_loaded_by_ordinary_collection(self):
        for name in ("board", "busio", "storage", "supervisor", "usb"):
            self.assertNotIn(name, sys.modules, name)

    def test_the_pinned_driver_hash_is_unchanged(self):
        from magwrite.sha256 import sha256_file
        digest = sha256_file(os.path.join(MAGTAG, "uc8151.py"))
        self.assertEqual(digest, EXPECTED_DRIVER_SHA256)
        self.assertIn(EXPECTED_DRIVER_SHA256, read(*MAGTAG_ENTRY))


class GlyphAdditionTest(unittest.TestCase):
    """Glyphs are additive keys only, so proven frames stay bit-identical."""

    # Every glyph that existed before this phase, with its exact rows.
    PREVIOUS_KEYS = (
        " ", "/", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
        "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
        "<", ">", ".", ",", "'", "-", ":", "!", "?",
    )
    ADDED_KEYS = (";", '"', "(", ")") + tuple(
        chr(ord("a") + offset) for offset in range(26)
    )

    def setUp(self):
        from magwrite.test_pattern import GLYPHS
        self.glyphs = GLYPHS

    def test_every_previously_proven_glyph_is_still_present(self):
        for key in self.PREVIOUS_KEYS:
            self.assertIn(key, self.glyphs, repr(key))

    def test_the_uppercase_glyphs_are_untouched(self):
        # Spot-check the exact bitmaps recorded in the verified editor run.
        self.assertEqual(
            self.glyphs["A"], ("010", "101", "111", "101", "101")
        )
        self.assertEqual(self.glyphs["."], ("000", "000", "000", "000", "010"))

    def test_the_additions_are_exactly_the_expected_new_keys(self):
        for key in self.ADDED_KEYS:
            self.assertIn(key, self.glyphs, repr(key))
        self.assertEqual(
            len(self.glyphs), len(self.PREVIOUS_KEYS) + len(self.ADDED_KEYS)
        )

    def test_every_glyph_still_fits_the_unchanged_three_by_five_cell(self):
        for key, rows in self.glyphs.items():
            self.assertEqual(len(rows), 5, repr(key))
            for row in rows:
                self.assertEqual(len(row), 3, repr(key))
                self.assertTrue(set(row) <= {"0", "1"}, repr(key))

    def test_lowercase_is_visually_distinct_from_its_uppercase(self):
        for offset in range(26):
            lower = chr(ord("a") + offset)
            self.assertNotEqual(
                self.glyphs[lower], self.glyphs[lower.upper()], lower
            )

    def test_every_added_glyph_is_distinct_from_every_other_glyph(self):
        """Scoped to the additions.

        ``O`` and ``0`` already shared a bitmap in the proven table before this
        phase. Changing either would break bit-identity with the verified editor
        frames, so that pre-existing collision is documented rather than fixed;
        this asserts only that nothing *added* collides with anything.
        """
        self.assertEqual(self.glyphs["O"], self.glyphs["0"])
        prior = {}
        for key in self.PREVIOUS_KEYS:
            prior.setdefault(self.glyphs[key], key)
        added = {}
        for key in self.ADDED_KEYS:
            rows = self.glyphs[key]
            clash = prior.get(rows) or added.get(rows)
            self.assertIsNone(
                clash, "added %r collides with %r" % (key, clash)
            )
            added[rows] = key

    def test_the_renderer_can_draw_every_added_glyph(self):
        from magwrite.mono_canvas import MonoCanvas
        from magwrite.test_pattern import draw_text
        canvas = MonoCanvas()
        draw_text(canvas, "".join(self.ADDED_KEYS), 9, 24, 2)


if __name__ == "__main__":
    unittest.main()
