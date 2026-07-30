"""Authoritative bounded multiline editor owned by the Fruit Jam.

The Fruit Jam is the only source of truth for document text, line structure,
cursor position, and the two revisions. The MagTag receives a finished semantic
viewport and never edits, wraps, scrolls, or interprets it.

Up and Down move by *visual* row, not logical line, so the preferred column is
the preferred visual column. That requires the editor to consult the same
deterministic layout the viewport builder uses; the layout is a pure function of
the document and the viewport width, so the editor stays deterministic.

Revision rules:

* ``document_revision`` advances only when the text actually changes.
* ``viewport_revision`` advances whenever visible state changes, which includes
  cursor-only movement and scrolling.

Edits are never silently dropped. Anything that would exceed a bound raises
``EditRejected`` so the caller can emit an explicit structured diagnostic.

The document bound, and why it is a character bound
---------------------------------------------------

Through V1.3 the document was 512 characters over 32 lines of 96. Those numbers
were sized for a transport experiment and they are wrong for a writing tool: the
editor word-wraps, so a **paragraph is one logical line**, and 96 characters is
about a sentence and a half. The V1.3 bench session hit
``document line capacity reached`` four times in ordinary prose. A writing
appliance whose first real session refuses the fifth sentence is not bounded, it
is broken.

So the bound is now a **character** bound, which is the one a writer can predict
and the one that actually governs cost:

* ``MAX_DOCUMENT_CHARS`` -- 8192, roughly 1,400 words. A journal entry, a scene,
  or a short essay fits whole. It is the bound that binds in practice;
* ``MAX_LINE_CHARS`` -- 1024, a long paragraph, so Enter stays a paragraph break
  rather than something the writer has to remember to press;
* ``MAX_DOCUMENT_LINES`` -- 512, a structural safety bound rather than a writing
  one. 8192 characters of prose is nowhere near 512 paragraphs; it is reachable
  only by holding Enter, and reaching it is refused as cleanly as any other bound.

Why these and not larger. The document is held whole in RAM and journaled as a
whole snapshot, so every bound here is multiplied through the storage path:

* one journal record is the escaped document, so the worst case is
  ``2 * MAX_DOCUMENT_CHARS`` bytes plus a header. ``journal.MAX_RECORD_BYTES`` is
  derived from this constant rather than written down beside it;
* ``Layout.locate`` runs per keystroke and is linear in the characters before the
  cursor; ``Layout.rows`` is linear in the whole document but runs only when a
  viewport is built, which pacing already holds to roughly one a second.

Both stay comfortably bounded at 8192 and neither needs file-backed editing or a
second document model to get there. Growing the bound by another order of
magnitude would; that is the line, and it has not been crossed.
"""

from magwrite_transport.editor_layout import Layout

MAX_EDITOR_EVENTS = 400
MAX_DOCUMENT_CHARS = 8192
MAX_DOCUMENT_LINES = 512
MAX_LINE_CHARS = 1024

CHAR = "CHAR"
ENTER = "ENTER"
BACKSPACE = "BACKSPACE"
DELETE = "DELETE"
LEFT = "LEFT"
RIGHT = "RIGHT"
UP = "UP"
DOWN = "DOWN"
HOME = "HOME"
END = "END"
EVENT_KINDS = (
    CHAR, ENTER, BACKSPACE, DELETE, LEFT, RIGHT, UP, DOWN, HOME, END,
)
# Up and Down are the only events that preserve a previously remembered
# preferred visual column; everything else re-anchors it to the new cursor.
VERTICAL_KINDS = (UP, DOWN)


class EditRejected(Exception):
    """An edit was refused explicitly; edits are never silently dropped."""


class SequenceError(Exception):
    """An event arrived out of order, duplicated, or with a gap."""


class QueueOverflow(Exception):
    """The bounded input queue is full; input is never silently discarded."""


class InputEvent:
    """One normalized input event.

    This is the boundary the LOLIN32 Bluetooth bridge will later produce. It
    deliberately carries no HID, Bluetooth, or CircuitPython concept: a future
    adapter only has to emit the same fields with monotonic sequence numbers.
    """

    __slots__ = ("sequence", "scenario", "kind", "value", "scheduled_ms")

    def __init__(self, sequence, scenario, kind, value="", scheduled_ms=0):
        if kind not in EVENT_KINDS:
            raise ValueError("unsupported event kind: " + str(kind))
        if kind == CHAR:
            if len(value) != 1 or not 32 <= ord(value) <= 126:
                raise ValueError("CHAR value must be one printable ASCII character")
        elif value:
            raise ValueError("only CHAR events carry a value")
        self.sequence = sequence
        self.scenario = scenario
        self.kind = kind
        self.value = value
        self.scheduled_ms = scheduled_ms


class BoundedEventQueue:
    """Fixed-capacity FIFO. Overflow raises instead of dropping an edit."""

    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._items = [None] * capacity
        self._head = 0
        self._size = 0
        self.overflow_count = 0
        self.maximum_depth = 0

    @property
    def capacity(self):
        return len(self._items)

    def __len__(self):
        return self._size

    def put(self, event):
        if self._size == self.capacity:
            self.overflow_count += 1
            raise QueueOverflow("editor event queue full")
        index = (self._head + self._size) % self.capacity
        self._items[index] = event
        self._size += 1
        if self._size > self.maximum_depth:
            self.maximum_depth = self._size
        return self._size

    def get(self):
        if not self._size:
            return None
        event = self._items[self._head]
        self._items[self._head] = None
        self._head = (self._head + 1) % self.capacity
        self._size -= 1
        return event


class SequenceTracker:
    """Exactly-once, strictly in-order processing of normalized input."""

    def __init__(self):
        self.expected = 0
        self.processed = 0

    def accept(self, event):
        if event.sequence != self.expected:
            raise SequenceError(
                "expected sequence %d, got %d" % (self.expected, event.sequence)
            )
        self.expected += 1
        self.processed += 1


class MultilineEditor:
    """The authoritative document, cursor, and revision state."""

    def __init__(
        self, width=None, max_chars=MAX_DOCUMENT_CHARS,
        max_lines=MAX_DOCUMENT_LINES, max_line_chars=MAX_LINE_CHARS,
        layout=None,
    ):
        if max_chars < 1 or max_lines < 1 or max_line_chars < 1:
            raise ValueError("editor bounds must be positive")
        self.layout = layout or Layout(width)
        self.max_chars = max_chars
        self.max_lines = max_lines
        self.max_line_chars = max_line_chars
        self.lines = [""]
        self.row = 0
        self.column = 0
        self.preferred_column = 0
        self.document_revision = 0
        self.viewport_revision = 0
        self.accepted_events = 0
        self.rejected_events = 0

    # ------------------------------------------------------------- inspection

    @property
    def text(self):
        return "\n".join(self.lines)

    @property
    def line(self):
        return self.lines[self.row]

    def character_count(self):
        """Total stored characters, counting each line break as one."""
        return sum(len(line) for line in self.lines) + len(self.lines) - 1

    def visual_rows(self):
        return self.layout.rows(self.lines)

    def cursor_visual_position(self):
        """Return ``(visual_row_index, visual_column)`` for the cursor."""
        return self.layout.locate(self.lines, self.row, self.column)

    # ------------------------------------------------------------- mutation

    def reset_document(self):
        """Clear the document between scenarios, keeping revisions monotonic."""
        changed = self.lines != [""]
        view_changed = changed or self.row or self.column
        self.lines = [""]
        self.row = 0
        self.column = 0
        self.preferred_column = 0
        if changed:
            self.document_revision += 1
        if view_changed:
            self.viewport_revision += 1
        return changed

    def _validate_document(self, text, row, column, what):
        """Return the validated line list for stored text, or reject explicitly.

        Bounds are enforced exactly as they are for an interactive edit, because
        a card is not a trusted input: a file that would exceed the editor's
        limits is refused rather than loaded into a state no edit could have
        produced. ``what`` names the source so the diagnostic says whether a
        recovery or a document switch was refused.
        """
        lines = text.split("\n")
        if len(lines) > self.max_lines:
            self._reject(what + " document exceeds line capacity")
        for line in lines:
            if len(line) > self.max_line_chars:
                self._reject(what + " line exceeds line capacity")
            for char in line:
                if not 32 <= ord(char) <= 126:
                    self._reject(what + " document contains an unsupported character")
        total = sum(len(line) for line in lines) + len(lines) - 1
        if total > self.max_chars:
            self._reject(what + " document exceeds document capacity")
        if not 0 <= row < len(lines):
            self._reject(what + " cursor row is outside the document")
        if not 0 <= column <= len(lines[row]):
            self._reject(what + " cursor column is outside its line")
        return lines

    def _adopt(self, lines, row, column, revision):
        self.lines = lines
        self.row = row
        self.column = column
        self.document_revision = revision
        self.preferred_column = self.cursor_visual_position()[1]
        self.viewport_revision += 1
        return revision

    def load(self, text, row=0, column=0, revision=None):
        """Adopt a recovered document, cursor, and revision.

        Used once, when a session opens on a document restored from the card.
        The revision is carried across rather than restarted so that revision
        numbers remain a continuous history of the document through a power loss;
        a restart would make the recovery journal impossible to read afterwards
        and would let a stale record outrank a newer one.
        """
        lines = self._validate_document(text, row, column, "recovered")
        if revision is None:
            revision = self.document_revision + 1
        if revision < self.document_revision:
            self._reject("recovered revision is older than the current one")
        return self._adopt(lines, row, column, revision)

    def open_document(self, text="", row=0, column=0):
        """Adopt a *different* document into this same editor. V1.4.

        This is the one operation that replaces the contents of the editor, and
        it exists because V1.4 has four modes and therefore more than one
        document. It does not weaken the V1.3 invariant it appears to touch --
        there is still exactly one ``MultilineEditor`` for the life of the
        session, and the shell still never calls this. The session does, and only
        after the outgoing document has been checkpointed, so a switch is a
        deliberate, durable handover rather than a close.

        The revision does **not** restart at the stored document's own revision,
        it continues from wherever this session already is. Two properties depend
        on that:

        * ``document_revision`` feeds the acknowledgement tracker and the save
          state, both of which assume it never goes backwards within a session;
        * per-document recency still works, because a document's stored revision
          is the highest ever written to it, and continuing from a session
          counter can only ever make the next record higher.

        A revision therefore identifies a state of *this session's* document
        history, and "higher wins" stays true inside every document's own log.
        """
        lines = self._validate_document(text, row, column, "opened")
        return self._adopt(lines, row, column, self.document_revision + 1)

    def note_visible_change(self):
        """Advance ``viewport_revision`` for visible state the editor does not own.

        The save-state indicator is drawn in the viewport but belongs to the
        persistence layer. Routing it through the editor keeps the editor the
        single owner of both revisions, which is what stops two different
        payloads from ever being transmitted under one revision number.
        """
        self.viewport_revision += 1
        return self.viewport_revision

    def _reject(self, reason):
        self.rejected_events += 1
        raise EditRejected(reason)

    def apply(self, event):
        """Apply one normalized event and return True if the text changed."""
        before_lines = list(self.lines)
        before_row = self.row
        before_column = self.column
        kind = event.kind

        if kind == CHAR:
            self._insert_character(event.value)
        elif kind == ENTER:
            self._split_line()
        elif kind == BACKSPACE:
            self._backspace()
        elif kind == DELETE:
            self._delete()
        elif kind == LEFT:
            self._move_left()
        elif kind == RIGHT:
            self._move_right()
        elif kind == UP:
            self._move_vertical(-1)
        elif kind == DOWN:
            self._move_vertical(1)
        elif kind == HOME:
            self.column = 0
        elif kind == END:
            self.column = len(self.line)
        else:
            self._reject("unsupported event kind")

        if kind not in VERTICAL_KINDS:
            self.preferred_column = self.cursor_visual_position()[1]

        self.accepted_events += 1
        changed = self.lines != before_lines
        if changed:
            self.document_revision += 1
        if changed or self.row != before_row or self.column != before_column:
            self.viewport_revision += 1
        return changed

    # --------------------------------------------------------------- editing

    def _insert_character(self, value):
        if len(value) != 1 or not 32 <= ord(value) <= 126:
            self._reject("CHAR must be one printable ASCII character")
        if len(self.line) >= self.max_line_chars:
            self._reject("line capacity reached")
        if self.character_count() >= self.max_chars:
            self._reject("document capacity reached")
        line = self.line
        self.lines[self.row] = line[: self.column] + value + line[self.column :]
        self.column += 1

    def _split_line(self):
        if len(self.lines) >= self.max_lines:
            self._reject("document line capacity reached")
        if self.character_count() >= self.max_chars:
            self._reject("document capacity reached")
        line = self.line
        self.lines[self.row] = line[: self.column]
        self.lines.insert(self.row + 1, line[self.column :])
        self.row += 1
        self.column = 0

    def _join_with_next(self, row):
        """Join line ``row + 1`` onto line ``row``; the join may be refused."""
        merged = len(self.lines[row]) + len(self.lines[row + 1])
        if merged > self.max_line_chars:
            self._reject("joined line exceeds line capacity")
        self.lines[row] = self.lines[row] + self.lines[row + 1]
        del self.lines[row + 1]

    def _backspace(self):
        if self.column:
            line = self.line
            self.lines[self.row] = line[: self.column - 1] + line[self.column :]
            self.column -= 1
        elif self.row:
            target = self.row - 1
            column = len(self.lines[target])
            self._join_with_next(target)
            self.row = target
            self.column = column

    def _delete(self):
        if self.column < len(self.line):
            line = self.line
            self.lines[self.row] = line[: self.column] + line[self.column + 1 :]
        elif self.row + 1 < len(self.lines):
            self._join_with_next(self.row)

    # --------------------------------------------------------------- motion

    def _move_left(self):
        if self.column:
            self.column -= 1
        elif self.row:
            self.row -= 1
            self.column = len(self.line)

    def _move_right(self):
        if self.column < len(self.line):
            self.column += 1
        elif self.row + 1 < len(self.lines):
            self.row += 1
            self.column = 0

    def _move_vertical(self, delta):
        """Move one visual row, honouring the preferred visual column."""
        rows = self.visual_rows()
        index, _ = self.layout.locate(self.lines, self.row, self.column)
        target = index + delta
        if not 0 <= target < len(rows):
            return
        logical_row, start, end = rows[target]
        column = start + self.preferred_column
        if column > end:
            column = end
        self.row = logical_row
        self.column = column
