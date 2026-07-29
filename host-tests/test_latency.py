"""Measured keypress-to-visible latency, as a recorder and in a whole session.

The physical run for this phase has to produce numbers, so the thing that
produces them needs its own coverage. Two properties matter most and are
asserted from both directions:

* the recorder is **passive** — a session with it and a session without it must
  behave identically, or the measurement is measuring itself;
* the anchor is the **first stale-making keypress**, not the newest one, or a
  fast burst would flatter every figure.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from keyboard_simulator import KeyboardLink, finish, type_characters
from magwrite_transport.latency import (
    DISPLAY_CAUGHT_UP, REFRESH_COMPLETED, REFRESH_STARTED, LatencyRecorder,
    Series,
)
from magwrite_transport.pacing import REASON_CAUGHT_UP, REASON_SUSTAINED
from test_pacing import (
    PAUSE_SECONDS, ScheduledKeyboardBackend, deliberate_schedule,
)


class SeriesTest(unittest.TestCase):
    def test_an_empty_series_describes_itself_without_inventing_numbers(self):
        described = Series().describe()
        self.assertEqual(described["count"], 0)
        self.assertIsNone(described["min"])
        self.assertIsNone(described["mean"])
        self.assertIsNone(described["max"])

    def test_a_series_tracks_count_min_mean_and_max(self):
        series = Series()
        for value in (1.0, 3.0, 2.0):
            series.add(value)
        described = series.describe()
        self.assertEqual(described["count"], 3)
        self.assertEqual(described["min"], 1.0)
        self.assertEqual(described["max"], 3.0)
        self.assertEqual(described["mean"], 2.0)

    def test_a_single_sample_is_its_own_minimum_maximum_and_mean(self):
        series = Series()
        series.add(0.5)
        self.assertEqual(series.describe(), {
            "count": 1, "min": 0.5, "mean": 0.5, "max": 0.5,
        })


class LatencyRecorderTest(unittest.TestCase):
    def setUp(self):
        self.recorder = LatencyRecorder()

    def test_latency_is_anchored_to_the_first_stale_making_keypress(self):
        """A later keystroke in the same burst has waited less."""
        self.recorder.note_input(1.0)
        self.recorder.note_input(1.1)
        self.recorder.note_input(1.2)
        self.recorder.note_sent(2.0, revision=5, reason=REASON_SUSTAINED)
        self.assertAlmostEqual(
            self.recorder.to_send.describe()["max"], 1.0
        )

    def test_the_anchor_resets_after_every_send(self):
        self.recorder.note_input(0.0)
        self.recorder.note_sent(1.0, revision=1, reason=REASON_SUSTAINED)
        self.assertIsNone(self.recorder.first_input_since_send)
        self.recorder.note_input(5.0)
        self.recorder.note_sent(5.5, revision=2, reason=REASON_SUSTAINED)
        self.assertAlmostEqual(self.recorder.to_send.describe()["max"], 1.0)
        self.assertAlmostEqual(self.recorder.to_send.describe()["min"], 0.5)

    def test_a_send_with_no_preceding_input_records_no_sample(self):
        """The forced final send may follow no new keystroke at all."""
        self.recorder.note_sent(1.0, revision=1, reason=None)
        self.assertEqual(self.recorder.to_send.count, 0)
        self.assertEqual(self.recorder.sends, 1)

    def test_the_whole_chain_is_measured_from_the_same_anchor(self):
        self.recorder.note_input(0.0)
        self.recorder.note_sent(0.5, revision=7, reason=REASON_SUSTAINED)
        self.recorder.note_status(0.7, REFRESH_STARTED, 7)
        self.recorder.note_status(1.8, REFRESH_COMPLETED, 7)
        self.assertAlmostEqual(self.recorder.to_send.describe()["max"], 0.5)
        self.assertAlmostEqual(
            self.recorder.to_refresh_start.describe()["max"], 0.7
        )
        self.assertAlmostEqual(
            self.recorder.to_refresh_complete.describe()["max"], 1.8
        )

    def test_display_caught_up_also_completes_a_frame(self):
        self.recorder.note_input(0.0)
        self.recorder.note_sent(0.5, revision=3, reason=REASON_SUSTAINED)
        self.recorder.note_status(2.0, DISPLAY_CAUGHT_UP, 3)
        self.assertEqual(self.recorder.to_refresh_complete.count, 1)

    def test_a_status_for_an_unknown_revision_is_ignored(self):
        self.recorder.note_status(1.0, REFRESH_STARTED, 999)
        self.assertEqual(self.recorder.to_refresh_start.count, 0)

    def test_a_completed_frame_is_released_so_tracking_stays_bounded(self):
        self.recorder.note_input(0.0)
        self.recorder.note_sent(0.5, revision=1, reason=REASON_SUSTAINED)
        self.assertIn(1, self.recorder.pending)
        self.recorder.note_status(1.5, REFRESH_COMPLETED, 1)
        self.assertNotIn(1, self.recorder.pending)

    def test_tracking_is_bounded_and_drops_the_oldest_frame(self):
        recorder = LatencyRecorder(capacity=2)
        for revision in (1, 2, 3):
            recorder.note_input(float(revision))
            recorder.note_sent(revision + 0.5, revision, REASON_SUSTAINED)
        self.assertEqual(len(recorder.pending), 2)
        self.assertEqual(recorder.overflowed, 1)
        self.assertNotIn(1, recorder.pending)
        # The dropped frame kept its send timing; only its refresh timing is lost.
        self.assertEqual(recorder.to_send.count, 3)

    def test_a_capacity_below_one_is_refused(self):
        with self.assertRaises(ValueError):
            LatencyRecorder(capacity=0)

    def test_samples_are_split_by_the_regime_that_released_them(self):
        self.recorder.note_input(0.0)
        self.recorder.note_sent(2.6, revision=1, reason=REASON_SUSTAINED)
        self.recorder.note_input(10.0)
        self.recorder.note_sent(11.3, revision=2, reason=REASON_CAUGHT_UP)
        summary = self.recorder.summary()
        self.assertAlmostEqual(
            summary["latency_keypress_to_send_sustained"]["max"], 2.6
        )
        self.assertAlmostEqual(
            summary["latency_keypress_to_send_caught_up"]["max"], 1.3
        )

    def test_a_forced_send_is_reported_under_its_own_name(self):
        self.recorder.note_input(0.0)
        self.recorder.note_sent(1.0, revision=1, reason=None)
        self.assertIn("latency_keypress_to_send_forced", self.recorder.summary())

    def test_pauses_are_counted_only_when_a_keystroke_ends_one(self):
        self.recorder.note_input(0.0, quiet_before=True)
        self.recorder.note_input(0.1, quiet_before=False)
        self.recorder.note_input(0.2, quiet_before=False)
        self.assertEqual(self.recorder.pauses_observed, 1)

    def test_frames_released_by_a_pause_are_counted_separately(self):
        self.recorder.note_frame_after_pause()
        self.recorder.note_frame_after_pause()
        self.assertEqual(
            self.recorder.summary()["latency_frames_after_pause"], 2
        )

    def test_the_summary_reports_every_required_measurement(self):
        for field in (
            "latency_keypress_to_send",
            "latency_keypress_to_refresh_start",
            "latency_keypress_to_refresh_complete",
            "latency_sends",
            "latency_pauses_observed",
            "latency_frames_after_pause",
            "latency_tracking_overflows",
        ):
            self.assertIn(field, self.recorder.summary(), field)

    def test_the_summary_is_json_serializable(self):
        import json
        self.recorder.note_input(0.0)
        self.recorder.note_sent(1.0, revision=1, reason=REASON_SUSTAINED)
        self.recorder.note_status(2.0, REFRESH_COMPLETED, 1)
        json.dumps(self.recorder.summary())


class MeasuredSessionTest(unittest.TestCase):
    """The recorder inside a real session, against the simulated panel."""

    def run_link(self, reports, **options):
        link = KeyboardLink(reports, **options).run()
        link.summary = link.session.summary("PASS")
        return link

    def test_a_sustained_run_measures_the_whole_chain(self):
        reports = type_characters("measured sustained typing") + finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        summary = link.summary
        self.assertGreater(summary["latency_keypress_to_send"]["count"], 0)
        self.assertGreater(
            summary["latency_keypress_to_refresh_start"]["count"], 0
        )
        self.assertGreater(
            summary["latency_keypress_to_refresh_complete"]["count"], 0
        )

    def test_the_chain_is_monotonic_on_average(self):
        """Send, then start, then complete: each strictly adds time."""
        reports = type_characters("monotonic chain check") + finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        summary = link.summary
        self.assertLess(
            summary["latency_keypress_to_send"]["mean"],
            summary["latency_keypress_to_refresh_start"]["mean"],
        )
        self.assertLess(
            summary["latency_keypress_to_refresh_start"]["mean"],
            summary["latency_keypress_to_refresh_complete"]["mean"],
        )

    def test_a_paused_run_measures_the_catch_up_path_separately(self):
        backend = ScheduledKeyboardBackend(
            deliberate_schedule(
                type_characters("ab cd") + finish(), gap=PAUSE_SECONDS
            ),
            clock=None,
        )
        link = KeyboardLink(backend=backend)
        backend.clock = link.clock
        link.run()
        summary = link.session.summary("PASS")
        self.assertGreater(summary["latency_pauses_observed"], 0)
        self.assertGreater(summary["latency_frames_after_pause"], 0)
        self.assertIn("latency_keypress_to_send_caught_up", summary)

    def test_catching_up_is_measurably_faster_than_typing_through(self):
        """The claim this phase exists to make, measured rather than asserted."""
        from magwrite_transport import pacing
        backend = ScheduledKeyboardBackend(
            deliberate_schedule(
                type_characters("ab cd ef") + finish(), gap=PAUSE_SECONDS
            ),
            clock=None,
        )
        link = KeyboardLink(backend=backend)
        backend.clock = link.clock
        link.run()
        summary = link.session.summary("PASS")
        caught_up = summary["latency_keypress_to_send_caught_up"]
        self.assertGreater(caught_up["count"], 0)
        self.assertLess(caught_up["max"], pacing.SUSTAINED_MIN_SEND_SECONDS)

    def test_measurement_never_changes_what_the_session_does(self):
        """Passive means passive: identical results with a throwaway recorder."""
        reports = type_characters("passivity check") + finish()
        first = self.run_link(reports, typing_interval_seconds=0.1)
        second = KeyboardLink(
            type_characters("passivity check") + finish(),
            typing_interval_seconds=0.1,
            latency=LatencyRecorder(capacity=1),
        ).run()
        second_summary = second.session.summary("PASS")
        for field in (
            "events_processed", "viewport_frames_sent", "viewports_built",
            "final_displayed_revision", "final_hash", "test_complete",
            "pacing_onset_sends", "pacing_caught_up_sends",
            "pacing_sustained_sends", "pacing_forced_sends",
        ):
            self.assertEqual(
                first.summary[field], second_summary[field], field
            )
        self.assertEqual(
            first.session.editor.text, second.session.editor.text
        )

    def test_tracking_never_overflows_inside_the_authorised_ceiling(self):
        from magwrite_transport.live_session import MAX_VIEWPORT_FRAMES
        from magwrite_transport.latency import TRACKING_CAPACITY
        self.assertGreaterEqual(TRACKING_CAPACITY, MAX_VIEWPORT_FRAMES)
        reports = type_characters("no overflow inside the ceiling") + finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        self.assertEqual(link.summary["latency_tracking_overflows"], 0)

    def test_the_measured_send_latency_respects_the_documented_bound(self):
        from keyboard_simulator import FULL_REFRESH_SECONDS, PARTIAL_REFRESH_SECONDS
        from magwrite_transport import pacing
        reports = type_characters("bounded measured latency") + finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        self.assertLessEqual(
            link.summary["latency_keypress_to_send"]["max"],
            pacing.maximum_pending_seconds(
                max(FULL_REFRESH_SECONDS, PARTIAL_REFRESH_SECONDS)
            ),
        )


if __name__ == "__main__":
    unittest.main()
