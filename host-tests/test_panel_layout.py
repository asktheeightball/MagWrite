"""The panel's font, its derived geometry, and the button footer. V1.7.

Three families of failure, and each is caught where it is cheapest.

* **The font.** The UI draws with ``terminalio.FONT`` and nothing else. On a
  board that is a firmware import; on the host there is no ``terminalio`` at all,
  so ``magwrite.font`` falls back to a metrics-only stand-in that carries no
  letterforms. These tests assert the fallback is *only* a fallback, that the
  stand-in reports the same cell the real font does, and that a character with no
  glyph is refused rather than silently drawn as a hole in a word.
* **The geometry.** Nothing about the layout is written down. The row pitch, the
  row count, and the column count are derived from the bounding box the font
  reports, so these assert the derivation -- that every row is on the panel, that
  the body never reaches the footer band, and that the cursor underline sits in
  the leading rather than on top of the row below.
* **The two boards agreeing.** The MagTag derives ``(columns, rows)`` from its
  font; the Fruit Jam wraps to constants in ``editor_layout``. They share no
  import by design, so a layout change on one board and not the other is exactly
  the kind of silent disagreement a host test has to catch. It is the same
  argument the button action tables get, and it is here for the same reason.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))

import config as magtag_config

from magwrite import font as font_module
from magwrite.button_footer import (
    ARROW_HEIGHT, ARROW_WIDTH, FOOTER_ACTIONS, LABELS, button_centres,
    draw_footer,
)
from magwrite.buttons import ACTIONS, DOWN, MENU, SELECT, UP
from magwrite.font import (
    PRINTABLE_ASCII, draw_text, is_builtin_font, metrics, missing_glyphs,
    text_width,
)
from magwrite.mono_canvas import MonoCanvas
from magwrite.startup_screens import fault_screen, starting_screen, waiting_screen
from magwrite.viewport_message import MAX_LINE_CHARS, MAX_LINES, ViewportMessage
from magwrite.viewport_renderer import (
    BODY_SCALE, CURSOR_HEIGHT, LEADING, MARGIN_X, PANEL_HEIGHT, PANEL_WIDTH,
    capacity, geometry, render_viewport,
)
from magwrite_transport.editor_layout import VIEWPORT_COLUMNS, VIEWPORT_ROWS
from magwrite_transport import shell_viewport


def ink_columns(buffer):
    """The landscape x of every column carrying at least one set pixel."""
    canvas = MonoCanvas()
    canvas.buf[:] = buffer
    columns = set()
    for x in range(PANEL_WIDTH):
        for y in range(PANEL_HEIGHT):
            index = (295 - x) * canvas.stride + (y >> 3)
            if not canvas.buf[index] & (0x80 >> (y & 7)):
                columns.add(x)
                break
    return columns


def ink_rows(buffer):
    """The landscape y of every row carrying at least one set pixel."""
    canvas = MonoCanvas()
    canvas.buf[:] = buffer
    rows = set()
    for y in range(PANEL_HEIGHT):
        for x in range(PANEL_WIDTH):
            index = (295 - x) * canvas.stride + (y >> 3)
            if not canvas.buf[index] & (0x80 >> (y & 7)):
                rows.add(y)
                break
    return rows


class FontTests(unittest.TestCase):
    def test_the_device_font_is_the_firmware_built_in_font(self):
        # The whole point of the change. On CPython there is no terminalio, so
        # this asserts the resolution rule rather than the result: the built-in
        # font is used whenever it exists, and the stand-in only when it does not.
        try:
            import terminalio
        except ImportError:
            terminalio = None
        if terminalio is None:
            self.assertFalse(is_builtin_font())
        else:
            self.assertTrue(is_builtin_font())
            self.assertIs(font_module.FONT, terminalio.FONT)

    def test_the_scale_is_native(self):
        self.assertEqual(font_module.NATIVE_SCALE, 1)
        self.assertEqual(BODY_SCALE, 1)

    def test_the_cell_is_the_font_s_own_bounding_box(self):
        self.assertEqual(metrics(), tuple(font_module.FONT.get_bounding_box()[:2]))

    def test_the_built_in_font_is_six_by_twelve(self):
        # Terminus at 12 px. Asserted because every derived number below follows
        # from it, so a firmware that shipped a different built-in font would
        # change the panel's capacity and should say so here first.
        self.assertEqual(metrics(), (6, 12))

    def test_every_character_either_board_may_draw_has_a_glyph(self):
        self.assertEqual(missing_glyphs(), ())

    def test_printable_ascii_is_exactly_the_printable_ascii_range(self):
        self.assertEqual(len(PRINTABLE_ASCII), 0x7F - 0x20)
        self.assertEqual(PRINTABLE_ASCII[0], " ")
        self.assertEqual(PRINTABLE_ASCII[-1], "~")

    def test_a_character_with_no_glyph_is_refused_rather_than_drawn(self):
        with self.assertRaises(ValueError):
            draw_text(MonoCanvas(), "é", 0, 0)

    def test_text_width_is_monospace(self):
        cell = metrics()[0]
        self.assertEqual(text_width(""), 0)
        self.assertEqual(text_width("MENU"), 4 * cell)
        self.assertEqual(text_width("MENU", 2), 8 * cell)

    def test_drawing_advances_by_one_cell_a_character(self):
        canvas = MonoCanvas()
        end = draw_text(canvas, "ABC", 10, 10)
        self.assertEqual(end, 10 + 3 * metrics()[0])

    def test_a_space_leaves_the_panel_alone(self):
        canvas = MonoCanvas()
        draw_text(canvas, "   ", 10, 10)
        self.assertEqual(ink_rows(canvas.buf), set())

    def test_a_letter_does_not(self):
        canvas = MonoCanvas()
        draw_text(canvas, "A", 10, 10)
        self.assertNotEqual(ink_rows(canvas.buf), set())

    def test_the_glyph_cache_cannot_grow_past_the_alphabet(self):
        # Every character outside PRINTABLE_ASCII raises before it is cached, so
        # the cache is bounded by the alphabet however long a session runs.
        canvas = MonoCanvas()
        draw_text(canvas, "".join(PRINTABLE_ASCII), 0, 0)
        for character in ("é", "↑", "\x00"):
            try:
                draw_text(canvas, character, 0, 0)
            except ValueError:
                pass
        self.assertLessEqual(len(font_module._ROWS), len(PRINTABLE_ASCII))

    def test_the_glyph_cache_is_discarded_when_the_font_changes(self):
        canvas = MonoCanvas()
        draw_text(canvas, "A", 0, 0)
        other = font_module._HostMetricsFont(width=8, height=16)
        draw_text(canvas, "A", 0, 0, 1, other)
        self.assertIs(font_module._ROWS_FONT, other)
        self.assertEqual(len(font_module._glyph_rows(other, "A")), 16)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.box = geometry()

    def test_the_panel_holds_forty_eight_columns_by_six_rows(self):
        self.assertEqual(capacity(), (48, 6))

    def test_the_column_count_is_the_usable_width_over_the_cell(self):
        self.assertEqual(
            self.box["columns"],
            (PANEL_WIDTH - 2 * MARGIN_X) // self.box["cell_width"],
        )

    def test_the_row_pitch_is_the_cell_plus_the_leading(self):
        self.assertEqual(
            self.box["row_pitch"], self.box["cell_height"] + LEADING)

    def test_a_full_row_of_text_fits_the_panel_width(self):
        self.assertLessEqual(
            MARGIN_X + text_width("W" * self.box["columns"]),
            PANEL_WIDTH - MARGIN_X,
        )

    def test_one_more_column_would_not(self):
        self.assertGreater(
            MARGIN_X + text_width("W" * (self.box["columns"] + 1)),
            PANEL_WIDTH - MARGIN_X,
        )

    def test_the_last_body_row_and_its_cursor_clear_the_footer_rule(self):
        last = (
            self.box["first_row_y"]
            + (self.box["rows"] - 1) * self.box["row_pitch"]
        )
        bottom = last + self.box["cell_height"] + CURSOR_HEIGHT
        self.assertLess(bottom, self.box["footer_rule_y"])

    def test_one_more_row_would_not(self):
        extra = (
            self.box["first_row_y"] + self.box["rows"] * self.box["row_pitch"]
            + self.box["cell_height"]
        )
        self.assertGreaterEqual(extra, self.box["footer_rule_y"])

    def test_the_cursor_underline_sits_in_the_leading_not_on_the_next_row(self):
        self.assertLessEqual(CURSOR_HEIGHT, LEADING)

    def test_the_footer_ends_on_the_panel(self):
        self.assertLess(
            self.box["footer_y"] + self.box["cell_height"], PANEL_HEIGHT)

    def test_the_header_clears_the_first_body_row(self):
        self.assertLess(
            self.box["header_y"] + self.box["cell_height"],
            self.box["header_rule_y"],
        )
        self.assertLess(self.box["header_rule_y"], self.box["first_row_y"])


class BoardAgreementTests(unittest.TestCase):
    """The two boards share no import, so this is what keeps them equal."""

    def test_the_fruit_jam_wraps_to_the_capacity_the_magtag_derives(self):
        self.assertEqual(capacity(), (VIEWPORT_COLUMNS, VIEWPORT_ROWS))

    def test_the_viewport_message_bounds_are_that_same_capacity(self):
        self.assertEqual((MAX_LINE_CHARS, MAX_LINES), capacity())

    def test_the_shell_screens_use_that_same_capacity(self):
        self.assertEqual(
            (shell_viewport.MAX_LINE_CHARS, shell_viewport.MAX_LINES),
            capacity(),
        )

    def test_the_widest_possible_frame_still_fits_the_protocol_payload(self):
        from magwrite.uart_protocol import MAX_PAYLOAD_SIZE

        columns, rows = capacity()
        message = ViewportMessage(
            1, 1, "T" * 20, ("W" * columns,) * rows, 0, columns, "S" * 20)
        self.assertLessEqual(len(message.encode()), MAX_PAYLOAD_SIZE)


class FooterTests(unittest.TestCase):
    def setUp(self):
        self.box = geometry()

    def test_the_footer_labels_the_four_actions_the_board_can_send(self):
        self.assertEqual(set(FOOTER_ACTIONS), set(ACTIONS))
        self.assertEqual(len(FOOTER_ACTIONS), len(ACTIONS))

    def test_the_footer_order_is_the_config_pin_order(self):
        # Left to right on the panel must be left to right on the bezel, and the
        # bezel order is the one config names. Reverse FOOTER_ACTIONS if a
        # physical check ever shows the labels the other way round.
        aliases = (
            magtag_config.BUTTON_MENU_PIN_ALIAS,
            magtag_config.BUTTON_UP_PIN_ALIAS,
            magtag_config.BUTTON_DOWN_PIN_ALIAS,
            magtag_config.BUTTON_SELECT_PIN_ALIAS,
        )
        self.assertEqual(aliases, ("BUTTON_A", "BUTTON_B", "BUTTON_C", "BUTTON_D"))
        self.assertEqual(FOOTER_ACTIONS, (MENU, UP, DOWN, SELECT))

    def test_the_two_word_labels_are_the_two_outer_buttons(self):
        self.assertEqual(set(LABELS), {MENU, SELECT})
        self.assertEqual(LABELS[MENU], "MENU")
        self.assertEqual(LABELS[SELECT], "SELECT")

    def test_the_centres_are_the_four_quarter_centres_of_the_panel(self):
        self.assertEqual(button_centres(), (37, 111, 185, 259))

    def test_every_label_fits_between_its_neighbours(self):
        centres = button_centres()
        for index, action in enumerate(FOOTER_ACTIONS):
            label = LABELS.get(action)
            width = ARROW_WIDTH if label is None else text_width(label)
            left = centres[index] - width // 2
            right = left + width
            self.assertGreaterEqual(left, MARGIN_X, action)
            self.assertLessEqual(right, PANEL_WIDTH - MARGIN_X, action)
            if index:
                previous = LABELS.get(FOOTER_ACTIONS[index - 1])
                previous_width = (
                    ARROW_WIDTH if previous is None else text_width(previous))
                self.assertGreater(
                    left, centres[index - 1] + previous_width // 2, action)

    def test_the_footer_stays_inside_its_own_band(self):
        canvas = MonoCanvas()
        draw_footer(canvas, self.box["footer_y"])
        rows = ink_rows(canvas.buf)
        self.assertTrue(rows)
        self.assertGreaterEqual(min(rows), self.box["footer_y"])
        self.assertLess(
            max(rows), self.box["footer_y"] + self.box["cell_height"])

    def test_the_arrows_are_drawn_and_are_not_letters(self):
        # Two arrows, each a solid triangle over a stem, and nothing from the
        # font: an arrow drawn as "^" or "v" is a caret and a letter.
        canvas = MonoCanvas()
        draw_footer(canvas, self.box["footer_y"])
        columns = ink_columns(canvas.buf)
        for centre in button_centres()[1:3]:
            self.assertIn(centre, columns)
            for offset in range(-(ARROW_WIDTH // 2), ARROW_WIDTH // 2 + 1):
                self.assertIn(centre + offset, columns)

    def test_the_arrow_fits_the_text_cell_it_is_centred_in(self):
        self.assertLessEqual(ARROW_HEIGHT, self.box["cell_height"])


class EveryScreenTests(unittest.TestCase):
    """The footer is on every screen, and no screen draws over it."""

    def screens(self):
        columns, rows = capacity()
        yield "startup", starting_screen()
        yield "waiting", waiting_screen()
        yield "fault", fault_screen("UART TX PIN A1 IN USE")
        yield "editor", ViewportMessage(
            7, 1, "MAGWRITE L01 C00", ("a real note, typed by hand",), 0, 26,
            "D001 V001 R01/01 s")
        yield "menu", ViewportMessage(
            1, 7, "MAGWRITE MENU",
            ("> JOURNAL", "  QUICK NOTE", "  DRAFTS", "  RECENT"), 0, 0,
            "MENU 1/4 s")
        yield "error", ViewportMessage(
            1, 7, "MAGWRITE ERROR", ("STORE UNUSABLE", "WORK IS KEPT"), 0, 0,
            "ERROR !")
        yield "full", ViewportMessage(
            1, 7, "T" * 20, ("W" * columns,) * rows, rows - 1, columns,
            "S" * 20)

    def test_every_screen_renders(self):
        for name, screen in self.screens():
            self.assertEqual(
                len(render_viewport(screen)), PANEL_WIDTH * PANEL_HEIGHT // 8,
                name,
            )

    def test_every_screen_carries_the_footer(self):
        box = geometry()
        bare = MonoCanvas()
        draw_footer(bare, box["footer_y"])
        expected = ink_columns(bare.buf)
        for name, screen in self.screens():
            drawn = ink_columns(render_viewport(screen))
            self.assertEqual(expected - drawn, set(), name)

    def test_no_screen_draws_between_the_body_and_the_footer(self):
        # Including the one that fills every row to the last column, which is
        # the case that would overlap if the row count were wrong.
        box = geometry()
        for name, screen in self.screens():
            rows = ink_rows(render_viewport(screen))
            gap = set(range(box["footer_rule_y"] + 1, box["footer_y"]))
            self.assertEqual(rows & gap, set(), name)

    def test_the_footer_is_identical_on_every_screen(self):
        # It carries no state, so a partial refresh never has to redraw it and
        # two screens can never disagree about the bezel.
        box = geometry()
        band = set(range(box["footer_y"], PANEL_HEIGHT))
        signatures = set()
        for _name, screen in self.screens():
            buffer = render_viewport(screen)
            canvas = MonoCanvas()
            canvas.buf[:] = buffer
            marks = []
            for y in sorted(band):
                for x in range(PANEL_WIDTH):
                    index = (295 - x) * canvas.stride + (y >> 3)
                    if not canvas.buf[index] & (0x80 >> (y & 7)):
                        marks.append((x, y))
            signatures.add(tuple(marks))
        self.assertEqual(len(signatures), 1)


if __name__ == "__main__":
    unittest.main()
