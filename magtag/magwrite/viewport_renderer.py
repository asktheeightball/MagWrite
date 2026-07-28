"""Render a semantic viewport without interpreting its text."""

from magwrite.mono_canvas import MonoCanvas
from magwrite.test_pattern import draw_text, landscape_rect


def render_viewport(viewport):
    canvas = MonoCanvas()
    draw_text(canvas, viewport.title, 8, 7, 1)
    draw_text(canvas, viewport.status, 220, 7, 1)
    landscape_rect(canvas, 7, 20, 282, 1, 1)
    for row, line in enumerate(viewport.lines):
        draw_text(canvas, line, 9, 31 + row * 25, 2)
    cursor_x = 9 + viewport.cursor_column * 8
    cursor_y = 43 + viewport.cursor_row * 25
    landscape_rect(canvas, cursor_x, cursor_y, 7, 2, 1)
    landscape_rect(canvas, 7, 108, 282, 1, 1)
    return canvas.buf
