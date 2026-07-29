"""Device-entry, activation, and guard coverage for the V1 responsiveness phase.

The single most important property asserted here is negative: **this phase must
not touch the completed USB-keyboard milestone's guards.** Those four files
exist on the two boards and are the evidence of a physically verified
milestone. A phase that reused them, required their absence, or wrote to them
would destroy that record.

So the four completed-milestone guards are treated exactly like the twenty
older ones — as prior guards, protected — and this phase gets four new paths of
its own. Every device-entry line the phase adds is asserted here, statically
where it cannot be imported and behaviourally where it can, because both prior
physical blockers happened in device-entry code the host suite never reached.
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
    APPROVED_TEST_MODES, V1_RESPONSIVENESS_DISPLAY_MODE,
    validate_physical_test_activation,
)

FRUITJAM_MODE = "FRUITJAM_V1_RESPONSIVENESS"
MAGTAG_MODE = "MAGTAG_V1_RESPONSIVENESS_DISPLAY"

FRUITJAM_ENTRY = ("fruitjam", "hardware_v1_responsiveness_test.py")
MAGTAG_ENTRY = ("magtag", "hardware_v1_responsiveness_display_test.py")

COMPLETED_ENTRIES = (
    ("fruitjam", "hardware_usb_keyboard_test.py"),
    ("magtag", "hardware_usb_keyboard_display_test.py"),
)

# The four paths this phase introduces. Nothing else may be created.
NEW_GUARDS = (
    "/magwrite_v1_responsiveness.started",
    "/magwrite_v1_responsiveness.complete",
    "/magwrite_v1_responsiveness_display.started",
    "/magwrite_v1_responsiveness_display.complete",
)

# The four guards of the completed, physically verified USB-keyboard milestone.
# They must remain byte-identical and are never required to be absent.
COMPLETED_MILESTONE_GUARDS = (
    "/magwrite_usb_keyboard.started",
    "/magwrite_usb_keyboard.complete",
    "/magwrite_usb_keyboard_display.started",
    "/magwrite_usb_keyboard_display.complete",
)

# Every guard that existed before this phase, from all earlier milestones.
OLDER_GUARDS = (
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

PROTECTED_GUARDS = OLDER_GUARDS + COMPLETED_MILESTONE_GUARDS

DOC = ("docs", "MAGWRITE_V1_RESPONSIVENESS_TEST.md")
FRUITJAM_EVIDENCE = ("docs", "FRUITJAM_V1_RESPONSIVENESS_SERIAL.jsonl")
MAGTAG_EVIDENCE = ("docs", "MAGTAG_V1_RESPONSIVENESS_SERIAL.jsonl")

COMPLETED_EVIDENCE = (
    ("docs", "FRUITJAM_USB_KEYBOARD_SERIAL.jsonl"),
    ("docs", "MAGTAG_USB_KEYBOARD_DISPLAY_SERIAL.jsonl"),
    ("docs", "FRUITJAM_USB_KEYBOARD_TEST.md"),
)


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


def config_values(*parts):
    """Literal top-level assignments from a config module, without importing it."""
    values = {}
    for line in read(*parts).splitlines():
        if not line or line.startswith((" ", "\t", "#")) or "=" not in line:
            continue
        name, _, raw = line.partition("=")
        try:
            values[name.strip()] = ast.literal_eval(raw.strip())
        except (SyntaxError, ValueError):
            continue
    return values


class GuardSeparationTest(unittest.TestCase):
    """The completed milestone's guards must survive this phase untouched."""

    def test_the_new_guard_family_is_entirely_distinct(self):
        for guard in NEW_GUARDS:
            self.assertNotIn(guard, PROTECTED_GUARDS, guard)
        self.assertEqual(len(set(NEW_GUARDS)), 4)

    def test_no_new_guard_is_a_prefix_or_suffix_of_a_protected_one(self):
        """A near-miss path is as dangerous as a reused one."""
        for new in NEW_GUARDS:
            for protected in PROTECTED_GUARDS:
                self.assertFalse(new.startswith(protected), (new, protected))
                self.assertFalse(protected.startswith(new), (new, protected))

    def test_neither_entry_point_names_a_protected_guard_as_its_own(self):
        for parts in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*parts)
            for guard in OLDER_GUARDS:
                self.assertNotIn(guard, source, (parts[-1], guard))

    def test_neither_entry_point_requires_a_completed_guard_to_be_absent(self):
        """`exists(...)` must never be applied to the completed milestone."""
        for parts in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*parts)
            for guard in COMPLETED_MILESTONE_GUARDS:
                self.assertNotIn('exists("%s")' % guard, source, parts[-1])

    def test_neither_entry_point_ever_writes_a_protected_guard(self):
        for parts in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*parts)
            for guard in PROTECTED_GUARDS:
                self.assertNotIn('open("%s"' % guard, source, parts[-1])
                self.assertNotIn("remove(%s)" % guard, source, parts[-1])
        self.assertNotIn("os.remove", read(*FRUITJAM_ENTRY))
        self.assertNotIn("os.remove", read(*MAGTAG_ENTRY))

    def test_the_only_guards_written_are_this_phases_own(self):
        for parts, started, complete in (
            (FRUITJAM_ENTRY, NEW_GUARDS[0], NEW_GUARDS[1]),
            (MAGTAG_ENTRY, NEW_GUARDS[2], NEW_GUARDS[3]),
        ):
            source = read(*parts)
            self.assertIn('START = "%s"' % started, source)
            self.assertIn('COMPLETE = "%s"' % complete, source)
            written = set(re.findall(r'open\((START|COMPLETE)', source))
            self.assertTrue(written.issubset({"START", "COMPLETE"}))

    def test_each_device_still_refuses_if_its_own_guard_exists(self):
        self.assertIn(
            "Fruit Jam V1 responsiveness guard exists", read(*FRUITJAM_ENTRY)
        )
        self.assertIn(
            "MagTag V1 responsiveness display guard exists", read(*MAGTAG_ENTRY)
        )
        for parts in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*parts)
            self.assertIn("if exists(START) or exists(COMPLETE):", source)

    def test_the_completed_milestone_entry_points_are_unmodified(self):
        """This phase is a sibling, not an edit of proven code."""
        for parts in COMPLETED_ENTRIES:
            source = read(*parts)
            self.assertNotIn("v1_responsiveness", source, parts[-1])
            self.assertNotIn("V1_RESPONSIVENESS", source, parts[-1])

    def test_the_completed_milestone_keeps_its_own_guard_paths(self):
        fruitjam = read("fruitjam", "hardware_usb_keyboard_test.py")
        self.assertIn('START = "/magwrite_usb_keyboard.started"', fruitjam)
        magtag = read("magtag", "hardware_usb_keyboard_display_test.py")
        self.assertIn(
            'START = "/magwrite_usb_keyboard_display.started"', magtag
        )

    def test_the_full_protected_inventory_is_the_expected_size(self):
        self.assertEqual(len(OLDER_GUARDS), 20)
        self.assertEqual(len(COMPLETED_MILESTONE_GUARDS), 4)
        self.assertEqual(len(set(PROTECTED_GUARDS)), 24)


class ActivationDefaultTest(unittest.TestCase):
    def test_the_fruitjam_phase_is_disabled_by_default(self):
        source = read("fruitjam", "config.py")
        self.assertIn("ENABLE_V1_RESPONSIVENESS_TEST = False", source)
        self.assertIn('V1_RESPONSIVENESS_TEST_MODE = "DISABLED"', source)

    def test_the_magtag_phase_is_disabled_by_default(self):
        source = read("magtag", "config.py")
        self.assertIn('V1_RESPONSIVENESS_DISPLAY_TEST_MODE = "DISABLED"', source)

    def test_every_activation_flag_on_both_boards_is_still_off(self):
        fruitjam = config_values("fruitjam", "config.py")
        magtag = config_values("magtag", "config.py")
        for name, value in fruitjam.items():
            if name.startswith("ENABLE_"):
                self.assertFalse(value, name)
            if name.endswith("_TEST_MODE"):
                self.assertEqual(value, "DISABLED", name)
        for name, value in magtag.items():
            if name.startswith("ENABLE_"):
                self.assertFalse(value, name)
            if name.endswith("_TEST_MODE"):
                self.assertEqual(value, "DISABLED", name)
        self.assertFalse(magtag["ENABLE_PHYSICAL_DISPLAY"])

    def test_the_shipped_configs_refuse_the_run_as_loaded(self):
        import config as magtag_config
        self.assertFalse(magtag_config.ENABLE_PHYSICAL_DISPLAY)
        self.assertEqual(
            magtag_config.V1_RESPONSIVENESS_DISPLAY_TEST_MODE, "DISABLED"
        )
        with self.assertRaises(RuntimeError):
            validate_physical_test_activation(
                magtag_config, V1_RESPONSIVENESS_DISPLAY_MODE
            )

    def test_the_new_display_mode_is_approved_but_distinct(self):
        self.assertIn(V1_RESPONSIVENESS_DISPLAY_MODE, APPROVED_TEST_MODES)
        self.assertEqual(V1_RESPONSIVENESS_DISPLAY_MODE, MAGTAG_MODE)
        self.assertNotEqual(
            V1_RESPONSIVENESS_DISPLAY_MODE, "MAGTAG_USB_KEYBOARD_DISPLAY"
        )

    def test_the_two_activation_modes_are_distinct_from_every_other(self):
        self.assertNotEqual(FRUITJAM_MODE, MAGTAG_MODE)
        self.assertEqual(len(set(APPROVED_TEST_MODES)), len(APPROVED_TEST_MODES))

    def test_the_fruitjam_entry_point_requires_every_gate(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("ENABLE_V1_RESPONSIVENESS_TEST", source)
        self.assertIn("V1_RESPONSIVENESS_TEST_MODE", source)
        self.assertIn("V1 responsiveness gate not armed", source)
        self.assertIn("UART_TX_PIN_ALIAS", source)
        self.assertIn("UART_RX_PIN_ALIAS", source)
        self.assertIn("VERSION != 1 or MAX_PAYLOAD_SIZE != 192", source)

    def test_the_magtag_entry_point_requires_every_gate(self):
        source = read(*MAGTAG_ENTRY)
        for gate in (
            "validate_physical_test_activation", "ENABLE_UART_RECEIVER",
            "ENABLE_UART_STATUS_TX", "V1_RESPONSIVENESS_DISPLAY_TEST_MODE",
            "V1 responsiveness display gate not armed",
            "driver hash mismatch",
        ):
            self.assertIn(gate, source, gate)

    def test_every_gate_is_checked_before_any_hardware_is_touched(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertLess(source.index("gate not armed"), source.index("busio.UART"))
        self.assertLess(
            source.index("gate not armed"),
            source.index("UsbHostKeyboardBackend("),
        )
        magtag = read(*MAGTAG_ENTRY)
        self.assertLess(
            magtag.index("driver hash mismatch"), magtag.index("busio.UART")
        )

    def test_the_boot_remount_gate_arms_this_phases_mode(self):
        """A prior physical blocker was exactly this: a boot gate that never
        armed the new mode, so the MagTag could not persist its guard."""
        source = read("magtag", "hardware_test_boot.py")
        self.assertIn('"%s"' % MAGTAG_MODE, source)
        self.assertIn("storage.remount", source)

    def test_the_boot_gate_lists_exactly_the_approved_modes(self):
        source = read("magtag", "hardware_test_boot.py")
        listed = set(re.findall(r'"([A-Z0-9_]+)"', source))
        self.assertEqual(listed, set(APPROVED_TEST_MODES))

    def test_no_guard_is_claimed_before_every_gate_has_passed(self):
        for parts in (FRUITJAM_ENTRY, MAGTAG_ENTRY):
            source = read(*parts)
            self.assertLess(
                source.index("if exists(START) or exists(COMPLETE):"),
                source.index('open(START, "w")'),
                parts[-1],
            )
            self.assertLess(
                source.index('open(START, "w")'), source.index("busio.UART"),
                parts[-1],
            )


class EntryPointBehaviourTest(unittest.TestCase):
    """What the entry points construct, asserted without importing them."""

    def test_the_fruitjam_entry_uses_the_adaptive_pacer(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("from magwrite_transport.pacing import DisplayPacer", source)
        self.assertIn("pacer=DisplayPacer(", source)
        for name in (
            "USB_KEYBOARD_COALESCE_SECONDS", "USB_KEYBOARD_QUIET_SECONDS",
            "USB_KEYBOARD_CAUGHT_UP_MIN_SEND_SECONDS",
            "USB_KEYBOARD_SUSTAINED_MIN_SEND_SECONDS",
        ):
            self.assertIn("config." + name, source, name)

    def test_the_fruitjam_entry_measures_latency(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("from magwrite_transport.latency import LatencyRecorder", source)
        self.assertIn("latency=LatencyRecorder()", source)

    def test_the_fruitjam_entry_selects_the_keyboard_layout(self):
        self.assertIn(
            "layout=config.USB_KEYBOARD_LAYOUT", read(*FRUITJAM_ENTRY)
        )

    def test_the_fruitjam_entry_finishes_on_the_application_key(self):
        """Escape is unreachable on the TH40 without leaving USB mode."""
        source = read(*FRUITJAM_ENTRY)
        self.assertIn('"finish_key": "APPLICATION"', source)

    def test_the_entry_points_enforce_both_ceilings_in_their_own_loops(self):
        source = read(*FRUITJAM_ENTRY)
        self.assertIn("viewport frame limit exceeded", source)
        self.assertIn("input frame limit exceeded", source)
        magtag = read(*MAGTAG_ENTRY)
        for limit in (
            "viewport limit exceeded", "input frame limit exceeded",
            "status frame limit exceeded", "refresh limit exceeded",
        ):
            self.assertIn(limit, magtag, limit)

    def test_the_authorised_ceilings_match_the_session_module(self):
        from magwrite_transport.live_session import (
            MAX_PARTIAL_REFRESHES, MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES,
        )
        magtag = read(*MAGTAG_ENTRY)
        self.assertIn("MAX_VIEWPORTS = %d" % MAX_VIEWPORT_FRAMES, magtag)
        self.assertIn("MAX_FRAMES = %d" % MAX_PROTOCOL_FRAMES, magtag)
        self.assertIn(
            "MAX_PARTIAL_REFRESHES = %d" % MAX_PARTIAL_REFRESHES, magtag
        )

    def test_the_magtag_entry_reports_panel_timings_for_the_comparison(self):
        magtag = read(*MAGTAG_ENTRY)
        for field in (
            "partial_refresh_minimum_ms", "partial_refresh_maximum_ms",
            "partial_refresh_mean_ms", "refresh_durations_ms",
        ):
            self.assertIn(field, magtag, field)

    def test_the_magtag_entry_pins_the_same_driver_hash(self):
        from magwrite.sha256 import sha256_file
        digest = sha256_file(os.path.join(MAGTAG, "uc8151.py"))
        self.assertIn(digest, read(*MAGTAG_ENTRY))

    def test_both_summaries_are_named_for_this_phase_not_the_completed_one(self):
        self.assertIn(
            '"v1_responsiveness_test_summary"', read(*FRUITJAM_ENTRY)
        )
        self.assertIn(
            '"event": "v1_responsiveness_display_test_summary"',
            read(*MAGTAG_ENTRY),
        )


class EvidenceSeparationTest(unittest.TestCase):
    """This phase writes its own evidence and never touches the completed set."""

    def test_the_plan_document_exists_and_names_the_new_guards(self):
        source = read(*DOC)
        for guard in NEW_GUARDS:
            self.assertIn(guard, source, guard)

    def test_the_plan_states_the_completed_guards_are_protected(self):
        source = read(*DOC)
        for guard in COMPLETED_MILESTONE_GUARDS:
            self.assertIn(guard, source, guard)
        self.assertIn("byte-identical", source)

    def test_the_plan_names_its_own_evidence_files(self):
        source = read(*DOC)
        self.assertIn("FRUITJAM_V1_RESPONSIVENESS_SERIAL.jsonl", source)
        self.assertIn("MAGTAG_V1_RESPONSIVENESS_SERIAL.jsonl", source)

    def test_the_plan_does_not_claim_a_physical_run_happened(self):
        source = read(*DOC)
        self.assertIn("NOT YET RUN", source)

    def test_the_plan_requires_every_named_measurement(self):
        source = read(*DOC).lower()
        for measurement in (
            "keypress to frame transmission",
            "keypress to refresh start",
            "keypress to refresh completion",
            "pause to catch-up transmission",
            "maximum visible lag",
            "frame count under several short pauses",
        ):
            self.assertIn(measurement, source, measurement)

    def test_the_plan_records_home_end_and_delete_as_physically_untested(self):
        source = read(*DOC)
        self.assertIn("physically untested", source)
        for key in ("Home", "End", "Delete"):
            self.assertIn(key, source, key)

    def test_the_completed_evidence_is_not_reused_as_this_phases_evidence(self):
        source = read(*DOC)
        for parts in COMPLETED_EVIDENCE:
            self.assertNotIn(
                "append to `%s`" % parts[-1], source, parts[-1]
            )

    def test_the_completed_evidence_files_still_exist(self):
        for parts in COMPLETED_EVIDENCE:
            self.assertTrue(
                os.path.exists(os.path.join(ROOT, *parts)), parts[-1]
            )


class HostSafetyTest(unittest.TestCase):
    FORBIDDEN = (
        "board", "busio", "storage", "supervisor", "displayio", "digitalio",
        "usb.core", "usb_host", "microcontroller",
    )

    def test_the_latency_module_imports_no_hardware(self):
        source = read("fruitjam", "magwrite_transport", "latency.py")
        for module in self.FORBIDDEN:
            self.assertNotIn("import " + module, source, module)

    def test_the_latency_module_imports_under_cpython(self):
        from magwrite_transport import latency
        self.assertTrue(hasattr(latency, "LatencyRecorder"))

    def test_the_latency_module_owns_no_guard_and_writes_no_file(self):
        source = read("fruitjam", "magwrite_transport", "latency.py")
        self.assertNotIn("/magwrite_", source)
        self.assertIsNone(re.search(r"(?<![.\w])open\(", source))

    def test_no_hardware_module_is_loaded_by_ordinary_collection(self):
        for name in ("board", "busio", "storage", "supervisor", "usb"):
            self.assertNotIn(name, sys.modules, name)


if __name__ == "__main__":
    unittest.main()
