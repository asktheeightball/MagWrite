"""Render a semantic viewport without interpreting its text.

Geometry only. The MagTag draws exactly the lines it was given, at fixed cells,
and never wraps, scrolls, or re-measures them.

The font is ``terminalio.FONT`` at native scale 1 -- see ``magwrite/font.py`` --
and every number below is derived from the bounding box that font reports rather
than written down. With the 6x12 built-in font the 296x128 landscape panel comes
out as:

    y=2     title and right-aligned status      (one 12 px cell)
    y=16    header rule
    y=19    body row 0    (12 px cell, cursor underline in the 2 px leading)
    y=33    body row 1
    y=47    body row 2
    y=61    body row 3
    y=75    body row 4
    y=89    body row 5    (underline ends at y=102)
    y=112   footer rule
    y=115   button footer                       (one 12 px cell, ends at y=126)

which is **48 columns by 6 rows**, against the 28 by 5 the hand-drawn 3x5 table
managed at scale 2 -- the same 6 px advance, so the same apparent size, with the
panel's width actually used.

:func:`capacity` is the single source of that pair. The Fruit Jam wraps to the
same numbers from its own constants, because the two boards share no import; a
host test asserts the two agree, which is the check that would have caught a
layout change on one board and not the other.
"""

from magwrite.button_footer import draw_footer
from magwrite.font import NATIVE_SCALE, draw_text, metrics, text_width
from magwrite.mono_canvas import MonoCanvas, landscape_rect

PANEL_WIDTH = 296
PANEL_HEIGHT = 128

# Native. The built-in font's 6 px advance is exactly what the old table drew at
# scale 2, so this is the size the bench already read comfortably, and no
# integer multiple of it fits a usable number of rows on a 128 px panel.
BODY_SCALE = NATIVE_SCALE

MARGIN_X = 4
HEADER_TOP = 2
# Between a text cell and the rule under it, and between that rule and the next
# text cell. Small on purpose: this is a writing panel, not a form.
RULE_GAP = 2
# Between body rows. The cursor underline lives in it, so it is never dead space.
LEADING = 2
CURSOR_HEIGHT = 2


def _cell(scale=BODY_SCALE, font=None):
    width, height = metrics(font)
    return width * scale, height * scale


def geometry(scale=BODY_SCALE, font=None):
    """Every y coordinate the panel uses, derived from the font's own metrics."""
    cell_width, cell_height = _cell(scale, font)
    header_y = HEADER_TOP
    header_rule_y = header_y + cell_height + RULE_GAP
    first_row_y = header_rule_y + 1 + RULE_GAP
    footer_y = PANEL_HEIGHT - cell_height - 1
    footer_rule_y = footer_y - RULE_GAP - 1
    pitch = cell_height + LEADING
    rows = (footer_rule_y - first_row_y) // pitch
    if rows < 1:
        raise ValueError("the panel cannot fit one body row in this font")
    columns = (PANEL_WIDTH - 2 * MARGIN_X) // cell_width
    return {
        "cell_width": cell_width,
        "cell_height": cell_height,
        "header_y": header_y,
        "header_rule_y": header_rule_y,
        "first_row_y": first_row_y,
        "row_pitch": pitch,
        "rows": rows,
        "columns": columns,
        "footer_rule_y": footer_rule_y,
        "footer_y": footer_y,
        "rule_x": MARGIN_X,
        "rule_width": PANEL_WIDTH - 2 * MARGIN_X,
    }


def capacity(scale=BODY_SCALE, font=None):
    """``(columns, rows)`` this panel can draw. The Fruit Jam wraps to these."""
    box = geometry(scale, font)
    return box["columns"], box["rows"]


def render_viewport(viewport, scale=BODY_SCALE, font=None):
    canvas = MonoCanvas()
    box = geometry(scale, font)
    draw_text(canvas, viewport.title, MARGIN_X, box["header_y"], scale, font)
    status_x = (
        PANEL_WIDTH - MARGIN_X - text_width(viewport.status, scale, font)
    )
    if status_x < MARGIN_X + text_width(viewport.title, scale, font):
        raise ValueError("viewport header does not fit the panel")
    draw_text(canvas, viewport.status, status_x, box["header_y"], scale, font)
    landscape_rect(
        canvas, box["rule_x"], box["header_rule_y"], box["rule_width"], 1, 1)
    for row, line in enumerate(viewport.lines):
        draw_text(
            canvas, line, MARGIN_X,
            box["first_row_y"] + row * box["row_pitch"], scale, font,
        )
    cursor_x = MARGIN_X + viewport.cursor_column * box["cell_width"]
    cursor_y = (
        box["first_row_y"] + viewport.cursor_row * box["row_pitch"]
        + box["cell_height"]
    )
    landscape_rect(
        canvas, cursor_x, cursor_y, box["cell_width"] - 1, CURSOR_HEIGHT, 1)
    landscape_rect(
        canvas, box["rule_x"], box["footer_rule_y"], box["rule_width"], 1, 1)
    draw_footer(canvas, box["footer_y"], scale, PANEL_WIDTH, font)
    return canvas.buf
