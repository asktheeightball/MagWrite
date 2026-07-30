"""The screens the MagTag draws before the Fruit Jam has said anything. V1.6.

Host-safe: this module builds :class:`ViewportMessage` objects and nothing else.
Rendering and refreshing stay where they already are, so there is no second
renderer, no second framebuffer, and no second refresh policy.

Why the display-only board draws anything of its own
----------------------------------------------------

Because for the first several seconds of a standalone start it is the only thing
that *can*. One USB-C cable goes into the Fruit Jam; the MagTag is fed from one
of its USB-A host ports, so both boards cold boot together. In that window the
Fruit Jam is mounting a card, reading a catalogue, and restoring a document, and
it has no way to say so: the link it would say it on is the link that is not up
yet. Before V1.6 the panel simply held whatever the last session left on it,
which on a device with no console is indistinguishable from a device that is
broken.

This does not make the MagTag authoritative for anything. These screens contain
no document, no cursor, no revision, and no state the Fruit Jam owns -- they say
only what this board can see for itself: that it has started, and that nothing
has arrived yet. The moment a viewport does arrive it is drawn over them by the
ordinary path, and nothing here is ever drawn again for the life of the session.

``revision`` is deliberately 0 on both. The acknowledgement protocol treats 0 as
"nothing has been displayed", these frames are never acknowledged to anybody, and
the first real viewport is a full refresh regardless -- so a boot screen cannot
put a number into a conversation it is not part of.
"""

from magwrite.font import PRINTABLE_ASCII
from magwrite.viewport_message import MAX_LINES, ViewportMessage

STARTING_TITLE = "MAGWRITE"
WAITING_TITLE = "MAGWRITE"

# Both fit the six-row, 48-column panel with room to spare, and every character
# is in the built-in font -- a host test asserts that against the font's own
# reported coverage rather than trusting it here.
STARTING_LINES = (
    "STARTING",
    "",
    "ONE CABLE, NO BUTTONS",
    "NEEDED",
)
WAITING_LINES = (
    "WAITING FOR THE",
    "WRITER BOARD",
    "",
    "BOTH BOARDS START",
    "TOGETHER - THIS IS NORMAL",
)

STARTING_STATUS = "STARTING"
WAITING_STATUS = "WAITING"

# The panel is drawn from an exception message here, which is the one string on
# this board that is not a literal, so it gets the same bounded wrap and the same
# renderable-character discipline the Fruit Jam's error screen gets.
ERROR_TITLE = "MAGWRITE FAULT"
ERROR_STATUS = "FAULT"
MAX_LINE_CHARS = 48
ERROR_REASON_LINES = 4

# Everything the built-in font draws. See magwrite/font.py.
SAFE_CHARACTERS = set(PRINTABLE_ASCII)

REPLACEMENT = " "


def safe_text(value, limit=MAX_LINE_CHARS):
    """Reduce ``value`` to characters the panel can draw, bounded."""
    if value is None:
        return ""
    out = ""
    for character in str(value):
        out += character if character in SAFE_CHARACTERS else REPLACEMENT
        if len(out) >= limit:
            break
    return out


def wrap(value, width=MAX_LINE_CHARS, max_lines=ERROR_REASON_LINES):
    """Bounded word wrap. A screen that cannot encode is worse than a short one."""
    text = safe_text(value, width * max_lines)
    lines = []
    current = ""
    for word in text.split(" "):
        if not word:
            continue
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
                if len(lines) >= max_lines:
                    return tuple(lines)
            lines.append(word[:width])
            word = word[width:]
            if len(lines) >= max_lines:
                return tuple(lines)
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = current + " " + word
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                return tuple(lines)
    if current and len(lines) < max_lines:
        lines.append(current)
    return tuple(lines)


def _screen(title, lines, status):
    return ViewportMessage(
        0, 1, title, tuple(safe_text(line) for line in lines), 0, 0, status,
    )


def starting_screen():
    """Drawn as soon as the panel is initialised, before a byte is read."""
    return _screen(STARTING_TITLE, STARTING_LINES, STARTING_STATUS)


def waiting_screen():
    """Drawn when the handshake has not arrived within the patience window.

    Separate from :func:`starting_screen` because they answer different
    questions. "Starting" means this board is alive; "waiting" means this board
    is alive and the other one is not talking yet, which is the only startup
    state a writer might reasonably act on -- by checking the cable.
    """
    return _screen(WAITING_TITLE, WAITING_LINES, WAITING_STATUS)


def fault_screen(detail):
    """A construction failure this board can still draw.

    Reached when the panel came up and something after it did not -- a UART pin
    the board does not expose, most plausibly. Without this the failure is one
    JSON line on a console that, in the standalone configuration, nobody is
    connected to.
    """
    reason = wrap(detail or "UNKNOWN FAULT")
    lines = list(reason) if reason else ["UNKNOWN FAULT"]
    lines.append("")
    lines.append("DISCONNECT POWER, RETRY")
    return _screen(ERROR_TITLE, tuple(lines[:MAX_LINES]), ERROR_STATUS)
