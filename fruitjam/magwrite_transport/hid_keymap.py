"""HID usage translation for one boot-protocol USB keyboard.

Host-safe. No CircuitPython, USB, or hardware concept appears here: this module
turns HID Usage Page 0x07 usage IDs plus a modifier byte into the normalized
editor vocabulary defined by ``editor.py``, and nothing else.

Coverage is deliberately bounded to what the MagTag can actually draw. Every
character this module can emit is present in the proven 3x5 glyph table, which a
host test asserts directly. A key with no supported glyph translates to ``None``
so the adapter can count it and emit a bounded diagnostic instead of pushing an
unrenderable character into the authoritative document.

Caps Lock affects letters only. Shift affects everything. Both together return
letters to lowercase, which is what a real keyboard does.
"""

from magwrite_transport.editor import (
    BACKSPACE, CHAR, DELETE, DOWN, END, ENTER, HOME, LEFT, RIGHT, UP,
)

# ------------------------------------------------------------------ modifiers

MODIFIER_LEFT_CTRL = 0x01
MODIFIER_LEFT_SHIFT = 0x02
MODIFIER_LEFT_ALT = 0x04
MODIFIER_LEFT_GUI = 0x08
MODIFIER_RIGHT_CTRL = 0x10
MODIFIER_RIGHT_SHIFT = 0x20
MODIFIER_RIGHT_ALT = 0x40
MODIFIER_RIGHT_GUI = 0x80
SHIFT_MASK = MODIFIER_LEFT_SHIFT | MODIFIER_RIGHT_SHIFT

# --------------------------------------------------------------- special usages

USAGE_NONE = 0x00
USAGE_ERROR_ROLLOVER = 0x01
USAGE_POST_FAIL = 0x02
USAGE_ERROR_UNDEFINED = 0x03
ERROR_USAGES = (USAGE_ERROR_ROLLOVER, USAGE_POST_FAIL, USAGE_ERROR_UNDEFINED)

# Modifier keys may also appear in the usage array on some keyboards. They are
# read from the modifier byte, so an array occurrence is ignored rather than
# treated as an unsupported key.
FIRST_MODIFIER_USAGE = 0xE0
LAST_MODIFIER_USAGE = 0xE7

FIRST_LETTER_USAGE = 0x04
LAST_LETTER_USAGE = 0x1D

USAGE_ESCAPE = 0x29
USAGE_CAPS_LOCK = 0x39

# Keyboard Application, the "menu" key. Accepted as a second finish control
# because the keyboard used for the physical phase is a 40% board whose Escape
# is only reachable through an Fn layer, and on that board the Fn combination
# also switches the keyboard out of USB mode — pressing "Escape" silences the
# device instead of ending the run. A standalone key sending 0x65 is the one
# reliable finish gesture that hardware can produce. The usage has no other
# meaning here: it has no glyph and no editor action, so it previously counted
# only as an unsupported key.
USAGE_APPLICATION = 0x65

# ------------------------------------------------------------ control actions

CONTROL_FINISH = "FINISH"
CONTROL_CAPS_LOCK = "CAPS_LOCK"
CONTROL_UNSUPPORTED = "UNSUPPORTED"
CONTROL_USAGES = {
    USAGE_ESCAPE: CONTROL_FINISH,
    USAGE_APPLICATION: CONTROL_FINISH,
    USAGE_CAPS_LOCK: CONTROL_CAPS_LOCK,
}
FINISH_USAGES = tuple(
    usage for usage, control in CONTROL_USAGES.items()
    if control == CONTROL_FINISH
)

# ---------------------------------------------------------------- named keys

NAMED_USAGES = {
    0x28: ENTER,        # Return
    0x58: ENTER,        # Keypad Enter
    0x2A: BACKSPACE,
    0x4C: DELETE,
    0x4A: HOME,
    0x4D: END,
    0x4F: RIGHT,
    0x50: LEFT,
    0x51: DOWN,
    0x52: UP,
}

# Repeating Home and End would be pure work: both are idempotent, so a held key
# would emit events that change nothing and burn viewport frames.
REPEATABLE_KINDS = (
    CHAR, ENTER, BACKSPACE, DELETE, LEFT, RIGHT, UP, DOWN,
)

# ---------------------------------------------------------------- printables

# usage -> (unshifted, shifted). ``None`` marks a variant with no glyph in the
# proven table; the key is recognised but produces no editor event.
PRINTABLE_USAGES = {
    0x1E: ("1", "!"),
    0x1F: ("2", None),      # @
    0x20: ("3", None),      # #
    0x21: ("4", None),      # $
    0x22: ("5", None),      # %
    0x23: ("6", None),      # ^
    0x24: ("7", None),      # &
    0x25: ("8", None),      # *
    0x26: ("9", "("),
    0x27: ("0", ")"),
    0x2C: (" ", " "),       # Space
    0x2D: ("-", None),      # _
    0x2E: (None, None),     # = and +
    0x2F: (None, None),     # [ and {
    0x30: (None, None),     # ] and }
    0x31: (None, None),     # \ and |
    0x32: (None, None),     # non-US # and ~
    0x33: (";", ":"),
    0x34: ("'", '"'),
    0x35: (None, None),     # ` and ~
    0x36: (",", "<"),
    0x37: (".", ">"),
    0x38: ("/", "?"),
}
for _offset in range(26):
    _lower = chr(ord("a") + _offset)
    PRINTABLE_USAGES[FIRST_LETTER_USAGE + _offset] = (_lower, _lower.upper())
del _offset, _lower


def is_modifier_usage(usage):
    return FIRST_MODIFIER_USAGE <= usage <= LAST_MODIFIER_USAGE


def is_error_usage(usage):
    return usage in ERROR_USAGES


def is_letter_usage(usage):
    return FIRST_LETTER_USAGE <= usage <= LAST_LETTER_USAGE


def shift_active(modifier):
    return bool(modifier & SHIFT_MASK)


def supported_characters():
    """Every character this keymap can ever emit, for glyph verification."""
    found = set()
    for unshifted, shifted in PRINTABLE_USAGES.values():
        for value in (unshifted, shifted):
            if value is not None:
                found.add(value)
    return found


def translate(usage, shift, caps_lock):
    """Return ``(kind, value)`` for one usage, or ``None`` if unsupported.

    ``None`` covers an unmapped usage and a mapped key whose required variant
    has no glyph. Both are ignored deterministically by the caller.
    """
    kind = NAMED_USAGES.get(usage)
    if kind is not None:
        return kind, ""
    variants = PRINTABLE_USAGES.get(usage)
    if variants is None:
        return None
    upper = (shift != caps_lock) if is_letter_usage(usage) else shift
    value = variants[1] if upper else variants[0]
    if value is None:
        return None
    return CHAR, value
