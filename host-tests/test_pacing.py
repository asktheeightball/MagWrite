"""Adaptive display pacing, as a policy and as integrated behaviour.

Two layers, deliberately separate:

* :class:`DisplayPacer` is driven directly with an ordinary float clock, so
  every branch of the policy is reachable and every constant is asserted
  against the panel measurement that justifies it;
* whole live sessions are then run through the real editor, viewport,
  transport, acknowledgement and simulated-panel code under four input shapes —
  isolated keystrokes, a burst, sustained typing, and typing while the display
  is busy — so the policy is proved in place rather than in isolation.

Nothing here models physical e-paper. It proves the scheduler behaves, and the
physical run remains the only thing that can prove panel latency.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from keyboard_simulator import (
    FULL_REFRESH_SECONDS, PARTIAL_REFRESH_SECONDS, KeyboardLink, finish,
    press_kind, type_characters,
)
from magwrite_transport import pacing
from magwrite_transport.pacing import (
    REASON_BUSY, REASON_CAUGHT_UP, REASON_COALESCING, REASON_NOTHING_PENDING,
    REASON_ONSET, REASON_SUSTAINED, REASON_WAITING, DisplayPacer,
)

LONGEST_SIMULATED_REFRESH = max(FULL_REFRESH_SECONDS, PARTIAL_REFRESH_SECONDS)

# Long enough to be unambiguously a pause, short enough to keep runs quick.
PAUSE_SECONDS = 2.0
# A real keystroke is held for a few tens of milliseconds, far below the repeat
# delay. Holding one for the whole gap would be testing key repeat instead.
HOLD_SECONDS = 0.05


class ScheduledKeyboardBackend:
    """Delivers scripted reports at exact simulated times.

    ``FakeKeyboardBackend`` paces every report by one uniform interval, which
    cannot express "type a character, then wait" — the gap would land between
    press and release and the key would repeat. This backend times each report
    individually, so a pause is a pause and not a held key.
    """

    def __init__(self, schedule, clock, descriptor=None):
        self.schedule = list(schedule)
        self.clock = clock
        self.descriptor = descriptor if descriptor is not None else {
            "vendor_id": "36B0", "product_id": "3002", "interface": 0,
            "endpoint": 0x81, "protocol": "boot_keyboard",
        }
        self.opens = 0
        self.closes = 0
        self.delivered = 0

    def open(self):
        self.opens += 1
        return self.descriptor

    def close(self):
        self.closes += 1

    def read_report(self):
        if not self.schedule:
            return None
        when, raw = self.schedule[0]
        if self.clock() < when:
            return None
        self.schedule.pop(0)
        self.delivered += 1
        return raw


def deliberate_schedule(reports, gap=PAUSE_SECONDS, hold=HOLD_SECONDS):
    """Time a press/release report stream as slow, deliberate keystrokes."""
    schedule = []
    now = 0.0
    for index, raw in enumerate(reports):
        schedule.append((now, raw))
        # Reports come in press/release pairs; hold briefly, then pause.
        now += hold if index % 2 == 0 else gap
    return schedule


class PacingConstantTest(unittest.TestCase):
    """Every constant must be justified by a measured panel number."""

    def test_the_measured_panel_numbers_are_internally_consistent(self):
        self.assertLess(
            pacing.MEASURED_PARTIAL_REFRESH_FASTEST_SECONDS,
            pacing.MEASURED_PARTIAL_REFRESH_MEAN_SECONDS,
        )
        self.assertLess(
            pacing.MEASURED_PARTIAL_REFRESH_MEAN_SECONDS,
            pacing.MEASURED_PARTIAL_REFRESH_SLOWEST_SECONDS,
        )
        self.assertGreater(
            pacing.MEASURED_FULL_REFRESH_SECONDS,
            pacing.MEASURED_PARTIAL_REFRESH_SLOWEST_SECONDS,
        )

    def test_the_catch_up_floor_is_at_least_one_slowest_partial_refresh(self):
        self.assertGreaterEqual(
            pacing.CAUGHT_UP_MIN_SEND_SECONDS,
            pacing.MEASURED_PARTIAL_REFRESH_SLOWEST_SECONDS,
        )

    def test_coalescing_always_spans_several_keystrokes(self):
        """At 60 WPM a keystroke lands every 100 ms."""
        self.assertGreaterEqual(pacing.COALESCE_SECONDS, 0.2)
        # But it must stay imperceptible at the start of a burst.
        self.assertLess(pacing.COALESCE_SECONDS, 0.5)

    def test_quiet_is_longer_than_a_hesitation_and_shorter_than_a_pause(self):
        self.assertGreater(pacing.QUIET_SECONDS, pacing.COALESCE_SECONDS)
        self.assertLess(pacing.QUIET_SECONDS, pacing.CAUGHT_UP_MIN_SEND_SECONDS)

    def test_catching_up_is_strictly_faster_than_typing_through(self):
        self.assertLess(
            pacing.CAUGHT_UP_MIN_SEND_SECONDS,
            pacing.SUSTAINED_MIN_SEND_SECONDS,
        )

    def test_only_one_viewport_is_ever_in_flight(self):
        self.assertEqual(pacing.SEND_WINDOW, 1)

    def test_the_maximum_pending_bound_accounts_for_an_in_flight_refresh(self):
        """A long full refresh, not the floor, is the real worst case."""
        bound = pacing.maximum_pending_seconds(
            pacing.MEASURED_FULL_REFRESH_SECONDS
        )
        self.assertGreater(bound, pacing.MEASURED_FULL_REFRESH_SECONDS)
        self.assertGreater(bound, pacing.SUSTAINED_MIN_SEND_SECONDS)

    def test_a_pacer_refuses_an_incoherent_configuration(self):
        with self.assertRaises(ValueError):
            DisplayPacer(quiet_seconds=0)
        with self.assertRaises(ValueError):
            DisplayPacer(sustained_min_send_seconds=0)
        with self.assertRaises(ValueError):
            DisplayPacer(
                caught_up_min_send_seconds=5.0, sustained_min_send_seconds=1.0
            )


class PacingPolicyTest(unittest.TestCase):
    """The decision function, driven directly."""

    def setUp(self):
        self.pacer = DisplayPacer()

    def test_nothing_pending_never_sends(self):
        self.assertEqual(
            self.pacer.decide(100.0, busy=False), REASON_NOTHING_PENDING
        )
        self.assertFalse(self.pacer.due(100.0, busy=False))

    def test_a_busy_panel_blocks_every_send_including_an_overdue_one(self):
        self.pacer.note_pending(0.0)
        self.assertEqual(self.pacer.decide(1000.0, busy=True), REASON_BUSY)
        self.assertFalse(self.pacer.due(1000.0, busy=True))

    def test_a_single_keypress_never_earns_its_own_frame(self):
        self.pacer.note_input(0.0)
        self.pacer.note_pending(0.0)
        inside = pacing.COALESCE_SECONDS / 2.0
        self.assertEqual(self.pacer.decide(inside, busy=False), REASON_COALESCING)
        self.assertFalse(self.pacer.due(inside, busy=False))

    def test_the_first_viewport_goes_out_one_coalescing_window_after_onset(self):
        self.pacer.note_input(0.0)
        self.pacer.note_pending(0.0)
        self.assertEqual(
            self.pacer.decide(pacing.COALESCE_SECONDS, busy=False), REASON_ONSET
        )

    def test_onset_does_not_wait_for_a_sustained_interval(self):
        """The defect the fixed 2.6 s policy had at the start of a session."""
        self.pacer.note_input(0.0)
        self.pacer.note_pending(0.0)
        self.assertTrue(
            self.pacer.due(pacing.COALESCE_SECONDS, busy=False)
        )
        self.assertLess(
            pacing.COALESCE_SECONDS, pacing.SUSTAINED_MIN_SEND_SECONDS
        )

    def test_sustained_typing_waits_the_sustained_floor(self):
        self.pacer.note_sent(0.0, REASON_ONSET)
        # Still typing throughout.
        for moment in (0.5, 1.0, 1.5, 2.0, 2.5):
            self.pacer.note_input(moment)
        self.pacer.note_pending(0.5)
        self.assertEqual(self.pacer.decide(2.5, busy=False), REASON_WAITING)
        self.pacer.note_input(2.55)
        self.assertEqual(
            self.pacer.decide(pacing.SUSTAINED_MIN_SEND_SECONDS, busy=False),
            REASON_SUSTAINED,
        )

    def test_typing_keeps_advancing_during_a_long_burst(self):
        """A sustained burst must not stall the display until it ends."""
        pacer = DisplayPacer()
        now = 0.0
        sends = []
        pacer.note_pending(now)
        for _ in range(4000):          # 40 s of continuous typing at 100 ms
            now += 0.01
            pacer.note_input(now)
            pacer.note_pending(now)
            if pacer.due(now, busy=False):
                reason = pacer.decide(now, busy=False)
                pacer.note_sent(now, reason)
                sends.append((now, reason))
                pacer.note_pending(now + 0.01)
        self.assertGreater(len(sends), 10)
        self.assertEqual(sends[0][1], REASON_ONSET)
        # Every later send is the sustained path, evenly spaced at the floor.
        for (earlier, _), (later, reason) in zip(sends[1:], sends[2:]):
            self.assertEqual(reason, REASON_SUSTAINED)
            # One loop step of slack: the gate is checked on a 10 ms cadence.
            self.assertAlmostEqual(
                later - earlier, pacing.SUSTAINED_MIN_SEND_SECONDS, delta=0.02
            )

    def test_a_pause_catches_up_without_waiting_out_the_sustained_floor(self):
        pacer = DisplayPacer()
        pacer.note_input(0.0)
        pacer.note_sent(0.0, REASON_ONSET)
        pacer.note_input(0.1)
        pacer.note_pending(0.1)
        # The writer stops. Quiet elapses, then the catch-up floor.
        quiet_at = 0.1 + pacing.QUIET_SECONDS
        self.assertTrue(pacer.quiet(quiet_at))
        due_at = pacing.CAUGHT_UP_MIN_SEND_SECONDS
        self.assertEqual(pacer.decide(due_at, busy=False), REASON_CAUGHT_UP)
        # Strictly sooner than the fixed policy would have allowed.
        self.assertLess(due_at, pacing.SUSTAINED_MIN_SEND_SECONDS)

    def test_a_pause_costs_at_most_one_frame(self):
        """After catching up there is nothing pending until typing resumes."""
        pacer = DisplayPacer()
        pacer.note_input(0.0)
        pacer.note_pending(0.0)
        now = pacing.CAUGHT_UP_MIN_SEND_SECONDS
        pacer.note_sent(now, REASON_CAUGHT_UP)
        pacer.clear_pending()
        for step in range(200):        # 20 s of silence
            now += 0.1
            self.assertEqual(
                pacer.decide(now, busy=False), REASON_NOTHING_PENDING
            )

    def test_the_newest_pending_state_goes_out_the_moment_the_panel_frees(self):
        pacer = DisplayPacer()
        pacer.note_input(0.0)
        pacer.note_sent(0.0, REASON_ONSET)
        pacer.note_input(0.1)
        pacer.note_pending(0.1)
        # Overdue on every count, but the panel is still refreshing.
        self.assertEqual(pacer.decide(9.0, busy=True), REASON_BUSY)
        # It comes free; the very next decision sends.
        self.assertTrue(pacer.due(9.0, busy=False))

    def test_pending_time_is_measured_from_when_the_display_fell_behind(self):
        """Not from the newest keystroke, or lag would slide forever."""
        pacer = DisplayPacer()
        pacer.note_pending(1.0)
        pacer.note_pending(2.0)
        pacer.note_pending(3.0)
        self.assertEqual(pacer.pending_since, 1.0)
        pacer.note_sent(4.0, REASON_SUSTAINED)
        self.assertAlmostEqual(pacer.maximum_pending_seconds, 3.0)

    def test_the_summary_counts_each_regime_separately(self):
        pacer = DisplayPacer()
        pacer.note_sent(0.0, REASON_ONSET)
        pacer.note_sent(1.0, REASON_SUSTAINED)
        pacer.note_sent(2.0, REASON_CAUGHT_UP)
        pacer.note_sent(3.0, None)
        summary = pacer.summary()
        self.assertEqual(summary["pacing_onset_sends"], 1)
        self.assertEqual(summary["pacing_sustained_sends"], 1)
        self.assertEqual(summary["pacing_caught_up_sends"], 1)
        self.assertEqual(summary["pacing_forced_sends"], 1)


class PacedSessionTest(unittest.TestCase):
    """Whole sessions under four input shapes, through the real code."""

    def run_link(self, reports, **options):
        link = KeyboardLink(reports, **options).run()
        link.summary = link.session.summary("PASS")
        return link

    def assert_no_input_lost_or_duplicated(self, link):
        summary = link.summary
        self.assertEqual(
            summary["events_processed"], summary["normalized_events"]
        )
        self.assertEqual(summary["events_rejected"], 0)
        self.assertEqual(summary["queue_overflows"], 0)
        sequences = [
            record["sequence"] for record in link.events("live_event_processed")
        ]
        self.assertEqual(sequences, list(range(len(sequences))))

    def assert_display_reconciles(self, link):
        summary = link.summary
        self.assertTrue(summary["test_complete"])
        self.assertEqual(
            summary["final_displayed_revision"],
            summary["final_transmitted_revision"],
        )
        self.assertEqual(
            summary["final_displayed_revision"],
            summary["final_viewport_revision"],
        )

    # ------------------------------------------------------------- input shapes

    def run_deliberate(self, reports, gap=PAUSE_SECONDS):
        backend = ScheduledKeyboardBackend(
            deliberate_schedule(reports, gap=gap), clock=None
        )
        link = KeyboardLink(backend=backend)
        backend.clock = link.clock      # the link owns the simulated clock
        link.run()
        link.summary = link.session.summary("PASS")
        return link

    def test_isolated_keystrokes_each_become_visible_without_a_long_wait(self):
        """Slow deliberate typing: every gap is a pause the catch-up path owns."""
        reports = type_characters("one two") + finish()
        link = self.run_deliberate(reports)
        self.assert_no_input_lost_or_duplicated(link)
        self.assert_display_reconciles(link)
        self.assertEqual(link.session.editor.text, "one two")
        # A pause after every keystroke: catching up is the dominant regime.
        self.assertGreater(link.summary["pacing_caught_up_sends"], 0)
        self.assertGreaterEqual(
            link.summary["pacing_caught_up_sends"],
            link.summary["pacing_sustained_sends"],
        )
        # No key was held long enough to repeat.
        self.assertEqual(link.summary["repeat_events"], 0)

    def test_a_pause_is_caught_up_faster_than_the_sustained_floor(self):
        """The latency the fixed 2.6 s policy imposed on a writer who stops."""
        reports = type_characters("ab") + finish()
        link = self.run_deliberate(reports)
        sent = link.events("live_viewport_sent")
        caught_up = [
            record for record in sent
            if record["pacing_reason"] == REASON_CAUGHT_UP
        ]
        self.assertTrue(caught_up)
        self.assertLessEqual(
            link.summary["pacing_maximum_pending_seconds"],
            pacing.maximum_pending_seconds(LONGEST_SIMULATED_REFRESH),
        )

    def test_a_burst_is_coalesced_rather_than_sent_per_keypress(self):
        reports = type_characters("a burst of characters typed very fast")
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.02)
        self.assert_no_input_lost_or_duplicated(link)
        self.assert_display_reconciles(link)
        self.assertLess(
            link.summary["viewport_frames_sent"],
            link.summary["events_processed"],
        )
        self.assertGreater(link.summary["viewports_superseded_locally"], 0)

    def test_sustained_typing_keeps_the_display_advancing(self):
        reports = type_characters(
            "sustained typing that runs on long enough\n"
            "to need several frames, so the panel is\n"
            "never left showing only the first few words"
        )
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        self.assert_no_input_lost_or_duplicated(link)
        self.assert_display_reconciles(link)
        self.assertGreater(link.summary["pacing_sustained_sends"], 3)
        sent = link.events("live_viewport_sent")
        self.assertGreater(len(sent), 4)

    def test_typing_while_the_display_is_busy_loses_nothing(self):
        """Input processing stays immediate no matter what the panel is doing."""
        reports = type_characters("typed straight through a refresh")
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.05)
        self.assert_no_input_lost_or_duplicated(link)
        self.assert_display_reconciles(link)
        # The panel never had two refreshes in flight.
        self.assertEqual(link.panel.maximum_concurrent, 1)

    # ------------------------------------------------------------- guarantees

    def test_a_refresh_is_never_started_while_the_magtag_is_busy(self):
        reports = type_characters("busy gate under continuous input")
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.03)
        # SimulatedPanel raises if a second refresh begins while one is running.
        self.assertEqual(link.panel.maximum_concurrent, 1)
        self.assertEqual(
            len(link.panel.starts), link.summary["refresh_started_received"]
        )

    def test_no_obsolete_viewport_is_ever_transmitted(self):
        """Every frame sent depicts the newest state at the moment it was sent."""
        reports = type_characters("obsolete frames must be coalesced away")
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.05)
        hashes = [
            record["text_hash"] for record in link.events("live_viewport_sent")
        ]
        self.assertEqual(len(hashes), len(set(hashes)))
        # The MagTag never had to discard one of ours as superseded.
        self.assertEqual(link.summary["viewport_frames_accepted"],
                         link.summary["viewport_frames_sent"])

    def test_pending_time_stays_inside_the_documented_bound(self):
        reports = type_characters(
            "maximum visible lag under continuous typing must stay bounded"
        )
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        self.assertLessEqual(
            link.summary["pacing_maximum_pending_seconds"],
            pacing.maximum_pending_seconds(LONGEST_SIMULATED_REFRESH),
        )

    def test_the_final_state_is_always_caught_up_before_the_run_ends(self):
        reports = type_characters("a final line typed right up to the end")
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        self.assert_display_reconciles(link)
        self.assertEqual(link.summary["pacing_forced_sends"], 1)
        self.assertEqual(
            link.session.editor.text,
            "a final line typed right up to the end",
        )

    def test_the_forced_final_send_still_respects_the_busy_gate(self):
        source = os.path.join(
            ROOT, "fruitjam", "magwrite_transport", "live_session.py"
        )
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("busy = self._outstanding() >= self.send_window", text)
        self.assertLess(text.index("if busy:"), text.index("if not force"))

    def test_pacing_never_reorders_or_drops_an_edit(self):
        reports = type_characters("ordering under pacing")
        reports += press_kind("HOME")
        reports += press_kind("RIGHT", 3)
        reports += press_kind("DELETE")
        reports += press_kind("END")
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.08)
        self.assert_no_input_lost_or_duplicated(link)
        # Home, three Rights, Delete: the "e" of "ordering" is removed.
        self.assertEqual(link.session.editor.text, "ordring under pacing")

    def test_every_send_records_which_regime_chose_it(self):
        reports = type_characters("regime logging")
        reports += finish()
        link = self.run_link(reports, typing_interval_seconds=0.1)
        for record in link.events("live_viewport_sent"):
            self.assertIn(
                record["pacing_reason"],
                pacing.SENDING_REASONS + ("FORCED",),
            )


if __name__ == "__main__":
    unittest.main()
