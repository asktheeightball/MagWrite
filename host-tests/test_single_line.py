import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.display_adapter import (
    SINGLE_LINE_TYPING_MODE,
    validate_physical_test_activation,
)
from magwrite.events import BoundedEventQueue, QueueOverflow
from magwrite.single_line import (
    MAX_PARTIAL_REFRESHES,
    MAX_TYPING_EVENTS,
    EditRejected,
    HorizontalViewport,
    ScheduledScenarioProducer,
    SequenceError,
    SequenceTracker,
    SingleLineEditor,
    TYPING_COMPLETE_GUARD,
    TYPING_START_GUARD,
    TypingEvent,
    numbered_scenarios,
)
from magwrite.typing_refresh import RefreshStopped, TypingRefreshCoordinator
from magwrite.test_pattern import GLYPHS


class FakeClock:
    def __init__(self):
        self.seconds = 0.0

    def __call__(self):
        return self.seconds


class FakePhysicalAdapter:
    def __init__(self, clock, duration=0.7, stuck=False):
        self.clock = clock
        self.duration = duration
        self.stuck = stuck
        self.active_until = None
        self.max_active = 0
        self.starts = []

    def begin_refresh(self, framebuffer, full=False):
        if self.active_until is not None:
            raise RuntimeError("second refresh in flight")
        self.active_until = self.clock.seconds + self.duration
        self.max_active = max(self.max_active, 1)
        self.starts.append(full)
        return full

    def is_busy(self):
        if self.active_until is None:
            return False
        if self.stuck or self.clock.seconds < self.active_until:
            return True
        self.active_until = None
        return False


class SingleLineTests(unittest.TestCase):
    def apply(self, editor, specs):
        for sequence, (kind, value) in enumerate(specs):
            editor.apply(TypingEvent(sequence, "test", kind, value))

    def test_all_scenarios_have_exact_final_text_and_order(self):
        tracker = SequenceTracker()
        total = 0
        for name, _, events, expected in numbered_scenarios():
            editor = SingleLineEditor()
            for event in events:
                tracker.accept(event)
                editor.apply(event)
            self.assertEqual(editor.text, expected, name)
            total += len(events)
        self.assertEqual(tracker.processed, total)
        self.assertLessEqual(total, MAX_TYPING_EVENTS)

    def test_physical_font_covers_layout_and_scenarios(self):
        required = "MAGWRITE TYPE TEST DOC INFLIGHT SHOWN <>"
        for _, _, events, _ in numbered_scenarios():
            required += "".join(event.value for event in events)
        self.assertEqual(set(required) - set(GLYPHS), set())

    def test_production_is_deterministic_at_all_rates(self):
        events = tuple(TypingEvent(i, "rate", "insert", "A") for i in range(8))
        for rate in ScheduledScenarioProducer.SUPPORTED_WPM:
            queue = BoundedEventQueue(16)
            producer = ScheduledScenarioProducer(events, rate)
            observed = []
            now = 0
            while not producer.complete:
                producer.produce_due(now, queue)
                event = queue.get()
                while event:
                    observed.append(event.sequence)
                    event = queue.get()
                now += 10
            self.assertEqual(observed, list(range(8)))

    def test_sequence_gap_duplicate_and_reorder_are_rejected(self):
        for bad in (1, -1, 2):
            tracker = SequenceTracker()
            with self.assertRaises(SequenceError):
                tracker.accept(TypingEvent(bad, "test", "left"))

    def test_capacity_rejection_is_explicit_and_revision_only_tracks_edits(self):
        editor = SingleLineEditor(max_chars=2)
        self.apply(editor, (("insert", "A"), ("insert", "B"), ("left", "")))
        self.assertEqual(editor.document_revision, 2)
        self.assertEqual(editor.render_revision, 3)
        with self.assertRaises(EditRejected):
            editor.apply(TypingEvent(3, "test", "insert", "C"))
        self.assertEqual(editor.rejected_events, 1)

    def test_cursor_boundaries_home_end_backspace_delete(self):
        editor = SingleLineEditor()
        self.apply(
            editor,
            (
                ("insert", "A"),
                ("insert", "B"),
                ("left", ""),
                ("backspace", ""),
                ("home", ""),
                ("delete", ""),
                ("left", ""),
                ("right", ""),
                ("end", ""),
                ("right", ""),
            ),
        )
        self.assertEqual(editor.text, "")
        self.assertEqual(editor.cursor, 0)

    def test_viewport_keeps_cursor_visible_at_boundaries(self):
        editor = SingleLineEditor(max_chars=64)
        for i, character in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            editor.apply(TypingEvent(i, "view", "insert", character))
        viewport = HorizontalViewport(columns=12)
        end = viewport.snapshot(editor)
        self.assertGreater(end["start"], 0)
        self.assertLess(end["cursor_cell"], 12)
        editor.apply(TypingEvent(27, "view", "home"))
        home = viewport.snapshot(editor)
        self.assertEqual(home["start"], 0)
        self.assertEqual(home["cursor_cell"], 1)
        for i in range(8):
            editor.apply(TypingEvent(28 + i, "view", "right"))
        middle = viewport.snapshot(editor)
        self.assertLessEqual(middle["start"], editor.cursor)
        self.assertLess(editor.cursor, middle["end"] + 1)

    def test_queue_overflow_and_limits_are_explicit(self):
        queue = BoundedEventQueue(1)
        queue.put(TypingEvent(0, "test", "left"))
        with self.assertRaises(QueueOverflow):
            queue.put(TypingEvent(1, "test", "right"))
        self.assertEqual(queue.overflow_count, 1)
        self.assertEqual(MAX_TYPING_EVENTS, 250)
        self.assertEqual(MAX_PARTIAL_REFRESHES, 100)

    def test_typing_mode_is_distinct_and_fail_closed(self):
        good = types.SimpleNamespace(
            HARDWARE_COMPATIBILITY_DECISION="COMPATIBLE",
            DISPLAY_CONTROLLER="UC8151D",
            ENABLE_PHYSICAL_DISPLAY=True,
        )
        self.assertTrue(validate_physical_test_activation(good, SINGLE_LINE_TYPING_MODE))
        for field, value in (
            ("ENABLE_PHYSICAL_DISPLAY", False),
            ("DISPLAY_CONTROLLER", "SSD1680"),
            ("HARDWARE_COMPATIBILITY_DECISION", "UNCONFIRMED"),
        ):
            bad = types.SimpleNamespace(**good.__dict__)
            setattr(bad, field, value)
            with self.assertRaises(RuntimeError):
                validate_physical_test_activation(bad, SINGLE_LINE_TYPING_MODE)

    def test_typing_guards_are_distinct_from_characterization_guards(self):
        self.assertNotEqual(TYPING_START_GUARD, TYPING_COMPLETE_GUARD)
        prior = (
            "/magwrite_refresh_test_20.started",
            "/magwrite_refresh_test_20.complete",
            "/magwrite_refresh_test_50.started",
            "/magwrite_refresh_test_50.complete",
            "/magwrite_refresh_test_100.started",
            "/magwrite_refresh_test_100.complete",
        )
        self.assertNotIn(TYPING_START_GUARD, prior)
        self.assertNotIn(TYPING_COMPLETE_GUARD, prior)

    def test_host_import_has_no_hardware_modules(self):
        for name in ("board", "busio", "digitalio", "storage", "supervisor"):
            self.assertNotIn(name, sys.modules)

    def test_newest_snapshot_coalesces_and_catches_up(self):
        clock = FakeClock()
        adapter = FakePhysicalAdapter(clock)
        logs = []
        coordinator = TypingRefreshCoordinator(
            adapter, logs.append, clock, full_refresh_interval=50
        )
        coordinator.offer(b"a", 1, 1, "fast")
        coordinator.service()
        self.assertEqual(coordinator.inflight_revision, 1)
        for revision in range(2, 8):
            coordinator.offer(bytes((revision,)), revision, revision, "fast")
        self.assertGreater(coordinator.stale_frames_skipped, 0)
        clock.seconds = 0.8
        coordinator.service()
        self.assertLessEqual(coordinator.displayed_revision, coordinator.latest[1])
        self.assertEqual(coordinator.inflight_revision, 7)
        clock.seconds = 1.6
        coordinator.service()
        self.assertTrue(coordinator.caught_up)
        self.assertEqual(coordinator.displayed_revision, 7)
        self.assertEqual(adapter.max_active, 1)
        self.assertGreater(coordinator.catch_up_refreshes, 0)

    def test_timeout_stops_later_refreshes(self):
        clock = FakeClock()
        adapter = FakePhysicalAdapter(clock, stuck=True)
        coordinator = TypingRefreshCoordinator(
            adapter, lambda record: None, clock, timeout_seconds=1.0
        )
        coordinator.offer(b"a", 1, 1, "test")
        coordinator.service()
        clock.seconds = 1.1
        with self.assertRaises(RefreshStopped):
            coordinator.service()
        self.assertEqual(len(adapter.starts), 1)
        self.assertEqual(coordinator.timeouts, 1)


if __name__ == "__main__":
    unittest.main()
