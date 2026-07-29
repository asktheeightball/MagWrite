"""Deterministic word wrapping and visual-row layout owned by the Fruit Jam.

All layout happens here, on the authoritative device. The MagTag receives
already-windowed lines and never wraps, scrolls, or measures anything.

A *visual row* is ``(logical_row, start, end)``; its text is
``lines[logical_row][start:end]``. When a row is broken at a space, that space
is consumed and belongs to neither row, so the next row starts at ``end + 1``.
When a single word is longer than the viewport it is hard wrapped and the next
row starts at ``end``.

Every function here is a pure function of the document and the width, so
identical editor state always produces an identical layout, viewport payload,
and CRC.
"""

VIEWPORT_COLUMNS = 28
VIEWPORT_ROWS = 5
SPACE = " "


class Layout:
    """Fixed character-cell wrapping for a bounded document."""

    def __init__(self, width=None, height=None):
        width = VIEWPORT_COLUMNS if width is None else width
        height = VIEWPORT_ROWS if height is None else height
        if width < 2:
            raise ValueError("layout width must be at least two cells")
        if height < 1:
            raise ValueError("layout height must be at least one row")
        self.width = width
        self.height = height

    # ----------------------------------------------------------------- wrap

    def wrap_line(self, line):
        """Return the ``(start, end)`` spans one logical line occupies."""
        width = self.width
        length = len(line)
        if length <= width:
            return ((0, length),)
        spans = []
        start = 0
        while length - start > width:
            limit = start + width
            # Prefer breaking at the last space that still fits. Searching one
            # past the limit lets a space land exactly on the boundary.
            brk = line.rfind(SPACE, start + 1, limit + 1)
            if brk <= start:
                spans.append((start, limit))  # hard wrap a long word
                start = limit
            else:
                spans.append((start, brk))
                start = brk + 1
        spans.append((start, length))
        return tuple(spans)

    def rows(self, lines):
        """Return every visual row of the document, in order."""
        result = []
        for logical_row, line in enumerate(lines):
            for start, end in self.wrap_line(line):
                result.append((logical_row, start, end))
        return result

    # --------------------------------------------------------------- cursor

    def locate(self, lines, row, column):
        """Return ``(visual_row_index, visual_column)`` for a cursor position.

        When a hard wrap makes a column belong to two adjacent rows, the later
        row wins, so the cursor sits at the start of the continuation rather
        than past the right edge of the row above.
        """
        index = 0
        found = None
        for logical_row, line in enumerate(lines):
            for start, end in self.wrap_line(line):
                if logical_row == row and start <= column <= end:
                    found = (index, column - start)
                index += 1
            if logical_row == row and found is not None:
                break
        if found is None:
            raise ValueError("cursor is outside the document")
        return found

    # -------------------------------------------------------------- window

    def scroll_top(self, cursor_row_index):
        """Return the first visible visual row for a cursor row index.

        This is a pure function of the cursor position, never of scrolling
        history, so identical editor state always yields an identical window.
        The cursor is therefore always visible: it stays put until it would
        fall past the bottom, after which it rides the last visible row.
        """
        if cursor_row_index < self.height:
            return 0
        return cursor_row_index - self.height + 1

    def window(self, lines, row, column):
        """Return the complete visible window for the current editor state."""
        rows = self.rows(lines)
        cursor_index, cursor_column = self.locate(lines, row, column)
        top = self.scroll_top(cursor_index)
        visible = rows[top : top + self.height]
        texts = tuple(
            lines[logical_row][start:end] for logical_row, start, end in visible
        )
        return {
            "lines": texts,
            "top": top,
            "total_rows": len(rows),
            "cursor_row": cursor_index - top,
            "cursor_column": cursor_column,
            "more_above": top > 0,
            "more_below": top + self.height < len(rows),
        }
