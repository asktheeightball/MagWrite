"""The MagTag UI's one font: CircuitPython's built-in ``terminalio.FONT``.

Every character the writer sees on the panel -- editor text, menus, titles, the
startup and waiting screens, status, error text, and the button footer -- is
drawn by :func:`draw_text` from this one font, at native scale 1.

Why the built-in font replaced the hand-drawn table
---------------------------------------------------

The panel used to be drawn from a 3x5 bitmap table maintained by hand in
``magwrite/test_pattern.py``. It worked, and it cost something every time: an
apostrophe, a semicolon, and the whole lowercase alphabet each arrived as a
separate act of type design, a character with no entry raised ``KeyError`` on the
first frame that carried it, and the sanitizers on both boards existed mostly to
keep that from happening. ``terminalio.FONT`` is Terminus at 6x12 -- a real
monospace terminal face, shipped with the firmware, covering the whole printable
ASCII range and beyond, at no flash cost and no maintenance cost.

That table is *not* deleted. The one-shot hardware harnesses that produced this
project's physical evidence still draw with it, and a proven harness is not
something to re-render on the way past. It is simply no longer the UI's font.

Scale, and why the geometry is computed rather than written down
----------------------------------------------------------------

Scale 1 is native and is what the panel uses. It is very close in size to what
the 3x5 table drew at scale 2 -- the same 6 px advance, two pixels more height --
so the text the bench already proved readable is the text this draws.

Nothing here hard-codes 6 or 12. :func:`metrics` asks the font for its own
bounding box and :mod:`magwrite.viewport_renderer` derives the row pitch, the row
count, and the column count from that. If a firmware build ever ships a different
built-in font, the layout follows it instead of drawing off the edge of the panel.

A missing glyph is still an error
---------------------------------

:func:`draw_text` raises on a codepoint the font has no glyph for, exactly as the
old table's ``KeyError`` did. Both boards sanitize every string they draw down to
printable ASCII, so this cannot happen; keeping it fatal is what keeps those
sanitizers honest, and a silent blank would be a defect that reaches the writer
as a hole in a word rather than as a report.

The host stand-in
-----------------

CPython has no ``terminalio``, so the host suite -- which renders real frames
through the real renderer -- gets :class:`_HostMetricsFont`. It is a test double
and never a font: it reports the same bounding box as the real one and fills each
cell with a pattern derived from the codepoint, so it carries no letterforms for
a host test to assert against by accident. On a board the import always succeeds
and the stand-in is unreachable; :func:`is_builtin_font` says which one is in use
and the standalone runtime logs it at startup.
"""

from magwrite.mono_canvas import landscape_pixel, landscape_rect

# Everything either board is allowed to draw. Terminus covers all of it; the
# runtime checks that against the real font on the real board at startup and
# logs anything missing, which is the only place that claim can honestly be made.
PRINTABLE_ASCII = tuple(chr(_code) for _code in range(0x20, 0x7F))

NATIVE_SCALE = 1


class _HostGlyphSheet:
    """The tile strip a :class:`_HostMetricsFont` glyph indexes into."""

    def __init__(self, width, height, count):
        self.width = width * count
        self.height = height
        self.cell_width = width

    def __getitem__(self, position):
        x, y = position
        code = 0x20 + x // self.cell_width
        # Deliberately not letterforms. Distinct per character so a host test
        # can still tell two frames apart, and recognisable as nothing at all.
        return ((code + y) >> (x % self.cell_width)) & 1


class _HostGlyph:
    __slots__ = ("bitmap", "tile_index", "width", "height", "dx", "dy",
                 "shift_x", "shift_y")

    def __init__(self, sheet, tile_index, width, height):
        self.bitmap = sheet
        self.tile_index = tile_index
        self.width = width
        self.height = height
        self.dx = 0
        self.dy = 0
        self.shift_x = width
        self.shift_y = height


class _HostMetricsFont:
    """Metrics of the built-in font, with none of its type design. Host only."""

    def __init__(self, width=6, height=12):
        self.width = width
        self.height = height
        self.sheet = _HostGlyphSheet(width, height, len(PRINTABLE_ASCII))

    def get_bounding_box(self):
        return (self.width, self.height)

    def get_glyph(self, codepoint):
        if not 0x20 <= codepoint <= 0x7E:
            return None
        return _HostGlyph(self.sheet, codepoint - 0x20, self.width, self.height)


_BUILTIN = None
try:  # CircuitPython. There is no fallback on a board and there must not be.
    import terminalio

    _BUILTIN = terminalio.FONT
except ImportError:
    _BUILTIN = None

FONT = _BUILTIN if _BUILTIN is not None else _HostMetricsFont()


def is_builtin_font(font=None):
    """True when the font in use is the firmware's own ``terminalio.FONT``."""
    font = FONT if font is None else font
    return _BUILTIN is not None and font is _BUILTIN


def metrics(font=None):
    """The font's own ``(cell_width, cell_height)`` in pixels, at scale 1."""
    font = FONT if font is None else font
    box = font.get_bounding_box()
    return int(box[0]), int(box[1])


def missing_glyphs(characters=PRINTABLE_ASCII, font=None):
    """Which of ``characters`` this font cannot draw. Empty is the answer."""
    font = FONT if font is None else font
    absent = []
    for character in characters:
        if font.get_glyph(ord(character)) is None:
            absent.append(character)
    return tuple(absent)


def text_width(text, scale=NATIVE_SCALE, font=None):
    """Advance width of ``text`` in pixels. Monospace, so no measuring loop."""
    return len(text) * metrics(font)[0] * scale


# One entry per character actually drawn, holding that glyph's rows as integer
# bitmasks. Bounded at the size of PRINTABLE_ASCII, because everything outside it
# raises before it can be cached, and it is read exactly once per character for
# the life of the board: a full 48x6 panel is 288 glyph draws, and reading them
# out of the font bitmap every frame is the one thing here an ESP32-S2 notices.
_ROWS = {}
_ROWS_FONT = None


def _glyph_rows(font, character):
    global _ROWS_FONT
    if font is not _ROWS_FONT:
        _ROWS.clear()
        _ROWS_FONT = font
    rows = _ROWS.get(character)
    if rows is not None:
        return rows
    glyph = font.get_glyph(ord(character))
    if glyph is None:
        raise ValueError("no glyph for " + repr(character))
    sheet = glyph.bitmap
    width = glyph.width
    height = glyph.height
    # The built-in font packs its glyphs as tiles in one bitmap. A single row of
    # tiles is the layout CircuitPython actually ships, and the grid form below
    # reduces to exactly that when there is one row -- so this handles both
    # without asking which it got.
    columns = sheet.width // width if width else 1
    if columns < 1:
        columns = 1
    origin_x = (glyph.tile_index % columns) * width
    origin_y = (glyph.tile_index // columns) * height
    built = []
    for gy in range(height):
        mask = 0
        row = origin_y + gy
        for gx in range(width):
            if sheet[origin_x + gx, row]:
                mask |= 1 << gx
        built.append(mask)
    rows = tuple(built)
    _ROWS[character] = rows
    return rows


def draw_text(canvas, text, x, y, scale=NATIVE_SCALE, font=None):
    """Draw ``text`` with its top-left cell corner at ``(x, y)``. Returns the
    x the next character would occupy.

    Raises ``ValueError`` for a character the font has no glyph for. See the
    module docstring: that is the old table's ``KeyError``, kept deliberately.
    """
    font = FONT if font is None else font
    advance = metrics(font)[0] * scale
    native = scale == 1
    for character in text:
        if character == " ":
            # The built-in font's space is blank, and a line of prose is a good
            # fraction spaces, so this is a shortcut worth taking on an ESP32-S2.
            x += advance
            continue
        for gy, mask in enumerate(_glyph_rows(font, character)):
            if not mask:
                continue
            top = y + gy * scale
            gx = 0
            while mask:
                if mask & 1:
                    if native:
                        landscape_pixel(canvas, x + gx, top, 1)
                    else:
                        landscape_rect(
                            canvas, x + gx * scale, top, scale, scale, 1)
                mask >>= 1
                gx += 1
        x += advance
    return x
