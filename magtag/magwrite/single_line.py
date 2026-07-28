"""Bounded single-line editor, viewport, and deterministic typing scenarios."""

MAX_TYPING_EVENTS = 250
MAX_PARTIAL_REFRESHES = 100
TYPING_TEST_MODE = "SINGLE_LINE_TYPING"
TYPING_START_GUARD = "/magwrite_single_line_typing.started"
TYPING_COMPLETE_GUARD = "/magwrite_single_line_typing.complete"


class EditRejected(Exception):
    pass


class SequenceError(Exception):
    pass


class TypingEvent:
    __slots__ = ("sequence", "scenario", "kind", "value")

    def __init__(self, sequence, scenario, kind, value=""):
        self.sequence = sequence
        self.scenario = scenario
        self.kind = kind
        self.value = value


class SingleLineEditor:
    def __init__(self, max_chars=96):
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self.max_chars = max_chars
        self.text = ""
        self.cursor = 0
        self.document_revision = 0
        self.render_revision = 0
        self.accepted_events = 0
        self.rejected_events = 0

    def apply(self, event):
        old_text = self.text
        old_cursor = self.cursor
        if event.kind == "insert":
            if len(event.value) != 1 or not 32 <= ord(event.value) <= 126:
                self.rejected_events += 1
                raise EditRejected("insert must be one printable ASCII character")
            if len(self.text) >= self.max_chars:
                self.rejected_events += 1
                raise EditRejected("line capacity reached")
            self.text = (
                self.text[: self.cursor] + event.value + self.text[self.cursor :]
            )
            self.cursor += 1
        elif event.kind == "backspace":
            if self.cursor:
                self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
                self.cursor -= 1
        elif event.kind == "delete":
            if self.cursor < len(self.text):
                self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]
        elif event.kind == "left":
            self.cursor = max(0, self.cursor - 1)
        elif event.kind == "right":
            self.cursor = min(len(self.text), self.cursor + 1)
        elif event.kind == "home":
            self.cursor = 0
        elif event.kind == "end":
            self.cursor = len(self.text)
        else:
            self.rejected_events += 1
            raise EditRejected("unsupported single-line event")

        self.accepted_events += 1
        changed = self.text != old_text
        view_changed = changed or self.cursor != old_cursor
        if changed:
            self.document_revision += 1
        if view_changed:
            self.render_revision += 1
        return changed


class HorizontalViewport:
    """Fixed-cell viewport that keeps the insertion cursor visible."""

    def __init__(self, columns=34):
        if columns < 4:
            raise ValueError("viewport must have at least four columns")
        self.columns = columns

    def snapshot(self, editor):
        content_columns = self.columns - 2
        max_start = max(0, len(editor.text) - content_columns)
        start = min(max_start, max(0, editor.cursor - content_columns + 1))
        end = min(len(editor.text), start + content_columns)
        left_hidden = start > 0
        right_hidden = end < len(editor.text)
        visible = editor.text[start:end]
        visible += " " * (content_columns - len(visible))
        content = list(visible)
        cursor_cell = editor.cursor - start
        if cursor_cell >= content_columns:
            cursor_cell = content_columns - 1
        line = ("<" if left_hidden else " ") + "".join(content)
        line += ">" if right_hidden else " "
        return {
            "text": line,
            "start": start,
            "end": end,
            "cursor_cell": cursor_cell + 1,
            "document_revision": editor.document_revision,
            "render_revision": editor.render_revision,
        }


def _insert_events(name, text):
    return [(name, "insert", character) for character in text]


def scenario_specs():
    ordinary = "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG"
    fast = "MAGWRITE CAPTURES EVERY KEY WHILE THE DISPLAY IS BUSY"
    typo = "TODAY I WROTE A JORUNAL ENTRY"
    correction = _insert_events("correction", typo)
    correction += [("correction", "home", "")]
    correction += [("correction", "right", "")] * 18
    correction += [
        ("correction", "delete", ""),
        ("correction", "right", ""),
        ("correction", "insert", "R"),
        ("correction", "end", ""),
    ]
    viewport_text = "PACK MY BOX WITH FIVE DOZEN LIQUOR JUGS"
    viewport = _insert_events("viewport", viewport_text)
    viewport += [("viewport", "left", "")] * 8
    viewport += [
        ("viewport", "home", ""),
        ("viewport", "end", ""),
        ("viewport", "left", ""),
        ("viewport", "left", ""),
        ("viewport", "left", ""),
        ("viewport", "left", ""),
    ]
    return (
        ("ordinary", 40, _insert_events("ordinary", ordinary), ordinary),
        ("fast_typing", 80, _insert_events("fast_typing", fast), fast),
        ("correction", 80, correction, "TODAY I WROTE A JOURNAL ENTRY"),
        ("viewport", 80, viewport, viewport_text),
    )


def numbered_scenarios():
    sequence = 0
    result = []
    for name, wpm, specs, expected in scenario_specs():
        events = []
        for scenario, kind, value in specs:
            events.append(TypingEvent(sequence, scenario, kind, value))
            sequence += 1
        result.append((name, wpm, tuple(events), expected))
    if sequence > MAX_TYPING_EVENTS:
        raise ValueError("typing scenarios exceed event safety limit")
    return tuple(result)


class ScheduledScenarioProducer:
    SUPPORTED_WPM = (40, 60, 80)

    def __init__(self, events, wpm, start_ms=0):
        if wpm not in self.SUPPORTED_WPM:
            raise ValueError("unsupported WPM")
        self.events = events
        self.interval_ms = 60000.0 / (wpm * 5)
        self.index = 0
        self.next_due_ms = start_ms

    @property
    def complete(self):
        return self.index == len(self.events)

    def produce_due(self, now_ms, queue):
        produced = 0
        while not self.complete and now_ms >= self.next_due_ms:
            queue.put(self.events[self.index])
            self.index += 1
            self.next_due_ms += self.interval_ms
            produced += 1
        return produced


class SequenceTracker:
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
