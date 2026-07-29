"""Render a semantic viewport without interpreting its text.

Geometry only. The MagTag draws exactly the lines it was given, at fixed cells,
and never wraps, scrolls, or re-measures them.

The 296x128 landscape panel is divided into a scale-1 header, a rule, five
scale-2 body rows on a 16 px pitch, and a closing rule:

    y=7    title (scale 1) and right-aligned status (scale 1)
    y=20   header rule
    y=24   body row 0        (glyph height 10, cursor underline at y+12)
    y=40   body row 1
    y=56   body row 2
    y=72   body row 3
    y=88   body row 4        (underline ends at y=102)
    y=108  footer rule
"""

from magwrite.mono_canvas import MonoCanvas
from magwrite.test_pattern import draw_text, landscape_rect

LEFT_MARGIN = 9
RIGHT_EDGE = 289
HEADER_Y = 7
HEADER_RULE_Y = 20
FIRST_ROW_Y = 24
ROW_PITCH = 16
BODY_SCALE = 2
CELL_WIDTH = 4 * BODY_SCALE
CURSOR_OFFSET_Y = 12
CURSOR_WIDTH = CELL_WIDTH - 1
CURSOR_HEIGHT = 2
FOOTER_RULE_Y = 108
HEADER_CELL_WIDTH = 4


def render_viewport(viewport):
    canvas = MonoCanvas()
    draw_text(canvas, viewport.title, 8, HEADER_Y, 1)
    status_x = RIGHT_EDGE - len(viewport.status) * HEADER_CELL_WIDTH
    if status_x < 8 + len(viewport.title) * HEADER_CELL_WIDTH:
        raise ValueError("viewport header does not fit the panel")
    draw_text(canvas, viewport.status, status_x, HEADER_Y, 1)
    landscape_rect(canvas, 7, HEADER_RULE_Y, 282, 1, 1)
    for row, line in enumerate(viewport.lines):
        draw_text(canvas, line, LEFT_MARGIN, FIRST_ROW_Y + row * ROW_PITCH, BODY_SCALE)
    cursor_x = LEFT_MARGIN + viewport.cursor_column * CELL_WIDTH
    cursor_y = FIRST_ROW_Y + viewport.cursor_row * ROW_PITCH + CURSOR_OFFSET_Y
    landscape_rect(canvas, cursor_x, cursor_y, CURSOR_WIDTH, CURSOR_HEIGHT, 1)
    landscape_rect(canvas, 7, FOOTER_RULE_Y, 282, 1, 1)
    return canvas.buf
