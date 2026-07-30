"""Shell screens, drawn through the proven viewport encoder.

Host-safe. There is no second renderer here and there is deliberately no second
transport: a menu is a semantic viewport like any other, so it goes out through
``encode_viewport``, the same bounded payload, the same CRC-32, the same
acknowledgement tracking, and the same adaptive pacing that the editor uses. The
MagTag cannot tell a menu from a document and must not be able to -- it draws the
lines it is given and interprets nothing.

That is also why the shell has no new display timing. A menu that redrew on its
own schedule would be a second pacing policy, and two pacing policies on one
panel is how a display ends up refreshing twice for one change.

Every character below has a glyph
---------------------------------

The panel's 3x5 table is the whole alphabet this device has. ``SAFE_CHARACTERS``
is the subset written out explicitly, and a host test asserts it against the
MagTag's real table; ``safe_text`` maps anything else to a space. This is not
defensive habit, it is a fixed defect: the first save indicator used "=" and "*",
which have no glyph, and the renderer raised ``KeyError`` on the first frame that
carried one. Error text is the obvious repeat of that mistake, because it is the
one string on the device that comes from an exception rather than from a literal.
"""

from magwrite_transport.deterministic_viewports import encode_viewport
from magwrite_transport.shell import (
    STATE_DRAFTS, STATE_ERROR, STATE_EXIT, STATE_MAIN_MENU,
)

# Distinct from the editor's scenario id so a shell frame is never mistaken for a
# document frame in a capture, a log, or a later reconciliation.
SHELL_SCENARIO_ID = 7

MAX_LINES = 5
MAX_LINE_CHARS = 28
MAX_FIELD_CHARS = 20

MENU_TITLE = "MAGWRITE MENU"
ERROR_TITLE = "MAGWRITE ERROR"
EXIT_TITLE = "MAGWRITE"
DRAFTS_TITLE = "MAGWRITE DRAFTS"
NO_DRAFTS = "NO DRAFTS YET"

SELECTED_PREFIX = "> "
UNSELECTED_PREFIX = "  "

# The punctuation the proven table actually carries. Letters and digits are added
# below. Anything absent from this set is replaced rather than drawn.
SAFE_PUNCTUATION = " /<>.,'-:!?;\"()"
SAFE_CHARACTERS = set(SAFE_PUNCTUATION)
for _code in range(ord("0"), ord("9") + 1):
    SAFE_CHARACTERS.add(chr(_code))
for _code in range(ord("A"), ord("Z") + 1):
    SAFE_CHARACTERS.add(chr(_code))
for _code in range(ord("a"), ord("z") + 1):
    SAFE_CHARACTERS.add(chr(_code))
del _code

REPLACEMENT = " "


def safe_text(value, limit=MAX_LINE_CHARS):
    """Return ``value`` reduced to characters the panel can draw, bounded."""
    if value is None:
        return ""
    out = ""
    for character in str(value):
        out += character if character in SAFE_CHARACTERS else REPLACEMENT
        if len(out) >= limit:
            break
    return out


def wrap(value, width=MAX_LINE_CHARS, max_lines=3):
    """Bounded word wrap for one sanitized string.

    Bounded twice: never more than ``max_lines`` lines, and never a line longer
    than ``width``. A word longer than the width is cut rather than allowed to
    overflow, because an error screen that cannot be encoded is worse than an
    error message that is short.
    """
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


def _status(text, save_indicator):
    if save_indicator:
        if len(save_indicator) != 1:
            raise ValueError("the save indicator must be one character")
        text = text + " " + save_indicator
    return safe_text(text, MAX_FIELD_CHARS)


def _encode(title, lines, cursor_row, cursor_column, status):
    if not lines:
        lines = ("",)
    lines = tuple(safe_text(line) for line in lines[:MAX_LINES])
    if cursor_row >= len(lines):
        cursor_row = len(lines) - 1
    if cursor_column > len(lines[cursor_row]):
        cursor_column = len(lines[cursor_row])
    return encode_viewport(
        SHELL_SCENARIO_ID, safe_text(title, MAX_FIELD_CHARS), lines,
        cursor_row, cursor_column, status,
    )


# ----------------------------------------------------------------- screens


def menu_payload(shell, save_indicator=None):
    """The main menu: every item visible at once, the selected one marked."""
    lines = []
    for index, item in enumerate(shell.items[:MAX_LINES]):
        prefix = SELECTED_PREFIX if index == shell.selection else UNSELECTED_PREFIX
        lines.append(prefix + item[1])
    row = shell.selection if shell.selection < len(lines) else 0
    status = _status(
        "MENU %d/%d" % (shell.selection + 1, len(shell.items)), save_indicator
    )
    return _encode(MENU_TITLE, tuple(lines), row, 0, status)


def drafts_payload(shell, save_indicator=None):
    """The working set: one document a row, the selected one marked.

    The catalogue is bounded well above five, so the panel shows a window and the
    status field says where in the list the writer is. Scrolling a list of titles
    is the same problem as scrolling a document and gets the same answer -- the
    window follows the cursor, and it is a pure function of the selection rather
    than of how the writer arrived at it.
    """
    visible = shell.visible_drafts()
    if not visible:
        lines = (NO_DRAFTS, "", "ESC  MENU")
        return _encode(DRAFTS_TITLE, lines, 0, 0, _status("0/0", save_indicator))
    lines = []
    for offset, entry in enumerate(visible):
        index = shell.draft_top + offset
        prefix = SELECTED_PREFIX if index == shell.draft_selection else (
            UNSELECTED_PREFIX
        )
        lines.append(prefix + entry.title)
    row = shell.draft_selection - shell.draft_top
    if not 0 <= row < len(lines):
        row = 0
    status = _status(
        "%d/%d" % (shell.draft_selection + 1, shell.draft_count), save_indicator
    )
    return _encode(DRAFTS_TITLE, tuple(lines), row, 0, status)


def error_payload(shell, save_indicator=None):
    """A recoverable failure. The document is still in the editor behind it."""
    reason = wrap(shell.error_reason or "UNKNOWN FAULT", MAX_LINE_CHARS, 3)
    lines = list(reason) if reason else ["UNKNOWN FAULT"]
    lines.append("WORK IS KEPT")
    lines.append("ENTER  MENU")
    status = _status("ERROR", save_indicator)
    return _encode(ERROR_TITLE, tuple(lines), 0, 0, status)


def exit_payload(shell, editor, save_indicator=None):
    """The closing screen, so a stop is something the writer can see happen."""
    lines = ("STOPPED", "%d CHARS  %d LINES"
             % (editor.character_count(), len(editor.lines)))
    status = _status("D%03d" % (editor.document_revision % 1000), save_indicator)
    return _encode(EXIT_TITLE, lines, 0, 0, status)


def payload(shell, editor, save_indicator=None):
    """Build the screen for the shell's current state.

    Returns ``None`` when the editor owns the panel, which is the caller's signal
    to build the ordinary document viewport it has always built.
    """
    state = shell.state
    if state == STATE_MAIN_MENU:
        return menu_payload(shell, save_indicator)
    if state == STATE_DRAFTS:
        return drafts_payload(shell, save_indicator)
    if state == STATE_ERROR:
        return error_payload(shell, save_indicator)
    if state == STATE_EXIT:
        return exit_payload(shell, editor, save_indicator)
    return None
