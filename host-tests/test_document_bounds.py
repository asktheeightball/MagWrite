"""The practical document limit: real lengths, scrolling, and clean refusal.

Written for V1.4, which replaced the transport-experiment bounds -- 512
characters over 32 lines of 96 -- with a bound sized for writing. The V1.3 bench
session hit ``document line capacity reached`` four times in ordinary prose,
because the editor word-wraps and a paragraph is therefore one logical line, so
96 characters was about a sentence and a half.

Four properties are asserted here and each one is a different way the change
could have been wrong:

* documents far longer than the old bounds are accepted, edited, and laid out;
* scrolling is correct at the beginning, the middle, and the end of a long
  document -- the window is a pure function of the cursor, so "the end" is the
  case where an off-by-one would show;
* editing still behaves at the very edge of the bound, where the last character
  that fits and the first that does not are one keystroke apart;
* the refusal at the real limit is clean: explicit, counted, and **lossless**.
  The document, the cursor, and the revision are all exactly what they were.

Nothing here uses a literal bound. Every test derives its sizes from the editor's
own constants, so these keep testing the property the next time the bounds move
rather than silently passing on a document that is no longer near a limit.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from fake_filesystem import FakeFileSystem
from magwrite.viewport_message import ViewportMessage
from magwrite_transport.deterministic_viewports import MAX_VIEWPORT_LINES
from magwrite_transport.document_store import DocumentStore
from magwrite_transport.editor import (
    BACKSPACE, CHAR, DOWN, EditRejected, ENTER, InputEvent, LEFT,
    MAX_DOCUMENT_CHARS, MAX_DOCUMENT_LINES, MAX_LINE_CHARS, MultilineEditor,
    RIGHT, UP,
)
from magwrite_transport.editor_layout import Layout, VIEWPORT_ROWS
from magwrite_transport.editor_viewport import EditorViewport
from magwrite_transport.journal import (
    MAX_RECORD_BYTES, Snapshot, decode_record, encode_record,
)
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE

# One paragraph of ordinary prose. Deliberately longer than the whole pre-V1.4
# document, so a test that uses several of them is testing the new bound rather
# than describing the old one.
PARAGRAPH = (
    "The panel is calm and the keyboard is the only thing making noise. "
    "There is nothing to check and nothing arriving, so the words are the "
    "only work in the room, which is the entire point of building it this "
    "way rather than opening a laptop and hoping."
)


def event(kind, value="", sequence=0):
    return InputEvent(sequence, "bounds", kind, value)


def type_text(editor, text):
    """Apply ``text`` through the ordinary event path, not by assignment."""
    for character in text:
        if character == "\n":
            editor.apply(event(ENTER))
        else:
            editor.apply(event(CHAR, character))
    return editor


def prose(target_chars):
    """Return roughly ``target_chars`` of paragraphs separated by line breaks."""
    out = []
    total = 0
    while total < target_chars:
        out.append(PARAGRAPH)
        total += len(PARAGRAPH) + 1
    return "\n".join(out)


class BoundShapeTests(unittest.TestCase):
    """The bounds themselves, before anything is done with them."""

    def test_the_document_bound_admits_a_real_piece_of_writing(self):
        # A journal entry or a short essay, not a paragraph. Asserted as a word
        # count because that is the unit the bound exists to serve.
        words = MAX_DOCUMENT_CHARS / 6.0
        self.assertGreaterEqual(words, 1000)

    def test_a_paragraph_fits_on_one_logical_line(self):
        # The defect V1.4 fixes. A writer never presses Enter mid-paragraph --
        # the editor wraps -- so the line bound has to hold a paragraph or it is
        # the bound that gets hit first, which is what happened on the bench.
        self.assertGreater(MAX_LINE_CHARS, len(PARAGRAPH))

    def test_the_character_bound_binds_before_the_line_bound_for_prose(self):
        # Requirement 2: a character limit, not a low line-count limit. With
        # paragraphs of a realistic length, the document fills up long before
        # the line count does.
        paragraphs = MAX_DOCUMENT_CHARS // (len(PARAGRAPH) + 1)
        self.assertLess(paragraphs, MAX_DOCUMENT_LINES)

    def test_the_line_bound_cannot_be_reached_without_exceeding_the_document(self):
        # Not a contradiction of the test above: one *line* of the maximum
        # length is fine, but the line bound cannot be the thing that stops a
        # writer whose lines are prose-shaped.
        self.assertLessEqual(MAX_LINE_CHARS, MAX_DOCUMENT_CHARS)

    def test_the_journal_record_bound_is_derived_from_the_document_bound(self):
        # The two drifting apart would mean a document the editor accepts and
        # the journal refuses to encode: a document that saves until it doesn't.
        self.assertGreaterEqual(MAX_RECORD_BYTES, 2 * MAX_DOCUMENT_CHARS)

    def test_the_worst_case_document_still_encodes_as_one_record(self):
        # Every character a backslash, which is the escape that doubles.
        worst = Snapshot(1, 0, MAX_DOCUMENT_CHARS, "\\" * MAX_DOCUMENT_CHARS)
        record = encode_record(0, worst)
        self.assertLessEqual(len(record), MAX_RECORD_BYTES)
        self.assertEqual(decode_record(record[:-1])[1], worst)


class LongDocumentTests(unittest.TestCase):
    """Documents far longer than the pre-V1.4 32-line, 512-character bound."""

    def setUp(self):
        self.editor = MultilineEditor()

    def test_a_document_far_longer_than_thirty_two_lines_is_accepted(self):
        type_text(self.editor, "\n".join("line %d" % n for n in range(200)))
        self.assertEqual(len(self.editor.lines), 200)
        self.assertGreater(len(self.editor.lines), 32)
        self.assertEqual(self.editor.lines[199], "line 199")

    def test_a_document_far_longer_than_five_hundred_characters_is_accepted(self):
        text = prose(4000)
        type_text(self.editor, text)
        self.assertEqual(self.editor.text, text)
        self.assertGreater(self.editor.character_count(), 512 * 4)

    def test_a_full_length_document_can_be_typed_one_event_at_a_time(self):
        # Through ``apply``, so every per-keystroke bound check runs at every
        # length rather than the whole document being installed at once.
        text = prose(MAX_DOCUMENT_CHARS - len(PARAGRAPH))
        type_text(self.editor, text)
        self.assertEqual(self.editor.text, text)
        self.assertEqual(self.editor.document_revision, len(text))

    def test_a_long_document_lays_out_into_far_more_rows_than_the_panel(self):
        type_text(self.editor, prose(4000))
        rows = self.editor.visual_rows()
        self.assertGreater(len(rows), VIEWPORT_ROWS * 20)

    def test_every_visual_row_of_a_long_document_fits_the_panel_width(self):
        type_text(self.editor, prose(4000))
        layout = self.editor.layout
        for logical_row, start, end in self.editor.visual_rows():
            self.assertLessEqual(end - start, layout.width)

    def test_a_long_document_round_trips_through_the_recovery_record(self):
        text = prose(MAX_DOCUMENT_CHARS - len(PARAGRAPH))
        type_text(self.editor, text)
        snapshot = Snapshot(
            self.editor.document_revision, self.editor.row, self.editor.column,
            self.editor.text,
        )
        record = encode_record(7, snapshot)
        sequence, decoded = decode_record(record[:-1])
        self.assertEqual(sequence, 7)
        self.assertEqual(decoded.text, text)

    def test_a_long_document_survives_a_checkpoint_and_comes_back(self):
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root="/sd/magwrite")
        store.open()
        text = prose(MAX_DOCUMENT_CHARS - len(PARAGRAPH))
        type_text(self.editor, text)
        snapshot = Snapshot(
            self.editor.document_revision, self.editor.row, self.editor.column,
            self.editor.text,
        )
        self.assertTrue(store.checkpoint(snapshot))
        reopened = DocumentStore(filesystem, root="/sd/magwrite")
        recovery = reopened.open()
        self.assertTrue(recovery.recovered)
        self.assertEqual(recovery.snapshot.text, text)

    def test_a_long_document_still_produces_a_bounded_viewport_payload(self):
        # The whole reason a long document is affordable: what crosses the UART
        # is a window, and a window is the same size whatever is behind it.
        type_text(self.editor, prose(4000))
        payload = EditorViewport(layout=self.editor.layout).payload(self.editor, 6)
        self.assertLessEqual(len(payload), MAX_PAYLOAD_SIZE)
        message = ViewportMessage.decode(self.editor.viewport_revision, payload)
        self.assertLessEqual(len(message.lines), MAX_VIEWPORT_LINES)


class ScrollingTests(unittest.TestCase):
    """The window at the beginning, the middle, and the end of a long document."""

    def setUp(self):
        self.editor = MultilineEditor()
        type_text(self.editor, prose(4000))
        self.layout = self.editor.layout
        self.rows = self.editor.visual_rows()

    def cursor_index(self):
        return self.editor.cursor_visual_position()[0]

    def window(self):
        return self.layout.window(
            self.editor.lines, self.editor.row, self.editor.column
        )

    def go_to_start(self):
        while self.editor.row or self.editor.column:
            self.editor.apply(event(LEFT))

    def go_to_end(self):
        self.editor.row = len(self.editor.lines) - 1
        self.editor.column = len(self.editor.lines[-1])
        self.editor.preferred_column = self.editor.cursor_visual_position()[1]

    # ------------------------------------------------------------- beginning

    def test_at_the_beginning_the_window_starts_at_the_top(self):
        self.go_to_start()
        window = self.window()
        self.assertEqual(window["top"], 0)
        self.assertEqual(window["cursor_row"], 0)
        self.assertFalse(window["more_above"])
        self.assertTrue(window["more_below"])

    def test_moving_up_at_the_beginning_does_not_move_the_window(self):
        self.go_to_start()
        for _ in range(5):
            self.editor.apply(event(UP))
        self.assertEqual(self.window()["top"], 0)
        self.assertEqual(self.editor.row, 0)

    def test_the_first_screenful_scrolls_only_once_the_cursor_would_leave_it(self):
        self.go_to_start()
        for step in range(VIEWPORT_ROWS - 1):
            self.editor.apply(event(DOWN))
            self.assertEqual(self.window()["top"], 0)
            self.assertEqual(self.window()["cursor_row"], step + 1)
        self.editor.apply(event(DOWN))
        self.assertEqual(self.window()["top"], 1)

    # ----------------------------------------------------------------- middle

    def test_in_the_middle_the_cursor_rides_the_last_visible_row(self):
        self.go_to_start()
        target = len(self.rows) // 2
        for _ in range(target):
            self.editor.apply(event(DOWN))
        window = self.window()
        self.assertEqual(window["cursor_row"], VIEWPORT_ROWS - 1)
        self.assertEqual(window["top"], target - VIEWPORT_ROWS + 1)
        self.assertTrue(window["more_above"])
        self.assertTrue(window["more_below"])

    def test_the_window_in_the_middle_is_the_rows_the_layout_says_it_is(self):
        self.go_to_start()
        for _ in range(len(self.rows) // 2):
            self.editor.apply(event(DOWN))
        window = self.window()
        expected = tuple(
            self.editor.lines[row][start:end]
            for row, start, end in self.rows[
                window["top"] : window["top"] + VIEWPORT_ROWS
            ]
        )
        self.assertEqual(window["lines"], expected)

    def test_scrolling_down_then_back_up_returns_the_same_window(self):
        # The window is a pure function of the cursor, never of history, so a
        # round trip has to be exact rather than merely close.
        self.go_to_start()
        for _ in range(len(self.rows) // 2):
            self.editor.apply(event(DOWN))
        middle = self.window()
        for _ in range(20):
            self.editor.apply(event(DOWN))
        for _ in range(20):
            self.editor.apply(event(UP))
        self.assertEqual(self.window(), middle)

    # -------------------------------------------------------------------- end

    def test_at_the_end_the_last_row_is_visible_and_nothing_is_below(self):
        self.go_to_end()
        window = self.window()
        self.assertFalse(window["more_below"])
        self.assertTrue(window["more_above"])
        self.assertEqual(
            window["top"] + window["cursor_row"], len(self.rows) - 1
        )

    def test_moving_down_at_the_end_does_not_move_the_window(self):
        self.go_to_end()
        window = self.window()
        for _ in range(5):
            self.editor.apply(event(DOWN))
        self.assertEqual(self.window(), window)

    def test_the_window_never_runs_past_the_end_of_the_document(self):
        self.go_to_start()
        for _ in range(len(self.rows) + 10):
            self.editor.apply(event(DOWN))
            window = self.window()
            self.assertLessEqual(
                window["top"] + len(window["lines"]), window["total_rows"]
            )
            self.assertLessEqual(len(window["lines"]), VIEWPORT_ROWS)

    def test_the_cursor_is_visible_at_every_row_of_a_long_document(self):
        # The one property scrolling exists to provide, asserted at every row
        # rather than at three chosen ones.
        self.go_to_start()
        for _ in range(len(self.rows) + 5):
            window = self.window()
            self.assertTrue(0 <= window["cursor_row"] < len(window["lines"]))
            self.editor.apply(event(DOWN))

    def test_typing_at_the_end_of_a_long_document_keeps_the_cursor_on_screen(self):
        self.go_to_end()
        type_text(self.editor, " and one more sentence to push the window along.")
        window = self.window()
        self.assertTrue(0 <= window["cursor_row"] < len(window["lines"]))
        self.assertFalse(window["more_below"])


class EditingNearTheLimitTests(unittest.TestCase):
    """The last character that fits and the first that does not."""

    def fill_to(self, remaining):
        """Return an editor holding a document ``remaining`` characters short."""
        editor = MultilineEditor()
        target = MAX_DOCUMENT_CHARS - remaining
        # Paragraph-shaped rather than one enormous line, so the line bound is
        # not what is being tested here.
        while editor.character_count() < target:
            room = target - editor.character_count()
            if room > MAX_LINE_CHARS:
                type_text(editor, "x" * MAX_LINE_CHARS)
                editor.apply(event(ENTER))
            else:
                type_text(editor, "x" * room)
        self.assertEqual(editor.character_count(), target)
        return editor

    def test_the_last_character_that_fits_is_accepted(self):
        editor = self.fill_to(1)
        editor.apply(event(CHAR, "z"))
        self.assertEqual(editor.character_count(), MAX_DOCUMENT_CHARS)

    def test_editing_continues_normally_one_character_from_the_limit(self):
        editor = self.fill_to(1)
        before = editor.text
        editor.apply(event(LEFT))
        editor.apply(event(RIGHT))
        editor.apply(event(BACKSPACE))
        editor.apply(event(CHAR, "y"))
        editor.apply(event(CHAR, "z"))
        self.assertEqual(editor.character_count(), MAX_DOCUMENT_CHARS)
        self.assertEqual(editor.text, before[:-1] + "yz")

    def test_backspace_at_the_limit_makes_room_for_another_character(self):
        # The limit must be a wall, not a trap: a full document is still an
        # editable one.
        editor = self.fill_to(0)
        editor.apply(event(BACKSPACE))
        editor.apply(event(CHAR, "q"))
        self.assertEqual(editor.character_count(), MAX_DOCUMENT_CHARS)
        self.assertEqual(editor.lines[-1][-1], "q")

    def test_cursor_movement_at_the_limit_is_never_refused(self):
        editor = self.fill_to(0)
        for kind in (LEFT, RIGHT, UP, DOWN):
            for _ in range(3):
                editor.apply(event(kind))
        self.assertEqual(editor.rejected_events, 0)

    def test_a_full_document_still_lays_out_and_encodes(self):
        editor = self.fill_to(0)
        payload = EditorViewport(layout=editor.layout).payload(editor, 6)
        self.assertLessEqual(len(payload), MAX_PAYLOAD_SIZE)

    def test_a_full_document_still_journals(self):
        editor = self.fill_to(0)
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root="/sd/magwrite")
        store.open()
        self.assertTrue(store.journal(
            Snapshot(editor.document_revision, editor.row, editor.column,
                     editor.text)
        ))
        self.assertEqual(store.read_latest().text, editor.text)


class CleanRefusalTests(unittest.TestCase):
    """The refusal at the real limit: explicit, counted, and lossless."""

    def full_editor(self):
        editor = MultilineEditor()
        while editor.character_count() < MAX_DOCUMENT_CHARS:
            room = MAX_DOCUMENT_CHARS - editor.character_count()
            if room > MAX_LINE_CHARS:
                type_text(editor, "x" * MAX_LINE_CHARS)
                editor.apply(event(ENTER))
            else:
                type_text(editor, "x" * room)
        return editor

    def assert_unchanged(self, editor, action):
        """Run ``action``, expect a refusal, and prove nothing at all moved."""
        text = editor.text
        row, column = editor.row, editor.column
        document_revision = editor.document_revision
        viewport_revision = editor.viewport_revision
        rejected = editor.rejected_events
        with self.assertRaises(EditRejected):
            action()
        self.assertEqual(editor.text, text)
        self.assertEqual(editor.row, row)
        self.assertEqual(editor.column, column)
        self.assertEqual(editor.document_revision, document_revision)
        self.assertEqual(editor.viewport_revision, viewport_revision)
        self.assertEqual(editor.rejected_events, rejected + 1)

    def test_the_character_after_the_last_one_is_refused_without_loss(self):
        editor = self.full_editor()
        self.assert_unchanged(editor, lambda: editor.apply(event(CHAR, "z")))

    def test_enter_at_the_document_limit_is_refused_without_loss(self):
        editor = self.full_editor()
        self.assert_unchanged(editor, lambda: editor.apply(event(ENTER)))

    def test_the_line_limit_is_refused_without_loss(self):
        editor = MultilineEditor()
        type_text(editor, "x" * MAX_LINE_CHARS)
        self.assert_unchanged(editor, lambda: editor.apply(event(CHAR, "z")))

    def test_the_line_count_limit_is_refused_without_loss(self):
        editor = MultilineEditor()
        for _ in range(MAX_DOCUMENT_LINES - 1):
            editor.apply(event(ENTER))
        self.assertEqual(len(editor.lines), MAX_DOCUMENT_LINES)
        self.assert_unchanged(editor, lambda: editor.apply(event(ENTER)))

    def test_a_join_that_would_exceed_the_line_limit_is_refused_without_loss(self):
        editor = MultilineEditor()
        type_text(editor, "x" * MAX_LINE_CHARS)
        editor.apply(event(ENTER))
        type_text(editor, "y" * 10)
        while editor.column:
            editor.apply(event(LEFT))
        self.assert_unchanged(editor, lambda: editor.apply(event(BACKSPACE)))

    def test_the_refusal_names_which_bound_was_reached(self):
        # The reason reaches the writer on a shell error screen, so it has to say
        # something true and specific rather than "rejected".
        editor = self.full_editor()
        try:
            editor.apply(event(CHAR, "z"))
        except EditRejected as error:
            self.assertIn("capacity", str(error))
        else:
            self.fail("the document limit was not enforced")

    def test_a_refused_document_is_still_journalled_and_recovered_intact(self):
        # The point of "without data loss": after the refusal the writer's work
        # is still exactly what it was and still reaches the card.
        editor = self.full_editor()
        with self.assertRaises(EditRejected):
            editor.apply(event(CHAR, "z"))
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root="/sd/magwrite")
        store.open()
        store.checkpoint(Snapshot(
            editor.document_revision, editor.row, editor.column, editor.text
        ))
        reopened = DocumentStore(filesystem, root="/sd/magwrite")
        recovered = reopened.open().snapshot
        self.assertEqual(recovered.text, editor.text)
        self.assertEqual(len(recovered.text.replace("\n", "")) + recovered.text.count("\n"),
                         MAX_DOCUMENT_CHARS)

    def test_a_stored_document_over_the_limit_is_refused_rather_than_loaded(self):
        # A card is not trusted input. This is the case that would otherwise put
        # the editor into a state no sequence of edits could produce.
        editor = MultilineEditor()
        oversized = "x" * (MAX_DOCUMENT_CHARS + 1)
        with self.assertRaises(EditRejected):
            editor.load(oversized)
        self.assertEqual(editor.text, "")

    def test_a_refusal_leaves_the_editor_usable(self):
        editor = self.full_editor()
        with self.assertRaises(EditRejected):
            editor.apply(event(CHAR, "z"))
        editor.apply(event(BACKSPACE))
        editor.apply(event(CHAR, "!"))
        self.assertEqual(editor.character_count(), MAX_DOCUMENT_CHARS)
        self.assertEqual(editor.lines[-1][-1], "!")


class LayoutCostTests(unittest.TestCase):
    """A long document must not need a different architecture to be laid out."""

    def test_layout_is_a_pure_function_at_full_length(self):
        editor = MultilineEditor()
        type_text(editor, prose(MAX_DOCUMENT_CHARS - len(PARAGRAPH)))
        layout = Layout()
        first = layout.rows(editor.lines)
        second = layout.rows(editor.lines)
        self.assertEqual(first, second)

    def test_the_window_reads_a_bounded_number_of_rows_however_long_it_is(self):
        # The property that makes the bound affordable: what is built per frame
        # is the panel's five rows, not the document.
        for target in (200, 2000, MAX_DOCUMENT_CHARS - len(PARAGRAPH)):
            editor = MultilineEditor()
            type_text(editor, prose(target))
            window = Layout().window(editor.lines, editor.row, editor.column)
            self.assertLessEqual(len(window["lines"]), VIEWPORT_ROWS)


if __name__ == "__main__":
    unittest.main()
