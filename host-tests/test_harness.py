import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.editor import LineEditor
from magwrite.events import (
    BoundedEventQueue,
    DeterministicProducer,
    QueueOverflow,
)
from magwrite.refresh import RefreshCoordinator, SimulatedAsyncDisplay
from magwrite.renderer import LandscapeRenderer


class HarnessTests(unittest.TestCase):
    def run_stream(self, wpm, text, display_duration=900, capacity=128):
        producer = DeterministicProducer(text, wpm)
        queue = BoundedEventQueue(capacity)
        editor = LineEditor(max_lines=8, max_chars=2048)
        display = SimulatedAsyncDisplay(display_duration)
        logs = []
        refresh = RefreshCoordinator(
            display, LandscapeRenderer(), full_refresh_interval=3, logger=logs.append
        )
        accepted_sequences = []
        now_ms = 0
        deadline = int(len(text) * producer.interval_ms + display_duration * 4)
        while now_ms <= deadline:
            producer.produce_due(now_ms, queue)
            event = queue.get()
            while event is not None:
                accepted_sequences.append(event.sequence)
                editor.apply(event)
                refresh.note_event(editor.revision)
                event = queue.get()
            refresh.service(now_ms, editor)
            now_ms += 10
        return editor, refresh, accepted_sequences, logs

    def test_80_wpm_is_ordered_lossless_and_catches_up(self):
        text = "the quick brown fox jumps over the lazy dog " * 4
        editor, refresh, sequences, logs = self.run_stream(80, text)
        self.assertEqual(editor.text, text)
        self.assertEqual(sequences, list(range(len(text))))
        self.assertEqual(editor.revision, len(text))
        self.assertEqual(editor.accepted_events, len(text))
        self.assertEqual(refresh.event_count, len(text))
        self.assertEqual(refresh.displayed_revision, editor.revision)
        self.assertGreater(refresh.stale_frame_count, 0)
        self.assertTrue(any(item["event"] == "refresh_start" for item in logs))
        self.assertTrue(any(item["event"] == "refresh_end" for item in logs))

    def test_all_required_rates(self):
        for wpm in DeterministicProducer.SUPPORTED_WPM:
            editor, refresh, sequences, _ = self.run_stream(wpm, "rate test")
            self.assertEqual(sequences, list(range(9)))
            self.assertEqual(refresh.displayed_revision, editor.revision)

    def test_queue_overflow_is_explicit_and_bounded(self):
        producer = DeterministicProducer("abcdef", 80)
        queue = BoundedEventQueue(2)
        with self.assertRaises(QueueOverflow):
            producer.produce_due(1000, queue)
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue.overflow_count, 1)

    def test_periodic_full_refresh_is_bounded_policy(self):
        editor, refresh, _, _ = self.run_stream(
            80, "abcdefghijklmnopqrstuv", display_duration=150
        )
        full_flags = [full for _, full in refresh.display.started]
        self.assertTrue(full_flags[0])
        self.assertEqual(refresh.full_refresh_count, sum(full_flags))
        self.assertGreaterEqual(refresh.full_refresh_count, 2)
        self.assertEqual(refresh.displayed_revision, editor.revision)


if __name__ == "__main__":
    unittest.main()
