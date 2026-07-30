"""Editor, layout, viewport, and input-adapter behaviour on the host.

These tests own detailed editor correctness so the physical run can stay a
single bounded smoke test.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.viewport_message import MAX_LINE_CHARS, MAX_LINES, ViewportMessage
from magwrite_transport.deterministic_viewports import MAX_VIEWPORT_LINES
from magwrite_transport.editor import (
    BACKSPACE, BoundedEventQueue, CHAR, DELETE, DOWN, END, ENTER, EditRejected,
    HOME, InputEvent, LEFT, MAX_DOCUMENT_CHARS, MAX_DOCUMENT_LINES,
    MAX_EDITOR_EVENTS, MultilineEditor, QueueOverflow, RIGHT, SequenceError,
    SequenceTracker, UP,
)
from magwrite_transport.editor_layout import Layout
from magwrite_transport.editor_scenarios import (
    MAX_EDITOR_PARTIAL_REFRESHES, MAX_EDITOR_STATUS_FRAMES,
    MAX_EDITOR_VIEWPORT_FRAMES, ScheduledEventProducer, numbered_scenarios,
    scenario_specs, total_event_count,
)
from magwrite_transport.editor_viewport import EditorViewport
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE


def build(editor, script):
    """Apply a compact ``(kind, value)`` script to an editor."""
    for sequence, item in enumerate(script):
        kind, value = item if isinstance(item, tuple) else (item, "")
        editor.apply(InputEvent(sequence, "test", kind, value))
    return editor


def typed(text):
    """Expand text into CHAR and ENTER pairs."""
    return [(ENTER, "") if c == "\n" else (CHAR, c) for c in text]


class MultilineEditingTest(unittest.TestCase):
    def setUp(self):
        self.editor = MultilineEditor()

    def test_multiline_insertion(self):
        build(self.editor, typed("ABC\nDEF\nGHI"))
        self.assertEqual(self.editor.lines, ["ABC", "DEF", "GHI"])
        self.assertEqual(self.editor.text, "ABC\nDEF\nGHI")
        self.assertEqual((self.editor.row, self.editor.column), (2, 3))

    def test_insertion_within_a_line(self):
        build(self.editor, typed("AC") + [(LEFT, ""), (CHAR, "B")])
        self.assertEqual(self.editor.lines, ["ABC"])
        self.assertEqual(self.editor.column, 2)

    def test_enter_splits_lines(self):
        build(self.editor, typed("ABCD") + [(HOME, "")] + [(RIGHT, "")] * 2)
        self.editor.apply(InputEvent(99, "t", ENTER))
        self.assertEqual(self.editor.lines, ["AB", "CD"])
        self.assertEqual((self.editor.row, self.editor.column), (1, 0))

    def test_backspace_joins_lines(self):
        build(self.editor, typed("AB\nCD") + [(HOME, ""), (BACKSPACE, "")])
        self.assertEqual(self.editor.lines, ["ABCD"])
        self.assertEqual((self.editor.row, self.editor.column), (0, 2))

    def test_backspace_within_a_line(self):
        build(self.editor, typed("ABC") + [(BACKSPACE, "")])
        self.assertEqual(self.editor.lines, ["AB"])

    def test_delete_joins_lines(self):
        build(self.editor, typed("AB\nCD") + [(HOME, ""), (LEFT, ""), (DELETE, "")])
        self.assertEqual(self.editor.lines, ["ABCD"])
        self.assertEqual((self.editor.row, self.editor.column), (0, 2))

    def test_delete_within_a_line(self):
        build(self.editor, typed("ABC") + [(HOME, ""), (DELETE, "")])
        self.assertEqual(self.editor.lines, ["BC"])

    def test_backspace_at_document_start_is_a_no_op(self):
        build(self.editor, [(BACKSPACE, "")])
        self.assertEqual(self.editor.lines, [""])
        self.assertEqual(self.editor.document_revision, 0)

    def test_delete_at_document_end_is_a_no_op(self):
        build(self.editor, typed("AB") + [(DELETE, "")])
        self.assertEqual(self.editor.lines, ["AB"])

    def test_left_and_right_cross_line_boundaries(self):
        build(self.editor, typed("AB\nCD") + [(HOME, "")])
        self.editor.apply(InputEvent(90, "t", LEFT))
        self.assertEqual((self.editor.row, self.editor.column), (0, 2))
        self.editor.apply(InputEvent(91, "t", RIGHT))
        self.assertEqual((self.editor.row, self.editor.column), (1, 0))

    def test_left_at_start_and_right_at_end_are_no_ops(self):
        build(self.editor, typed("AB") + [(HOME, ""), (LEFT, "")])
        self.assertEqual((self.editor.row, self.editor.column), (0, 0))
        build(self.editor, [(END, ""), (RIGHT, "")])
        self.assertEqual((self.editor.row, self.editor.column), (0, 2))

    def test_home_and_end(self):
        build(self.editor, typed("ABCDE") + [(HOME, "")])
        self.assertEqual(self.editor.column, 0)
        self.editor.apply(InputEvent(80, "t", END))
        self.assertEqual(self.editor.column, 5)

    def test_up_and_down_use_the_preferred_visual_column(self):
        build(self.editor, typed("ABCDEFGH\nXY\nIJKLMNOP") + [(END, "")])
        self.assertEqual((self.editor.row, self.editor.column), (2, 8))
        self.editor.apply(InputEvent(70, "t", UP))
        # The short middle line clamps the cursor to its end.
        self.assertEqual((self.editor.row, self.editor.column), (1, 2))
        self.editor.apply(InputEvent(71, "t", UP))
        # The preferred column is remembered, not lost to the clamp.
        self.assertEqual((self.editor.row, self.editor.column), (0, 8))
        self.editor.apply(InputEvent(72, "t", DOWN))
        self.assertEqual((self.editor.row, self.editor.column), (1, 2))
        self.editor.apply(InputEvent(73, "t", DOWN))
        self.assertEqual((self.editor.row, self.editor.column), (2, 8))

    def test_horizontal_motion_resets_the_preferred_column(self):
        build(self.editor, typed("ABCDEFGH\nXY\nIJKLMNOP") + [(END, ""), (UP, "")])
        self.editor.apply(InputEvent(60, "t", LEFT))
        self.assertEqual((self.editor.row, self.editor.column), (1, 1))
        self.editor.apply(InputEvent(61, "t", UP))
        self.assertEqual((self.editor.row, self.editor.column), (0, 1))

    def test_up_at_the_top_and_down_at_the_bottom_are_no_ops(self):
        build(self.editor, typed("AB\nCD"))
        self.editor.apply(InputEvent(50, "t", DOWN))
        self.assertEqual((self.editor.row, self.editor.column), (1, 2))
        build(self.editor, [(HOME, ""), (UP, ""), (UP, "")])
        self.assertEqual((self.editor.row, self.editor.column), (0, 0))

    def test_up_and_down_move_by_visual_row_inside_one_logical_line(self):
        editor = MultilineEditor(layout=Layout(width=10, height=5))
        build(editor, typed("AAAA BBBB CCCC DDDD"))
        rows = editor.visual_rows()
        self.assertGreater(len(rows), 1)
        index_before = editor.cursor_visual_position()[0]
        editor.apply(InputEvent(40, "t", UP))
        self.assertEqual(editor.cursor_visual_position()[0], index_before - 1)
        self.assertEqual(editor.row, 0)


class EditorBoundsTest(unittest.TestCase):
    def test_document_capacity_is_rejected_explicitly(self):
        editor = MultilineEditor(max_chars=4, max_line_chars=99)
        build(editor, typed("ABCD"))
        with self.assertRaises(EditRejected):
            editor.apply(InputEvent(9, "t", CHAR, "E"))
        self.assertEqual(editor.rejected_events, 1)
        self.assertEqual(editor.text, "ABCD")

    def test_line_count_is_rejected_explicitly(self):
        editor = MultilineEditor(max_lines=2)
        build(editor, typed("A\nB"))
        with self.assertRaises(EditRejected):
            editor.apply(InputEvent(9, "t", ENTER))
        self.assertEqual(len(editor.lines), 2)

    def test_line_length_is_rejected_explicitly(self):
        editor = MultilineEditor(max_line_chars=3)
        build(editor, typed("ABC"))
        with self.assertRaises(EditRejected):
            editor.apply(InputEvent(9, "t", CHAR, "D"))
        self.assertEqual(editor.lines, ["ABC"])

    def test_join_that_would_overflow_a_line_is_rejected(self):
        editor = MultilineEditor(max_line_chars=4)
        build(editor, typed("ABC\nDEF") + [(HOME, "")])
        with self.assertRaises(EditRejected):
            editor.apply(InputEvent(9, "t", BACKSPACE))
        self.assertEqual(editor.lines, ["ABC", "DEF"])

    def test_a_rejected_edit_never_changes_state(self):
        editor = MultilineEditor(max_line_chars=2)
        build(editor, typed("AB"))
        before = (list(editor.lines), editor.row, editor.column,
                  editor.document_revision, editor.viewport_revision)
        with self.assertRaises(EditRejected):
            editor.apply(InputEvent(9, "t", CHAR, "C"))
        after = (list(editor.lines), editor.row, editor.column,
                 editor.document_revision, editor.viewport_revision)
        self.assertEqual(before, after)

    def test_non_ascii_and_unknown_kinds_are_refused_at_construction(self):
        with self.assertRaises(ValueError):
            InputEvent(0, "t", CHAR, "é")
        with self.assertRaises(ValueError):
            InputEvent(0, "t", "PASTE")
        with self.assertRaises(ValueError):
            InputEvent(0, "t", CHAR, "AB")

    def test_default_bounds_are_the_documented_ones(self):
        editor = MultilineEditor()
        self.assertEqual(editor.max_chars, MAX_DOCUMENT_CHARS)
        self.assertEqual(editor.max_lines, MAX_DOCUMENT_LINES)


class RevisionSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.editor = MultilineEditor()

    def test_document_revision_changes_only_when_text_changes(self):
        build(self.editor, typed("AB"))
        document = self.editor.document_revision
        build(self.editor, [(LEFT, ""), (RIGHT, ""), (HOME, ""), (END, "")])
        self.assertEqual(self.editor.document_revision, document)

    def test_cursor_movement_advances_the_viewport_revision(self):
        build(self.editor, typed("AB"))
        viewport = self.editor.viewport_revision
        build(self.editor, [(LEFT, "")])
        self.assertEqual(self.editor.viewport_revision, viewport + 1)

    def test_motion_that_changes_nothing_advances_no_revision(self):
        build(self.editor, typed("AB") + [(HOME, "")])
        document = self.editor.document_revision
        viewport = self.editor.viewport_revision
        build(self.editor, [(HOME, ""), (LEFT, ""), (UP, "")])
        self.assertEqual(self.editor.document_revision, document)
        self.assertEqual(self.editor.viewport_revision, viewport)

    def test_text_change_advances_both_revisions(self):
        build(self.editor, typed("A"))
        self.assertEqual(self.editor.document_revision, 1)
        self.assertEqual(self.editor.viewport_revision, 1)

    def test_reset_keeps_revisions_monotonic(self):
        build(self.editor, typed("AB\nCD"))
        document = self.editor.document_revision
        viewport = self.editor.viewport_revision
        self.assertTrue(self.editor.reset_document())
        self.assertEqual(self.editor.lines, [""])
        self.assertGreater(self.editor.document_revision, document)
        self.assertGreater(self.editor.viewport_revision, viewport)
        self.assertFalse(self.editor.reset_document())


class InputAdapterTest(unittest.TestCase):
    def test_exactly_once_and_in_order(self):
        tracker = SequenceTracker()
        for sequence in range(5):
            tracker.accept(InputEvent(sequence, "t", CHAR, "A"))
        self.assertEqual(tracker.processed, 5)
        self.assertEqual(tracker.expected, 5)

    def test_duplicate_sequence_is_refused(self):
        tracker = SequenceTracker()
        tracker.accept(InputEvent(0, "t", CHAR, "A"))
        with self.assertRaises(SequenceError):
            tracker.accept(InputEvent(0, "t", CHAR, "A"))

    def test_out_of_order_and_gapped_sequences_are_refused(self):
        tracker = SequenceTracker()
        tracker.accept(InputEvent(0, "t", CHAR, "A"))
        with self.assertRaises(SequenceError):
            tracker.accept(InputEvent(2, "t", CHAR, "A"))
        tracker = SequenceTracker()
        tracker.accept(InputEvent(0, "t", CHAR, "A"))
        tracker.accept(InputEvent(1, "t", CHAR, "A"))
        with self.assertRaises(SequenceError):
            tracker.accept(InputEvent(1, "t", CHAR, "A"))

    def test_queue_overflow_is_explicit_and_counted(self):
        queue = BoundedEventQueue(2)
        queue.put(InputEvent(0, "t", CHAR, "A"))
        queue.put(InputEvent(1, "t", CHAR, "B"))
        with self.assertRaises(QueueOverflow):
            queue.put(InputEvent(2, "t", CHAR, "C"))
        self.assertEqual(queue.overflow_count, 1)
        self.assertEqual(len(queue), 2)

    def test_queue_is_fifo_and_records_maximum_depth(self):
        queue = BoundedEventQueue(4)
        for sequence in range(3):
            queue.put(InputEvent(sequence, "t", CHAR, "A"))
        self.assertEqual(queue.maximum_depth, 3)
        self.assertEqual(queue.get().sequence, 0)
        self.assertEqual(queue.get().sequence, 1)
        queue.put(InputEvent(3, "t", CHAR, "A"))
        self.assertEqual(queue.get().sequence, 2)
        self.assertEqual(queue.get().sequence, 3)
        self.assertIsNone(queue.get())

    def test_producer_emits_each_event_once_when_due(self):
        events = tuple(InputEvent(i, "t", CHAR, "A", i * 150) for i in range(4))
        producer = ScheduledEventProducer(events, 80)
        queue = BoundedEventQueue(8)
        self.assertEqual(producer.produce_due(0.0, queue), 1)
        self.assertEqual(producer.produce_due(149.0, queue), 0)
        self.assertEqual(producer.produce_due(450.0, queue), 3)
        self.assertTrue(producer.complete)
        self.assertEqual(producer.produce_due(9999.0, queue), 0)
        self.assertEqual([queue.get().sequence for _ in range(4)], [0, 1, 2, 3])

    def test_producer_respects_the_drain_budget(self):
        events = tuple(InputEvent(i, "t", CHAR, "A", i * 150) for i in range(10))
        producer = ScheduledEventProducer(events, 80)
        queue = BoundedEventQueue(16)
        # Everything is long overdue, so only the budget limits the drain.
        self.assertEqual(producer.produce_due(10000.0, queue, budget=4), 4)
        self.assertFalse(producer.complete)
        self.assertEqual(producer.produce_due(10000.0, queue, budget=4), 4)

    def test_producer_overflow_surfaces_as_queue_overflow(self):
        events = tuple(InputEvent(i, "t", CHAR, "A", i * 150) for i in range(4))
        producer = ScheduledEventProducer(events, 80)
        with self.assertRaises(QueueOverflow):
            producer.produce_due(10000.0, BoundedEventQueue(2))


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.layout = Layout(width=10, height=3)

    def test_short_line_is_one_visual_row(self):
        self.assertEqual(self.layout.wrap_line("ABC"), ((0, 3),))
        self.assertEqual(self.layout.wrap_line(""), ((0, 0),))

    def test_deterministic_word_wrapping_consumes_the_break_space(self):
        # "ALPHA BETA" is exactly the width, so greedy wrapping keeps it whole
        # and the space at index 10 is consumed by the break.
        line = "ALPHA BETA GAMMA"
        spans = self.layout.wrap_line(line)
        self.assertEqual(spans, ((0, 10), (11, 16)))
        self.assertEqual([line[a:b] for a, b in spans], ["ALPHA BETA", "GAMMA"])

    def test_wrapping_breaks_at_the_last_space_that_fits(self):
        line = "AAA BBB CCC DDD"
        spans = self.layout.wrap_line(line)
        self.assertEqual(spans, ((0, 7), (8, 15)))
        self.assertEqual([line[a:b] for a, b in spans], ["AAA BBB", "CCC DDD"])

    def test_word_exactly_the_width_is_not_wrapped(self):
        self.assertEqual(self.layout.wrap_line("ABCDEFGHIJ"), ((0, 10),))

    def test_long_word_hard_wraps(self):
        line = "ABCDEFGHIJKLMNOPQRSTUVW"
        spans = self.layout.wrap_line(line)
        self.assertEqual(spans, ((0, 10), (10, 20), (20, 23)))
        self.assertEqual(
            [line[a:b] for a, b in spans],
            ["ABCDEFGHIJ", "KLMNOPQRST", "UVW"],
        )

    def test_long_word_after_a_short_word_hard_wraps(self):
        line = "AB CDEFGHIJKLMNOP"
        spans = self.layout.wrap_line(line)
        self.assertEqual([line[a:b] for a, b in spans],
                         ["AB", "CDEFGHIJKL", "MNOP"])

    def test_layout_is_a_pure_function_of_document_and_width(self):
        lines = ["ALPHA BETA GAMMA", "DELTA"]
        self.assertEqual(self.layout.rows(lines), self.layout.rows(lines))

    def test_locate_maps_the_cursor_to_a_visual_cell(self):
        lines = ["ALPHA BETA GAMMA"]
        self.assertEqual(self.layout.locate(lines, 0, 0), (0, 0))
        self.assertEqual(self.layout.locate(lines, 0, 5), (0, 5))
        # Column 10 is the end of the first visual row; 11 starts the second,
        # because the space at index 10 was consumed by the break.
        self.assertEqual(self.layout.locate(lines, 0, 10), (0, 10))
        self.assertEqual(self.layout.locate(lines, 0, 11), (1, 0))
        self.assertEqual(self.layout.locate(lines, 0, 16), (1, 5))

    def test_locate_prefers_the_continuation_row_on_a_hard_wrap(self):
        lines = ["ABCDEFGHIJKL"]
        self.assertEqual(self.layout.locate(lines, 0, 10), (1, 0))

    def test_locate_rejects_a_cursor_outside_the_document(self):
        with self.assertRaises(ValueError):
            self.layout.locate(["AB"], 0, 5)

    def test_scroll_keeps_the_cursor_visible(self):
        lines = ["A", "B", "C", "D", "E", "F"]
        for row in range(len(lines)):
            window = self.layout.window(lines, row, 0)
            self.assertGreaterEqual(window["cursor_row"], 0)
            self.assertLess(window["cursor_row"], self.layout.height)
            self.assertLessEqual(len(window["lines"]), self.layout.height)

    def test_vertical_scrolling_pins_the_cursor_to_the_last_row(self):
        lines = ["A", "B", "C", "D", "E", "F"]
        window = self.layout.window(lines, 5, 0)
        self.assertEqual(window["top"], 3)
        self.assertEqual(window["lines"], ("D", "E", "F"))
        self.assertEqual(window["cursor_row"], 2)
        self.assertTrue(window["more_above"])
        self.assertFalse(window["more_below"])

    def test_short_document_is_not_scrolled(self):
        window = self.layout.window(["A", "B"], 0, 0)
        self.assertEqual(window["top"], 0)
        self.assertFalse(window["more_above"])
        self.assertFalse(window["more_below"])

    def test_window_is_deterministic_and_history_free(self):
        lines = ["A", "B", "C", "D", "E", "F"]
        walked = self.layout.window(lines, 5, 0)
        self.layout.window(lines, 0, 0)
        self.assertEqual(self.layout.window(lines, 5, 0), walked)

    def test_layout_bounds_are_validated(self):
        with self.assertRaises(ValueError):
            Layout(width=1)
        with self.assertRaises(ValueError):
            Layout(width=10, height=0)


class ViewportTest(unittest.TestCase):
    def setUp(self):
        self.viewport = EditorViewport()
        self.editor = MultilineEditor(layout=self.viewport.layout)

    def test_payload_is_deterministic_for_identical_state(self):
        build(self.editor, typed("HELLO WORLD"))
        self.assertEqual(
            self.viewport.payload(self.editor, 1),
            self.viewport.payload(self.editor, 1),
        )

    def test_payload_decodes_as_a_valid_viewport_message(self):
        build(self.editor, typed("ALPHA BETA\nGAMMA"))
        payload = self.viewport.payload(self.editor, 3)
        message = ViewportMessage.decode(self.editor.viewport_revision, payload)
        self.assertEqual(message.scenario_id, 3)
        self.assertEqual(message.lines, ("ALPHA BETA", "GAMMA"))
        self.assertLessEqual(len(message.lines), MAX_LINES)

    def test_viewport_is_pre_windowed_and_never_exceeds_the_panel(self):
        build(self.editor, typed("\n".join("LINE %d" % n for n in range(9))))
        payload = self.viewport.payload(self.editor, 1)
        message = ViewportMessage.decode(1, payload)
        self.assertEqual(len(message.lines), MAX_VIEWPORT_LINES)
        for line in message.lines:
            self.assertLessEqual(len(line), MAX_LINE_CHARS)

    def test_cursor_is_always_inside_the_transmitted_viewport(self):
        script = typed("\n".join("ROW %d" % n for n in range(9)))
        for step in range(1, len(script) + 1):
            editor = MultilineEditor(layout=self.viewport.layout)
            build(editor, script[:step])
            message = ViewportMessage.decode(
                1, self.viewport.payload(editor, 1)
            )
            self.assertLess(message.cursor_row, len(message.lines))
            self.assertLessEqual(
                message.cursor_column, len(message.lines[message.cursor_row])
            )

    def test_worst_case_payload_fits_the_protocol_maximum(self):
        editor = MultilineEditor(layout=self.viewport.layout)
        wide = "W" * MAX_LINE_CHARS
        build(editor, typed("\n".join([wide] * (MAX_VIEWPORT_LINES + 2))))
        payload = self.viewport.payload(editor, 255)
        self.assertLessEqual(len(payload), MAX_PAYLOAD_SIZE)
        ViewportMessage.decode(1, payload)

    def test_status_and_title_report_authoritative_state(self):
        build(self.editor, typed("AB\nCD"))
        window = self.viewport.window(self.editor)
        self.assertIn("L02", self.viewport.title_text(self.editor))
        self.assertIn("C02", self.viewport.title_text(self.editor))
        status = self.viewport.status_text(self.editor, window)
        self.assertTrue(status.startswith("D"))
        self.assertLessEqual(len(status), 20)
        self.assertLessEqual(len(self.viewport.title_text(self.editor)), 20)

    def test_empty_document_still_produces_one_line(self):
        message = ViewportMessage.decode(0, self.viewport.payload(self.editor, 1))
        self.assertEqual(message.lines, ("",))
        self.assertEqual(message.cursor_row, 0)
        self.assertEqual(message.cursor_column, 0)


class ScenarioTest(unittest.TestCase):
    def test_every_scenario_reaches_its_exact_expected_document(self):
        layout = Layout()
        for name, _, _, _, _, events, expected in numbered_scenarios():
            editor = MultilineEditor(layout=layout)
            for event in events:
                editor.apply(event)
            self.assertEqual(editor.text, expected, name)

    def test_scenarios_only_use_supported_event_kinds(self):
        for name, _, _, _, _, events, _ in numbered_scenarios():
            for event in events:
                self.assertIn(
                    event.kind,
                    (CHAR, ENTER, BACKSPACE, DELETE, LEFT, RIGHT, UP, DOWN,
                     HOME, END),
                    name,
                )

    def test_sequences_are_monotonic_across_the_whole_run(self):
        expected = 0
        for _, _, _, _, _, events, _ in numbered_scenarios():
            for event in events:
                self.assertEqual(event.sequence, expected)
                expected += 1
        self.assertEqual(expected, total_event_count())

    def test_scheduled_times_are_monotonic(self):
        previous = -1
        for _, _, _, _, _, events, _ in numbered_scenarios():
            for event in events:
                self.assertGreaterEqual(event.scheduled_ms, previous)
                previous = event.scheduled_ms

    def test_scenario_five_produces_a_fully_visible_final_note(self):
        layout = Layout()
        name, scenario_id, _, _, _, events, expected = numbered_scenarios()[4]
        self.assertEqual(name, "journal")
        editor = MultilineEditor(layout=layout)
        for event in events:
            editor.apply(event)
        window = layout.window(editor.lines, editor.row, editor.column)
        self.assertFalse(window["more_above"])
        self.assertFalse(window["more_below"])
        # "Fully visible" is the property, not a row count: the note has to fit
        # the panel, and a wider panel fits it in fewer rows.
        self.assertLessEqual(window["total_rows"], layout.height)
        self.assertEqual(len(window["lines"]), window["total_rows"])

    def test_scenario_four_actually_scrolls(self):
        layout = Layout()
        name, _, _, _, _, events, _ = numbered_scenarios()[3]
        self.assertEqual(name, "scrolling")
        editor = MultilineEditor(layout=layout)
        tops = set()
        for event in events:
            editor.apply(event)
            tops.add(layout.window(editor.lines, editor.row, editor.column)["top"])
        self.assertGreater(len(tops), 1)
        self.assertGreater(
            len(editor.visual_rows()), layout.height
        )

    def test_scenario_three_is_the_eighty_wpm_case(self):
        name, _, wpm, _, _, _, _ = numbered_scenarios()[2]
        self.assertEqual(name, "fast_typing")
        self.assertEqual(wpm, 80)

    def test_event_total_is_inside_the_physical_ceiling(self):
        self.assertLessEqual(total_event_count(), MAX_EDITOR_EVENTS)
        self.assertLessEqual(MAX_EDITOR_EVENTS, 400)

    def test_frame_budgets_sit_under_the_physical_ceilings(self):
        budget = sum(item[4] for item in scenario_specs()) + len(scenario_specs())
        self.assertLessEqual(budget, MAX_EDITOR_VIEWPORT_FRAMES)
        self.assertLessEqual(MAX_EDITOR_VIEWPORT_FRAMES, 75)
        self.assertLessEqual(MAX_EDITOR_STATUS_FRAMES, 150)
        self.assertLessEqual(MAX_EDITOR_PARTIAL_REFRESHES, 40)

    def test_scenario_text_is_renderable_by_the_proven_glyph_table(self):
        from magwrite.test_pattern import GLYPHS
        for name, _, _, _, _, events, expected in numbered_scenarios():
            for character in expected:
                if character != "\n":
                    self.assertIn(character, GLYPHS, name)


if __name__ == "__main__":
    unittest.main()
