"""Integrated live-typing session behaviour on the host.

One shared deterministic run drives the real HID translation, adapter, editor,
layout, viewport, transport, and acknowledgement code, so the physical run only
has to confirm the panel and the real keyboard.

The scripted report stream mirrors the six physical scenarios: basic typing,
punctuation with Shift, a correction, multiline editing, typing while the display
is busy, and a final realistic note.
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from keyboard_simulator import (
    FakeKeyboardBackend, KeyboardLink, finish, press_kind, press_release,
    report, type_characters,
)
from magwrite.test_pattern import GLYPHS
from magwrite_transport.hid_keymap import USAGE_ESCAPE
from magwrite_transport.live_session import (
    LIVE_SCENARIO_ID, MAX_KEYBOARD_EVENTS, MAX_PARTIAL_REFRESHES,
    MAX_PROTOCOL_FRAMES, MAX_VIEWPORT_FRAMES, LiveSessionError,
    LiveTypingSession,
)
from magwrite_transport.usb_hid_descriptors import UsbKeyboardNotFound

PHYSICAL_EVENT_CEILING = 500
PHYSICAL_VIEWPORT_CEILING = 100
PHYSICAL_FRAME_CEILING = 200
PHYSICAL_PARTIAL_REFRESH_CEILING = 50

SCENARIO_1 = "MAGWRITE USB KEYBOARD TEST"
SCENARIO_2 = "Hello, MagWrite! It's working."
SCENARIO_4 = "line one\nline two\nline three"
SCENARIO_6 = "A real note, typed by hand."


def correction_reports():
    """Type ``JORUNAL``, then repair it to ``JOURNAL`` with real keys.

    Home, then Right x18 to the transposed ``R``, Delete it, Right past the
    ``U``, retype ``R``, then End.
    """
    reports = type_characters("TODAY I WROTE A JORUNAL ENTRY")
    reports += press_kind("HOME")
    reports += press_kind("RIGHT", 18)
    reports += press_kind("DELETE")
    reports += press_kind("RIGHT")
    reports += type_characters("R")
    reports += press_kind("END")
    return reports


def multiline_reports():
    reports = type_characters(SCENARIO_4)
    reports += press_kind("UP", 2)
    reports += press_kind("HOME")
    reports += press_kind("DOWN")
    reports += press_kind("END")
    reports += press_kind("LEFT", 2)
    reports += press_kind("RIGHT")
    reports += press_kind("DOWN")
    reports += press_kind("END")
    return reports


def full_script():
    reports = type_characters(SCENARIO_1)
    reports += press_kind("ENTER")
    reports += type_characters(SCENARIO_2)
    reports += press_kind("ENTER")
    reports += correction_reports()
    reports += press_kind("ENTER")
    reports += multiline_reports()
    reports += press_kind("ENTER")
    reports += type_characters(SCENARIO_6)
    reports += finish()
    return reports


class LiveRunTest(unittest.TestCase):
    """One shared deterministic run; every assertion reads from it."""

    @classmethod
    def setUpClass(cls):
        cls.link = KeyboardLink(full_script()).run()
        cls.summary = cls.link.session.summary("PASS")
        cls.records = cls.link.records

    def events(self, name):
        return [r for r in self.records if r.get("event") == name]

    # ---------------------------------------------------------------- input

    def test_the_run_completes_and_the_keyboard_drove_every_event(self):
        self.assertTrue(self.link.session.complete)
        self.assertGreater(self.summary["normalized_events"], 100)
        self.assertEqual(
            self.summary["events_processed"], self.summary["normalized_events"]
        )

    def test_every_event_is_processed_exactly_once_and_in_order(self):
        processed = self.events("live_event_processed")
        self.assertEqual(
            [r["sequence"] for r in processed],
            list(range(self.summary["events_processed"])),
        )

    def test_no_event_is_rejected_duplicated_or_dropped(self):
        self.assertEqual(self.summary["events_rejected"], 0)
        self.assertEqual(self.summary["queue_overflows"], 0)
        self.assertEqual(self.events("live_event_rejected"), [])

    def test_no_duplicate_report_ever_became_an_event(self):
        normalized = self.events("keyboard_event_normalized")
        self.assertEqual(len(normalized), self.summary["normalized_events"])
        self.assertEqual(
            len(set(r["sequence"] for r in normalized)), len(normalized)
        )

    def test_queue_depth_stays_inside_its_bound(self):
        self.assertGreaterEqual(self.summary["maximum_queue_depth"], 1)
        self.assertLess(
            self.summary["maximum_queue_depth"], self.summary["queue_capacity"]
        )

    def test_input_is_drained_before_any_viewport_is_generated(self):
        """No viewport may be sent before the input it depicts was applied."""
        latest = -1
        for record in self.records:
            if record.get("event") == "live_event_processed":
                latest = record["sequence"]
            elif record.get("event") == "live_viewport_sent":
                self.assertGreaterEqual(latest, 0)
        self.assertEqual(latest, self.summary["events_processed"] - 1)

    def test_a_report_is_always_normalized_before_it_is_applied(self):
        order = [
            record["event"] for record in self.records
            if record.get("event") in
            ("keyboard_event_normalized", "live_event_processed")
        ]
        # The first thing that ever happens to an event is normalization.
        self.assertEqual(order[0], "keyboard_event_normalized")

    # ------------------------------------------------------------- scenarios

    def test_scenario_one_basic_typing_is_exact(self):
        self.assertEqual(self.link.session.editor.lines[0], SCENARIO_1)

    def test_scenario_two_punctuation_and_shift_are_exact(self):
        self.assertEqual(self.link.session.editor.lines[1], SCENARIO_2)

    def test_scenario_three_correction_repairs_the_transposition(self):
        line = self.link.session.editor.lines[2]
        self.assertEqual(line, "TODAY I WROTE A JOURNAL ENTRY")
        self.assertNotIn("JORUNAL", line)

    def test_scenario_four_multiline_editing_produces_three_lines(self):
        self.assertEqual(
            self.link.session.editor.lines[3:6],
            ["line one", "line two", "line three"],
        )

    def test_scenario_six_final_note_is_exact(self):
        self.assertEqual(self.link.session.editor.lines[-1], SCENARIO_6)

    def test_the_final_document_is_renderable_by_the_proven_glyph_table(self):
        for character in self.link.session.editor.text:
            if character != "\n":
                self.assertIn(character, GLYPHS, repr(character))

    def test_both_cases_and_the_required_punctuation_were_exercised(self):
        text = self.link.session.editor.text
        self.assertTrue(any(c.islower() for c in text))
        self.assertTrue(any(c.isupper() for c in text))
        for character in ",!'.":
            self.assertIn(character, text)

    # ------------------------------------------------------------ coalescing

    def test_viewport_count_is_far_below_the_event_count(self):
        self.assertLess(
            self.summary["viewport_frames_sent"],
            self.summary["events_processed"] // 4,
        )

    def test_stale_viewport_states_are_coalesced_before_transmission(self):
        self.assertGreater(self.summary["viewports_superseded_locally"], 0)
        self.assertGreater(
            self.summary["viewports_built"], self.summary["viewport_frames_sent"]
        )
        self.assertTrue(self.events("live_viewport_superseded"))

    def test_typing_continues_while_the_display_is_busy(self):
        """Events must be processed during an in-flight refresh."""
        started = [
            r for r in self.records
            if r.get("event") == "live_status_received"
            and r.get("message_type") == 7
        ]
        self.assertTrue(started)
        # Between the first REFRESH_STARTED and the last REFRESH_COMPLETED,
        # input kept being applied.
        first = self.records.index(started[0])
        applied_after = [
            r for r in self.records[first:]
            if r.get("event") == "live_event_processed"
        ]
        self.assertGreater(len(applied_after), 10)

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

    def test_the_final_display_catches_up(self):
        self.assertGreater(self.summary["display_caught_up_received"], 0)
        self.assertTrue(self.events("live_test_complete"))

    def test_no_transport_integrity_failure_occurs(self):
        for field in (
            "crc_failures", "status_frames_rejected", "status_sequence_gaps",
            "status_duplicates", "status_stale", "timeouts",
            "resynchronization_events", "discarded_prefix_bytes",
        ):
            self.assertEqual(self.summary[field], 0, field)
        self.assertIsNone(self.summary["stop_reason"])

    def test_the_viewport_uses_its_own_scenario_id(self):
        self.assertEqual(LIVE_SCENARIO_ID, 6)

    # ------------------------------------------------------- physical limits

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
        self.assertLessEqual(self.link.status_frames_sent, PHYSICAL_FRAME_CEILING)
        partials = [
            item for item in self.link.scheduler.completions if not item[2]
        ]
        self.assertLessEqual(len(partials), PHYSICAL_PARTIAL_REFRESH_CEILING)

    def test_harness_ceilings_match_the_authorised_limits(self):
        self.assertEqual(MAX_KEYBOARD_EVENTS, PHYSICAL_EVENT_CEILING)
        self.assertEqual(MAX_VIEWPORT_FRAMES, PHYSICAL_VIEWPORT_CEILING)
        self.assertEqual(MAX_PROTOCOL_FRAMES, PHYSICAL_FRAME_CEILING)
        self.assertEqual(MAX_PARTIAL_REFRESHES, PHYSICAL_PARTIAL_REFRESH_CEILING)

    # ---------------------------------------------------------- diagnostics

    def test_required_diagnostic_records_are_emitted(self):
        for name in (
            "usb_keyboard_connected", "hid_report_received",
            "keyboard_event_normalized", "keyboard_repeat_started",
            "live_event_processed", "live_document_revision_changed",
            "live_viewport_sent", "live_viewport_superseded",
            "live_status_received", "live_typing_started",
            "live_typing_finished", "live_test_complete",
        ):
            self.assertTrue(self.events(name), name)

    def test_diagnostic_records_are_json_serializable(self):
        for record in self.records:
            json.loads(json.dumps(record))

    def test_the_summary_reports_every_required_field(self):
        for field in (
            "result", "reports_received", "normalized_events",
            "duplicate_reports", "repeat_events", "unsupported_usages",
            "queue_overflows", "viewport_frames_sent",
            "final_transmitted_revision", "final_displayed_revision",
            "final_hash", "crc_failures", "timeouts", "final_document_text",
            "usb_descriptor",
        ):
            self.assertIn(field, self.summary)
        json.loads(json.dumps(self.summary))

    def test_the_run_is_reproducible(self):
        repeat = KeyboardLink(full_script()).run().session.summary("PASS")
        self.assertEqual(repeat["final_hash"], self.summary["final_hash"])
        self.assertEqual(
            repeat["final_displayed_revision"],
            self.summary["final_displayed_revision"],
        )
        self.assertEqual(
            repeat["viewport_frames_sent"], self.summary["viewport_frames_sent"]
        )
        self.assertEqual(
            repeat["final_document_text"], self.summary["final_document_text"]
        )


class HumanPacedRunTest(unittest.TestCase):
    """The same script released at roughly 60 WPM.

    The unpaced run above delivers the whole script faster than one physical
    refresh, so it proves ordering but predicts almost no frames. This run is the
    one whose frame and refresh counts are comparable to a physical session.
    """

    @classmethod
    def setUpClass(cls):
        cls.link = KeyboardLink(
            full_script(),
            typing_interval_seconds=KeyboardLink.HUMAN_REPORT_INTERVAL_SECONDS,
        ).run()
        cls.summary = cls.link.session.summary("PASS")

    def test_the_document_is_identical_to_the_unpaced_run(self):
        self.assertEqual(
            self.summary["final_document_text"],
            "\n".join([
                SCENARIO_1, SCENARIO_2, "TODAY I WROTE A JOURNAL ENTRY",
                "line one", "line two", "line three", SCENARIO_6,
            ]),
        )

    def test_no_keypress_is_lost_or_duplicated_at_human_pace(self):
        self.assertEqual(
            self.summary["events_processed"], self.summary["normalized_events"]
        )
        self.assertEqual(self.summary["events_rejected"], 0)
        self.assertEqual(self.summary["queue_overflows"], 0)

    def test_many_refreshes_happen_while_typing_continues(self):
        self.assertGreater(self.link.scheduler.refresh_count, 5)
        self.assertLess(
            self.link.scheduler.refresh_count, self.summary["events_processed"]
        )

    def test_stale_states_are_still_coalesced_at_human_pace(self):
        self.assertGreater(self.summary["viewports_superseded_locally"], 0)
        self.assertLess(
            self.summary["viewport_frames_sent"],
            self.summary["events_processed"] // 2,
        )

    def test_the_document_scrolls_past_the_five_row_window(self):
        editor = self.link.session.editor
        self.assertGreater(len(editor.visual_rows()), editor.layout.height)
        window = editor.layout.window(editor.lines, editor.row, editor.column)
        self.assertTrue(window["more_above"])

    def test_the_final_revision_and_hash_still_reconcile(self):
        self.assertEqual(
            self.summary["final_displayed_revision"],
            self.summary["final_transmitted_revision"],
        )
        self.assertTrue(self.summary["test_complete"])
        self.assertEqual(
            int(self.summary["final_hash"], 16), self.link.scheduler.latest_hash
        )

    def test_the_paced_run_stays_inside_every_authorised_limit(self):
        self.assertLessEqual(
            self.summary["events_processed"], PHYSICAL_EVENT_CEILING
        )
        self.assertLessEqual(
            self.summary["viewport_frames_sent"], PHYSICAL_VIEWPORT_CEILING
        )
        self.assertLessEqual(
            self.summary["input_frames_sent"], PHYSICAL_FRAME_CEILING
        )
        self.assertLessEqual(self.link.status_frames_sent, PHYSICAL_FRAME_CEILING)
        partials = [i for i in self.link.scheduler.completions if not i[2]]
        self.assertLessEqual(len(partials), PHYSICAL_PARTIAL_REFRESH_CEILING)

    def test_exactly_one_full_refresh_still_seeds_the_panel(self):
        fulls = [i for i in self.link.scheduler.completions if i[2]]
        self.assertEqual(len(fulls), 1)

    def test_the_paced_run_is_reproducible(self):
        repeat = KeyboardLink(
            full_script(),
            typing_interval_seconds=KeyboardLink.HUMAN_REPORT_INTERVAL_SECONDS,
        ).run().session.summary("PASS")
        self.assertEqual(repeat["final_hash"], self.summary["final_hash"])
        self.assertEqual(
            repeat["viewport_frames_sent"], self.summary["viewport_frames_sent"]
        )


class LiveStopConditionTest(unittest.TestCase):
    def test_a_queue_overflow_stops_the_session(self):
        """A burst faster than the editor can drain must fail loudly."""
        link = KeyboardLink(
            backend=FakeKeyboardBackend(
                type_characters("A" * 40), reports_per_poll=64
            ),
            adapter_options={"poll_budget": 64},
            queue_capacity=2,
        )
        with self.assertRaises(LiveSessionError) as caught:
            link.run(maximum_iterations=40000)
        self.assertIn("overflow", str(caught.exception))

    def test_a_rejected_edit_stops_the_session(self):
        link = KeyboardLink(type_characters("ABCDEFGH"))
        link.session.editor.max_line_chars = 2
        with self.assertRaises(LiveSessionError):
            link.run(maximum_iterations=40000)

    def test_a_corrupt_status_byte_stream_stops_the_session(self):
        from magwrite_transport.protocol import encode_frame
        link = KeyboardLink(type_characters("ABC"))
        for _ in range(200):
            link.step()
        good = encode_frame(6, 1, 1, b"")
        link.session.feed(good[:-4] + b"\x00\x00\x00\x00")
        with self.assertRaises(LiveSessionError):
            for _ in range(50):
                link.session.service()

    def test_the_session_times_out_when_the_panel_never_answers(self):
        link = KeyboardLink(type_characters("ABC"))
        link.scheduler.service = lambda chunks=(): None
        with self.assertRaises(Exception):
            link.run(maximum_iterations=200000)

    def test_a_silent_keyboard_eventually_times_out_the_idle_bound(self):
        link = KeyboardLink(type_characters("A"), idle_timeout_seconds=5.0)
        with self.assertRaises(LiveSessionError) as caught:
            link.run(maximum_iterations=200000)
        self.assertIn("idle", str(caught.exception))

    def test_the_absolute_session_bound_is_enforced(self):
        link = KeyboardLink(
            type_characters("A"), idle_timeout_seconds=100000.0,
            session_timeout_seconds=4.0,
        )
        with self.assertRaises(LiveSessionError) as caught:
            link.run(maximum_iterations=200000)
        self.assertIn("session timeout", str(caught.exception))

    def test_the_viewport_frame_ceiling_stops_the_session(self):
        """The 100-frame ceiling refuses the next send rather than exceeding it."""
        link = KeyboardLink(type_characters("ABC"))
        for _ in range(400):
            link.step()
        self.assertGreater(link.session.viewport_frames_sent, 0)
        link.session.viewport_frames_sent = MAX_VIEWPORT_FRAMES
        link.session.last_sent_payload = None
        link.session.send_window = 999
        with self.assertRaises(LiveSessionError) as caught:
            link.session._maybe_send_viewport(link.clock.now, force=True)
        self.assertIn("viewport frame limit exceeded", str(caught.exception))

    def test_the_protocol_frame_ceiling_stops_the_session(self):
        link = KeyboardLink(type_characters("ABC"))
        for _ in range(400):
            link.step()
        link.session.frame_sequence = MAX_PROTOCOL_FRAMES
        with self.assertRaises(LiveSessionError) as caught:
            link.session._emit(2, 1, b"x")
        self.assertIn("input frame limit exceeded", str(caught.exception))

    def test_a_keyboard_that_never_appears_does_not_spin_forever(self):
        """Bounded retries, then a latched ERROR rather than a hot loop."""
        link = KeyboardLink(
            backend=FakeKeyboardBackend(open_error=UsbKeyboardNotFound("none")),
            idle_timeout_seconds=8.0,
        )
        with self.assertRaises(Exception):
            link.run(maximum_iterations=200000)
        self.assertLessEqual(
            link.backend.opens, link.session.adapter.state.max_attempts
        )


class LiveFinishTest(unittest.TestCase):
    def test_escape_ends_the_run_and_nothing_after_it_is_typed(self):
        link = KeyboardLink(
            type_characters("AB") + finish() + type_characters("CD")
        ).run()
        self.assertEqual(link.session.editor.text, "AB")
        self.assertTrue(link.session.adapter.finish_requested)

    def test_the_run_does_not_finish_until_the_queue_is_drained(self):
        link = KeyboardLink(type_characters("HELLO") + finish()).run()
        self.assertEqual(link.session.editor.text, "HELLO")
        self.assertEqual(len(link.session.queue), 0)
        self.assertEqual(link.session.events_processed, 5)

    def test_finishing_without_typing_anything_stops_explicitly(self):
        """There is no final viewport to reconcile, so it must not hang."""
        link = KeyboardLink(finish())
        with self.assertRaises(LiveSessionError) as caught:
            link.run(maximum_iterations=200000)
        self.assertIn("empty document", str(caught.exception))

    def test_the_final_state_is_the_one_that_is_displayed(self):
        link = KeyboardLink(type_characters("FINAL") + finish()).run()
        summary = link.session.summary("PASS")
        self.assertEqual(
            summary["final_displayed_revision"],
            link.session.editor.viewport_revision,
        )
        self.assertEqual(summary["final_document_text"], "FINAL")


class LiveConstructionTest(unittest.TestCase):
    def test_an_adapter_may_be_supplied_directly(self):
        from magwrite_transport.editor import BoundedEventQueue
        from magwrite_transport.usb_keyboard_adapter import UsbKeyboardAdapter
        queue = BoundedEventQueue(8)
        adapter = UsbKeyboardAdapter(
            FakeKeyboardBackend(()), queue, lambda r: None
        )
        session = LiveTypingSession(lambda: 0.0, lambda r: None, adapter=adapter)
        self.assertIs(session.adapter, adapter)

    def test_the_session_never_reuses_the_scenario_driven_session(self):
        """The proven scripted session must stay untouched by this phase."""
        from magwrite_transport import editor_session
        self.assertFalse(hasattr(editor_session, "LiveTypingSession"))
        self.assertNotIn("usb", editor_session.__doc__.lower())


if __name__ == "__main__":
    unittest.main()
