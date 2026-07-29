"""Regression cover for the arming-wait defect found on the first physical run.

The MagTag previously started its test deadline at ``editor_display_ready``,
so the operator-paced arming wait was charged to the run budget. On the
2026-07-28 attempt that consumed 112 s of a 150 s budget and the run timed out
39 s in, with the editor itself behaving correctly.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.run_clock import ARMING_TIMEOUT, RUN_TIMEOUT, RunClock


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RunClockTests(unittest.TestCase):
    def clock(self, arming=900, run=150):
        fake = FakeClock()
        return fake, RunClock(fake, arming, run)

    def test_arming_wait_is_not_charged_to_the_run(self):
        fake, clock = self.clock()
        fake.advance(112)                      # the observed arming wait
        self.assertIsNone(clock.expired())
        self.assertEqual(clock.start_run(), 112)
        fake.advance(149)
        self.assertIsNone(clock.expired(), "run budget must survive the wait")
        fake.advance(2)
        self.assertEqual(clock.expired(), RUN_TIMEOUT)

    def test_the_original_defect_would_have_failed_this_test(self):
        # Arming wait plus run time exceeds the run budget, yet must pass.
        fake, clock = self.clock()
        fake.advance(112)
        clock.start_run()
        fake.advance(100)
        self.assertGreater(112 + 100, 150)
        self.assertIsNone(clock.expired())

    def test_arming_phase_has_its_own_generous_bound(self):
        fake, clock = self.clock()
        self.assertFalse(clock.running)
        fake.advance(900)
        self.assertIsNone(clock.expired())
        fake.advance(1)
        self.assertEqual(clock.expired(), ARMING_TIMEOUT)

    def test_start_run_is_idempotent(self):
        fake, clock = self.clock()
        fake.advance(10)
        self.assertEqual(clock.start_run(), 10)
        fake.advance(5)
        self.assertEqual(clock.start_run(), 10, "must not restart the deadline")
        self.assertEqual(clock.elapsed(), 5)

    def test_elapsed_tracks_the_current_phase(self):
        fake, clock = self.clock()
        fake.advance(30)
        self.assertEqual(clock.elapsed(), 30)
        clock.start_run()
        fake.advance(7)
        self.assertEqual(clock.elapsed(), 7)

    def test_configured_budgets_are_present_and_ordered(self):
        import config

        self.assertEqual(config.EDITOR_TEST_TIMEOUT_SECONDS, 150)
        self.assertGreater(
            config.EDITOR_ARMING_TIMEOUT_SECONDS,
            config.EDITOR_TEST_TIMEOUT_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
