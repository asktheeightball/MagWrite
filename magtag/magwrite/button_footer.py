"""The persistent strip that says what the four bezel buttons do.

The MagTag's four buttons have been the primary shell controls since V1.5, and
until now the panel never said so. A writer who had put the device down had to
remember which of four unlabelled buttons opened the menu and which one selected,
and the only place that mapping was written down was a table in ``HARDWARE.md``.
The footer is that table, printed above the buttons it describes, on every screen.

What it is allowed to know
--------------------------

Nothing. It draws four fixed labels for the four fixed normalized actions this
board already sends. It does not know what state the shell is in, whether an
action is available, or what it will do -- all of which the Fruit Jam owns -- so
the footer never changes, never disagrees with the shell, and costs no protocol.
That is also why it is not sent as viewport lines: a label the Fruit Jam had to
transmit on every frame would be four rows of payload spent saying the same thing
forever, and a chance for the two boards to disagree about the bezel.

Geometry
--------

Four labels, centred on the four quarter-centres of the panel's long axis, which
is where the four buttons sit. It is drawn below the body rows and below a rule,
in the same font at the same scale as everything else, and nothing else is drawn
in the band it occupies -- so it cannot overlap the document however long a line
is or however many rows the layout derives.

If a physical check ever shows the labels reversed with respect to the bezel,
:data:`FOOTER_ACTIONS` is the one line to reverse: it is the panel's left-to-right
order, and the action names themselves are fixed by the protocol.

The arrows
----------

``UP`` and ``DOWN`` are drawn as filled triangles from display primitives rather
than set as text. The built-in font has no arrow glyph in the ASCII range both
boards restrict themselves to, and ``^`` and ``v`` are a caret and a letter --
readable as arrows only by someone already told they are arrows. A triangle is
the thing itself, costs nine rectangles, and reads at arm's length on e-paper.
"""

from magwrite.buttons import DOWN, MENU, SELECT, UP
from magwrite.font import draw_text, metrics, text_width
from magwrite.mono_canvas import landscape_rect

# Left to right across the panel, against the bezel. Mirrors the pin order in
# magtag/config.py -- A MENU, B UP, C DOWN, D SELECT -- and a host test asserts
# these are exactly the actions ``magwrite.buttons`` can send.
FOOTER_ACTIONS = (MENU, UP, DOWN, SELECT)

# Text for the two that are words; the other two are drawn.
LABELS = {MENU: "MENU", SELECT: "SELECT"}
ARROWS = {UP: "up", DOWN: "down"}

# A nine-pixel triangle over a three-pixel stem. Odd widths so both centre
# exactly on a button.
ARROW_WIDTH = 9
ARROW_HEAD_HEIGHT = 5
ARROW_STEM_WIDTH = 3
ARROW_STEM_HEIGHT = 4
ARROW_HEIGHT = ARROW_HEAD_HEIGHT + ARROW_STEM_HEIGHT


def button_centres(panel_width=296, count=None):
    """The x centre of each button, evenly across the panel's long axis."""
    count = len(FOOTER_ACTIONS) if count is None else count
    return tuple(
        panel_width * (2 * index + 1) // (2 * count) for index in range(count)
    )


def draw_arrow(canvas, centre_x, top_y, up):
    """A filled triangle with a stem, centred on ``centre_x``."""
    for step in range(ARROW_HEAD_HEIGHT):
        if up:
            half = step
            y = top_y + step
        else:
            half = ARROW_HEAD_HEIGHT - 1 - step
            y = top_y + ARROW_STEM_HEIGHT + step
        landscape_rect(canvas, centre_x - half, y, 2 * half + 1, 1, 1)
    stem_y = top_y + ARROW_HEAD_HEIGHT if up else top_y
    landscape_rect(
        canvas, centre_x - ARROW_STEM_WIDTH // 2, stem_y,
        ARROW_STEM_WIDTH, ARROW_STEM_HEIGHT, 1,
    )


def draw_footer(canvas, top_y, scale=1, panel_width=296, font=None):
    """Draw the four labels in the band starting at ``top_y``.

    ``top_y`` is the top of one text cell; the arrows are centred inside that
    same cell, so the footer occupies exactly one row's height whatever the font
    reports.
    """
    cell_height = metrics(font)[1] * scale
    arrow_top = top_y + (cell_height - ARROW_HEIGHT) // 2
    if arrow_top < top_y:
        arrow_top = top_y
    for centre, action in zip(button_centres(panel_width), FOOTER_ACTIONS):
        label = LABELS.get(action)
        if label is None:
            draw_arrow(canvas, centre, arrow_top, action == UP)
            continue
        draw_text(
            canvas, label, centre - text_width(label, scale, font) // 2, top_y,
            scale, font,
        )
