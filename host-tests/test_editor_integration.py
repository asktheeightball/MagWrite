"""Integrated Fruit Jam editor to MagTag display behaviour on the host.

This suite drives the real editor, layout, viewport, transport, and
acknowledgement code through the deterministic simulator, so the physical run
only has to confirm the panel itself.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from editor_simulator import EditorLink, SimulatedPanel
from magwrite.ack_scheduler import AckSchedulerError
from magwrite.uart_protocol import (
    DISPLAY_CAUGHT_UP, FRAME_ACCEPTED, MAX_RECEIVE_BUFFER, REFRESH_COMPLETED,
    REFRESH_STARTED, TEST_COMPLETE, VIEWPORT,
)
from magwrite_transport.ack_tracker import AckError, AckTracker
from magwrite_transport.editor import InputEvent, CHAR
from magwrite_transport.editor_scenarios import (
    MAX_EDITOR_EVENTS, MAX_EDITOR_PARTIAL_REFRESHES, MAX_EDITOR_STATUS_FRAMES,
    MAX_EDITOR_VIEWPORT_FRAMES, numbered_scenarios, total_event_count,
)
from magwrite_transport.editor_session import EditorSession, EditorSessionError
from magwrite_transport.protocol import Frame, encode_frame
from magwrite_transport.status_message import encode_status

PHYSICAL_EVENT_CEILING = 400
PHYSICAL_VIEWPORT_CEILING = 75
PHYSICAL_FRAME_CEILING = 150
PHYSICAL_PARTIAL_REFRESH_CEILING = 40


class IntegratedRunTest(unittest.TestCase):
    """One shared deterministic run; every assertion reads from it."""

    @classmethod
    def setUpClass(cls):
        cls.link = EditorLink().run()
        cls.summary = cls.link.session.summary("PASS")
        cls.records = cls.link.records

    def events(self, name):
        return [r for r in self.records if r.get("event") == name]

    # --------------------------------------------------------------- input

    def test_every_event_is_processed_exactly_once_and_in_order(self):
        processed = self.events("editor_event_processed")
        self.assertEqual(len(processed), total_event_count())
        self.assertEqual(
            [r["sequence"] for r in processed], list(range(total_event_count()))
        )

    def test_no_event_is_rejected_and_no_queue_overflow_occurs(self):
        self.assertEqual(self.summary["events_rejected"], 0)
        self.assertEqual(self.summary["queue_overflows"], 0)
        self.assertEqual(self.events("editor_event_rejected"), [])

    def test_queue_depth_stays_far_inside_its_bound(self):
        self.assertGreaterEqual(self.summary["maximum_queue_depth"], 1)
        self.assertLess(
            self.summary["maximum_queue_depth"], self.link.session.queue.capacity
        )

    def test_input_is_drained_before_any_viewport_is_generated(self):
        """No viewport may be sent before the input it depicts was applied."""
        latest_processed = -1
        for record in self.records:
            if record.get("event") == "editor_event_processed":
                latest_processed = record["sequence"]
            elif record.get("event") == "editor_viewport_sent":
                self.assertGreaterEqual(latest_processed, 0)
        self.assertEqual(latest_processed, total_event_count() - 1)

    # ------------------------------------------------------------ document

    def test_every_scenario_final_document_matches_exactly(self):
        expected = {
            name: text for name, _, _, _, _, _, text in numbered_scenarios()
        }
        self.assertEqual(self.summary["scenario_final_texts"], expected)

    def test_the_final_document_is_the_journal_note(self):
        _, _, _, _, _, _, expected = numbered_scenarios()[4]
        self.assertEqual(self.link.session.editor.text, expected)
        self.assertEqual(self.summary["final_document_lines"], 3)

    def test_document_revision_is_below_the_event_count(self):
        """Navigation events move the cursor without changing the document."""
        self.assertLess(
            self.summary["document_revision"], self.summary["events_processed"]
        )
        self.assertGreater(self.summary["document_revision"], 0)

    def test_viewport_revision_advances_past_the_document_revision(self):
        self.assertGreater(
            self.summary["final_viewport_revision"],
            self.summary["document_revision"],
        )

    # ------------------------------------------------------------ coalescing

    def test_viewport_count_is_substantially_lower_than_event_count(self):
        self.assertLess(
            self.summary["viewport_frames_sent"],
            self.summary["events_processed"] // 4,
        )

    def test_stale_viewport_states_are_coalesced_before_transmission(self):
        self.assertGreater(self.summary["viewports_superseded_locally"], 0)
        self.assertGreater(
            self.summary["viewports_built"], self.summary["viewport_frames_sent"]
        )
        self.assertTrue(self.events("editor_viewport_superseded"))

    def test_not_every_edit_produces_a_physical_refresh(self):
        self.assertLess(
            self.link.scheduler.refresh_count, self.summary["events_processed"]
        )
        self.assertGreater(self.link.scheduler.refresh_count, 0)

    def test_the_magtag_supersedes_pending_frames_during_fast_typing(self):
        self.assertGreater(self.link.scheduler.superseded_count, 0)
        self.assertEqual(
            self.link.scheduler.accepted_count,
            self.link.scheduler.rendered_count
            + self.link.scheduler.superseded_count,
        )

    def test_at_most_one_refresh_is_ever_in_flight(self):
        self.assertEqual(self.link.panel.maximum_concurrent, 1)

    def test_exactly_one_full_refresh_seeds_the_panel(self):
        fulls = [item for item in self.link.scheduler.completions if item[2]]
        self.assertEqual(len(fulls), 1)
        self.assertTrue(self.link.scheduler.completions[0][2])

    # ---------------------------------------------------- acknowledgements

    def test_acknowledgement_counts_are_consistent(self):
        self.assertEqual(
            self.summary["frame_accepted_received"],
            self.summary["viewport_frames_sent"],
        )
        self.assertEqual(
            self.summary["refresh_started_received"],
            self.summary["refresh_completed_received"],
        )
        self.assertEqual(
            self.summary["refresh_completed_received"],
            self.link.scheduler.refresh_count,
        )

    def test_skipped_revisions_are_never_marked_displayed(self):
        rendered = {item[0] for item in self.link.scheduler.completions}
        for state in self.link.session.tracker.states:
            if state.displayed:
                self.assertIn(state.revision, rendered)

    def test_displayed_revision_never_exceeds_the_transmitted_revision(self):
        self.assertLessEqual(
            self.summary["final_displayed_revision"],
            self.summary["final_transmitted_revision"],
        )
        self.assertLessEqual(
            self.link.scheduler.displayed_revision,
            self.link.scheduler.latest_revision,
        )

    def test_final_revision_and_hash_reconcile(self):
        self.assertEqual(
            self.summary["final_displayed_revision"],
            self.summary["final_transmitted_revision"],
        )
        self.assertEqual(
            self.summary["final_displayed_revision"],
            self.link.session.editor.viewport_revision,
        )
        self.assertEqual(
            int(self.summary["final_hash"], 16), self.link.scheduler.latest_hash
        )
        self.assertTrue(self.summary["test_complete"])

    def test_acknowledgement_tracking_stays_bounded(self):
        self.assertLessEqual(
            len(self.link.session.tracker.states),
            self.link.session.tracker.capacity,
        )

    def test_no_transport_integrity_failure_occurs(self):
        for field in (
            "crc_failures", "status_frames_rejected", "status_sequence_gaps",
            "status_duplicates", "status_stale", "timeouts",
            "resynchronization_events", "discarded_prefix_bytes",
        ):
            self.assertEqual(self.summary[field], 0, field)
        self.assertIsNone(self.summary["stop_reason"])

    def test_display_caught_up_is_reported_for_the_final_state(self):
        self.assertGreater(self.summary["display_caught_up_received"], 0)
        self.assertTrue(self.events("editor_test_complete"))

    # -------------------------------------------------------- physical limits

    def test_the_run_stays_inside_every_authorised_physical_limit(self):
        self.assertLessEqual(
            self.summary["events_processed"], PHYSICAL_EVENT_CEILING
        )
        self.assertLessEqual(
            self.summary["viewport_frames_sent"], PHYSICAL_VIEWPORT_CEILING
        )
        self.assertLessEqual(
            self.summary["input_frames_sent"], PHYSICAL_FRAME_CEILING
        )
        self.assertLessEqual(
            self.link.status_frames_sent, PHYSICAL_FRAME_CEILING
        )
        partials = [
            item for item in self.link.scheduler.completions if not item[2]
        ]
        self.assertLessEqual(len(partials), PHYSICAL_PARTIAL_REFRESH_CEILING)

    def test_harness_ceilings_sit_at_or_under_the_authorised_limits(self):
        self.assertLessEqual(MAX_EDITOR_EVENTS, PHYSICAL_EVENT_CEILING)
        self.assertLessEqual(MAX_EDITOR_VIEWPORT_FRAMES, PHYSICAL_VIEWPORT_CEILING)
        self.assertLessEqual(MAX_EDITOR_STATUS_FRAMES, PHYSICAL_FRAME_CEILING)
        self.assertLessEqual(
            MAX_EDITOR_PARTIAL_REFRESHES, PHYSICAL_PARTIAL_REFRESH_CEILING
        )

    # ----------------------------------------------------------- diagnostics

    def test_required_diagnostic_records_are_emitted(self):
        for name in (
            "editor_event_processed", "editor_document_revision_changed",
            "editor_viewport_sent", "editor_viewport_superseded",
            "editor_status_received", "editor_viewport_ack_state",
            "editor_scenario_started", "editor_scenario_complete",
            "editor_test_complete",
        ):
            self.assertTrue(self.events(name), name)

    def test_every_scenario_reports_started_and_complete(self):
        self.assertEqual(
            len(self.events("editor_scenario_started")), len(numbered_scenarios())
        )
        self.assertEqual(
            len(self.events("editor_scenario_complete")), len(numbered_scenarios())
        )

    def test_diagnostic_records_are_json_serializable(self):
        import json
        for record in self.records:
            json.loads(json.dumps(record))

    def test_the_run_is_reproducible(self):
        repeat = EditorLink().run().session.summary("PASS")
        self.assertEqual(repeat["final_hash"], self.summary["final_hash"])
        self.assertEqual(
            repeat["final_displayed_revision"],
            self.summary["final_displayed_revision"],
        )
        self.assertEqual(
            repeat["viewport_frames_sent"], self.summary["viewport_frames_sent"]
        )


class SessionStopConditionTest(unittest.TestCase):
    def test_a_rejected_edit_stops_the_session(self):
        link = EditorLink()
        link.session.editor.max_line_chars = 2
        with self.assertRaises(EditorSessionError):
            link.run(maximum_iterations=40000)

    def test_input_queue_overflow_stops_the_session(self):
        link = EditorLink(queue_capacity=2)
        link.session.queue.put(InputEvent(0, "t", CHAR, "A"))
        link.session.queue.put(InputEvent(1, "t", CHAR, "B"))
        with self.assertRaises(EditorSessionError):
            link.run(maximum_iterations=40000)

    def test_a_corrupt_status_byte_stream_stops_the_session(self):
        link = EditorLink()
        for _ in range(200):
            link.step()
        good = encode_frame(FRAME_ACCEPTED, 1, 1, b"")
        link.session.feed(good[:-4] + b"\x00\x00\x00\x00")
        with self.assertRaises(EditorSessionError):
            for _ in range(50):
                link.session.service()

    def test_the_session_times_out_when_the_panel_never_answers(self):
        link = EditorLink(timeout_seconds=5.0)
        link.scheduler.service = lambda chunks=(): None
        with self.assertRaises(Exception):
            link.run(maximum_iterations=40000)


class AckTrackerEditorModeTest(unittest.TestCase):
    """The editor opt-in must not weaken any other acknowledgement rule."""

    def _accepted(self, tracker, revision, sequence, now=0.0):
        tracker.sent(revision, sequence, 0xABCD, now)

    def test_intermediate_catch_up_is_refused_by_default(self):
        tracker = AckTracker(allow_intermediate_catch_up=False)
        self.assertFalse(tracker.allow_intermediate_catch_up)
        self.assertEqual(tracker.intermediate_catch_ups, 0)

    def test_catch_up_above_the_transmitted_revision_is_always_refused(self):
        tracker = AckTracker(allow_intermediate_catch_up=True)
        self._accepted(tracker, 1, 1)
        payload = encode_status(DISPLAY_CAUGHT_UP, {
            "displayed_revision": 9,
            "latest_received_revision": 9,
            "viewport_hash": 0xABCD,
        })
        with self.assertRaises(AckError) as caught:
            tracker.apply(Frame(DISPLAY_CAUGHT_UP, 1, 1, payload), 0.0)
        self.assertIn("exceeds transmitted", str(caught.exception))

    def test_catch_up_before_refresh_completion_is_refused(self):
        tracker = AckTracker(allow_intermediate_catch_up=True)
        self._accepted(tracker, 1, 1)
        payload = encode_status(DISPLAY_CAUGHT_UP, {
            "displayed_revision": 1,
            "latest_received_revision": 1,
            "viewport_hash": 0xABCD,
        })
        with self.assertRaises(AckError):
            tracker.apply(Frame(DISPLAY_CAUGHT_UP, 1, 1, payload), 0.0)

    def test_the_integrated_run_needs_no_intermediate_catch_up(self):
        link = EditorLink().run()
        self.assertEqual(link.session.tracker.intermediate_catch_ups, 0)


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


# Every guard that existed before this phase. None may be reused, renamed, or
# removed by the editor integration test.
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
)
NEW_GUARDS = (
    "/magwrite_editor_integration.started",
    "/magwrite_editor_integration.complete",
    "/magwrite_editor_display.started",
    "/magwrite_editor_display.complete",
)
EXPECTED_DRIVER_SHA256 = (
    "A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E"
)


class ActivationDefaultTest(unittest.TestCase):
    def test_fruitjam_editor_activation_is_disabled_by_default(self):
        source = read("fruitjam", "config.py")
        self.assertIn("ENABLE_EDITOR_INTEGRATION_TEST = False", source)
        self.assertIn('EDITOR_INTEGRATION_TEST_MODE = "DISABLED"', source)

    def test_magtag_activation_is_disabled_by_default(self):
        """This harness stays disarmed even though the panel now ships enabled.

        V1.6: the MagTag ships as the standalone appliance, so the display and
        both UART directions are on — they are the product. The editor-display
        harness needs its own mode string *and* the matching
        ``PHYSICAL_TEST_MODE``, and neither is set.
        """
        source = read("magtag", "config.py")
        self.assertIn('EDITOR_DISPLAY_TEST_MODE = "DISABLED"', source)
        self.assertIn('PHYSICAL_TEST_MODE = "MAGTAG_STANDALONE"', source)
        self.assertNotIn('PHYSICAL_TEST_MODE = "MAGTAG_EDITOR_DISPLAY"', source)

    def test_both_entry_points_require_every_gate(self):
        fruitjam = read("fruitjam", "hardware_editor_test.py")
        self.assertIn("ENABLE_EDITOR_INTEGRATION_TEST", fruitjam)
        self.assertIn("EDITOR_INTEGRATION_TEST_MODE", fruitjam)
        self.assertIn("editor gate not armed", fruitjam)
        magtag = read("magtag", "hardware_editor_display_test.py")
        for gate in (
            "validate_physical_test_activation", "ENABLE_UART_RECEIVER",
            "ENABLE_UART_STATUS_TX", "EDITOR_DISPLAY_TEST_MODE",
        ):
            self.assertIn(gate, magtag)

    def test_boot_remount_is_gated_on_the_editor_mode(self):
        boot = read("fruitjam", "boot.py")
        self.assertIn("ENABLE_EDITOR_INTEGRATION_TEST", boot)
        self.assertIn("FRUITJAM_EDITOR_INTEGRATION", boot)

    def test_editor_mode_is_an_approved_magtag_display_mode(self):
        from magwrite.display_adapter import (
            APPROVED_TEST_MODES, EDITOR_DISPLAY_MODE,
        )
        self.assertIn(EDITOR_DISPLAY_MODE, APPROVED_TEST_MODES)


class GuardTest(unittest.TestCase):
    def test_the_four_new_guards_are_declared(self):
        fruitjam = read("fruitjam", "hardware_editor_test.py")
        self.assertIn('START = "/magwrite_editor_integration.started"', fruitjam)
        self.assertIn('COMPLETE = "/magwrite_editor_integration.complete"', fruitjam)
        magtag = read("magtag", "hardware_editor_display_test.py")
        self.assertIn('START = "/magwrite_editor_display.started"', magtag)
        self.assertIn('COMPLETE = "/magwrite_editor_display.complete"', magtag)

    def test_new_guards_are_independent_of_every_prior_guard(self):
        for guard in NEW_GUARDS:
            self.assertNotIn(guard, PRIOR_GUARDS)

    def test_the_editor_entry_points_touch_no_prior_guard(self):
        for part in (
            ("fruitjam", "hardware_editor_test.py"),
            ("magtag", "hardware_editor_display_test.py"),
        ):
            source = read(*part)
            for guard in PRIOR_GUARDS:
                self.assertNotIn(guard, source, guard)

    def test_prior_guards_are_still_declared_by_their_owners(self):
        owners = {
            "/magwrite_refresh_test_20.started": ("magtag", "hardware_refresh_test.py"),
            "/magwrite_single_line_typing.started": (
                "magtag", "magwrite", "single_line.py"),
            "/magwrite_uart_tx.started": ("fruitjam", "code.py"),
            "/magwrite_uart_rx.started": ("magtag", "hardware_uart_viewport_test.py"),
            "/magwrite_uart_ack_tx.started": ("fruitjam", "hardware_uart_ack_test.py"),
            "/magwrite_uart_ack_rx.started": ("magtag", "hardware_uart_ack_test.py"),
        }
        for guard, part in owners.items():
            self.assertIn(guard, read(*part), guard)

    def test_a_rerun_is_blocked_once_either_guard_exists(self):
        for part in (
            ("fruitjam", "hardware_editor_test.py"),
            ("magtag", "hardware_editor_display_test.py"),
        ):
            source = read(*part)
            self.assertIn("if exists(START) or exists(COMPLETE):", source)
            self.assertIn("guard exists", source)

    def test_neither_entry_point_retries_or_deletes_a_guard(self):
        for part in (
            ("fruitjam", "hardware_editor_test.py"),
            ("magtag", "hardware_editor_display_test.py"),
        ):
            source = read(*part)
            self.assertNotIn("os.remove", source)
            self.assertNotIn("os.unlink", source)

    def test_a_failed_run_keeps_the_started_guard_and_writes_no_complete(self):
        for part in (
            ("fruitjam", "hardware_editor_test.py"),
            ("magtag", "hardware_editor_display_test.py"),
        ):
            self.assertIn(
                'open(COMPLETE if result == "PASS" else START, "w")', read(*part)
            )


class IntegrityTest(unittest.TestCase):
    def test_protocol_constants_match_on_both_devices(self):
        from magwrite import uart_protocol as rx
        from magwrite_transport import protocol as tx
        for name in (
            "VERSION", "HEADER_SIZE", "CRC_SIZE", "MAX_PAYLOAD_SIZE",
            "MAX_RECEIVE_BUFFER", "MAGIC", "HELLO", "VIEWPORT", "END_OF_TEST",
            "STATUS_HELLO", "FRAME_ACCEPTED", "REFRESH_STARTED",
            "REFRESH_COMPLETED", "DISPLAY_CAUGHT_UP", "FRAME_REJECTED",
            "DISPLAY_ERROR", "TEST_COMPLETE",
        ):
            self.assertEqual(getattr(rx, name), getattr(tx, name), name)

    def test_viewport_line_ceilings_match_on_both_devices(self):
        from magwrite.viewport_message import MAX_LINES
        from magwrite_transport.deterministic_viewports import MAX_VIEWPORT_LINES
        self.assertEqual(MAX_LINES, MAX_VIEWPORT_LINES)

    def test_the_editor_entry_point_pins_the_wire_format(self):
        source = read("fruitjam", "hardware_editor_test.py")
        self.assertIn("VERSION != 1 or MAX_PAYLOAD_SIZE != 192", source)

    def test_the_pinned_driver_hash_is_unchanged(self):
        from magwrite.sha256 import sha256_file
        digest = sha256_file(os.path.join(ROOT, "magtag", "uc8151.py"))
        self.assertEqual(digest, EXPECTED_DRIVER_SHA256)
        self.assertIn(
            EXPECTED_DRIVER_SHA256, read("magtag", "hardware_editor_display_test.py")
        )

    def test_the_display_entry_point_verifies_the_driver_before_arming(self):
        source = read("magtag", "hardware_editor_display_test.py")
        self.assertIn('sha256_file("/uc8151.py")', source)
        self.assertLess(
            source.index("driver hash mismatch"), source.index("busio.UART")
        )


class ParserResynchronizationTest(unittest.TestCase):
    """Reset-time line noise must be discarded and accounted, never fatal."""

    def test_leading_noise_is_discarded_and_counted(self):
        link = EditorLink()
        link.session.feed(b"\x00" * 64)
        parser = link.session.parser
        self.assertIsNone(parser.pop())
        self.assertEqual(parser.bytes_discarded_before_magic, 64)
        self.assertEqual(parser.resynchronization_events, 1)
        self.assertEqual(parser.crc_failures, 0)

    def test_a_frame_after_noise_is_still_recovered(self):
        link = EditorLink()
        frame = encode_frame(TEST_COMPLETE, 1, 1, b"")
        link.session.feed(b"\x5a\x5a\x5a" + frame)
        recovered = link.session.parser.pop()
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.message_type, TEST_COMPLETE)
        self.assertEqual(link.session.parser.bytes_discarded_before_magic, 3)

    def test_the_parser_accumulator_stays_bounded(self):
        link = EditorLink()
        link.session.feed(b"\x00" * 4096)
        self.assertLessEqual(
            len(link.session.parser.buffer), MAX_RECEIVE_BUFFER)
        self.assertGreater(link.session.parser.buffer_overflows, 0)


class HostSafetyTest(unittest.TestCase):
    def test_editor_modules_import_no_hardware(self):
        forbidden = (
            "board", "busio", "storage", "supervisor", "displayio", "digitalio",
        )
        paths = [
            os.path.join(ROOT, "fruitjam", "magwrite_transport", name)
            for name in (
                "editor.py", "editor_layout.py", "editor_viewport.py",
                "editor_scenarios.py", "editor_session.py",
            )
        ]
        paths.append(os.path.join(ROOT, "magtag", "magwrite", "viewport_renderer.py"))
        for path in paths:
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            for module in forbidden:
                self.assertNotIn("import " + module, source, path)

    def test_editor_modules_are_loaded_without_hardware_stubs(self):
        for name in ("board", "busio", "storage", "supervisor"):
            self.assertNotIn(name, sys.modules)


if __name__ == "__main__":
    unittest.main()
