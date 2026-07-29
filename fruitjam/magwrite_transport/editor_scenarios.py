"""Deterministic local input for the integrated editor test.

No keyboard, Bluetooth, or wireless input exists here. Every event is generated
locally from a fixed script at a deterministic words-per-minute schedule, so the
run is exactly reproducible on the host and on the device.

This module is the *deterministic input source* in the architecture. It sits
behind the same normalized ``InputEvent`` boundary the LOLIN32 Bluetooth bridge
will later use, so swapping the source will not touch the editor, the layout,
the viewport, or the acknowledgement code.

Only characters present in the proven MagTag glyph table are used.
"""

from magwrite_transport.editor import (
    BACKSPACE, CHAR, DELETE, DOWN, END, ENTER, HOME, InputEvent, LEFT,
    MAX_EDITOR_EVENTS, RIGHT, UP,
)

# Authorised physical ceilings for this integrated run. The harness budgets
# below sit well under them so a runaway loop stops first.
MAX_EDITOR_VIEWPORT_FRAMES = 75
MAX_EDITOR_INPUT_FRAMES = 150
MAX_EDITOR_STATUS_FRAMES = 150
MAX_EDITOR_PARTIAL_REFRESHES = 40
SUPPORTED_WPM = (40, 60, 80)

PARAGRAPH_LINES = (
    "MAGWRITE IS A WRITING TOOL.",
    "IT RUNS ON E-PAPER.",
    "CURSOR STAYS VISIBLE.",
)
PARAGRAPH_TEXT = "\n".join(PARAGRAPH_LINES)

CORRECTION_TEXT = "TODAY I WROTE A JOURNAL ENTRY.\nSECOND LINE. AMEN."

FAST_TEXT = "MAGWRITE CAPTURES EVERY KEY WHILE THE DISPLAY IS BUSY."

SCROLL_LINES = (
    "LINE ONE", "LINE TWO", "LINE THREE", "LINE FOUR", "LINE FIVE", "LINE SIX",
)
SCROLL_TEXT = "\n".join(SCROLL_LINES)

JOURNAL_TEXT = (
    "28 JULY 2026.\n"
    "\n"
    "FIRST REAL WORDS ON THE MAGWRITE PROTOTYPE. THE SCREEN HOLDS THEM."
)


def interval_ms(wpm):
    if wpm not in SUPPORTED_WPM:
        raise ValueError("unsupported WPM")
    return 60000.0 / (wpm * 5)


def _chars(text):
    """Expand text into CHAR and ENTER events."""
    out = []
    for character in text:
        if character == "\n":
            out.append((ENTER, ""))
        else:
            out.append((CHAR, character))
    return out


def _repeat(kind, count):
    return [(kind, "")] * count


def _paragraph_specs():
    """Scenario 1: plain multiline paragraph entry."""
    return _chars(PARAGRAPH_TEXT)


def _correction_specs():
    """Scenario 2: deliberate spelling and line-break errors, then corrections.

    The typed text contains the transposition ``JORUNAL`` and an unwanted line
    break before ``ENTRY.``. Both are repaired with navigation and deletion
    only, so the final document is reached by editing rather than retyping.
    """
    specs = _chars("TODAY I WROTE A JORUNAL")
    specs += [(ENTER, "")]
    specs += _chars("ENTRY.")

    # Repair the unwanted line break: Backspace at column zero joins upward.
    specs += [(HOME, ""), (BACKSPACE, ""), (CHAR, " ")]

    # Repair JORUNAL -> JOURNAL: delete the transposed R and reinsert it after
    # the U. Column 18 is the R in "TODAY I WROTE A JORUNAL ENTRY.".
    specs += [(HOME, "")]
    specs += _repeat(RIGHT, 18)
    specs += [(DELETE, ""), (RIGHT, ""), (CHAR, "R"), (END, "")]

    # A second logical line, then vertical motion across a wrapped line to
    # exercise the preferred visual column.
    specs += [(ENTER, "")]
    specs += _chars("SECOND LINE.")
    specs += [(UP, ""), (UP, ""), (DOWN, ""), (DOWN, "")]

    # Left and Right across a line boundary.
    specs += [(HOME, ""), (LEFT, ""), (RIGHT, ""), (END, "")]

    # A third line joined upward with Delete at end of line.
    specs += [(ENTER, "")]
    specs += _chars("AMEN.")
    specs += [(HOME, ""), (LEFT, ""), (DELETE, ""), (CHAR, " "), (END, "")]
    return specs


def _scroll_specs():
    """Scenario 4: more visual rows than fit, then cursor navigation."""
    specs = _chars(SCROLL_TEXT)
    specs += _repeat(UP, 5)          # up to the first line
    specs += [(HOME, "")]
    specs += _repeat(DOWN, 2)        # back into the middle
    specs += [(END, "")]
    specs += _repeat(DOWN, 3)        # down to the last line
    specs += [(END, "")]
    return specs


def scenario_specs():
    """Return ``(name, id, wpm, min_send_seconds, max_frames, specs, expected)``.

    ``min_send_seconds`` and ``max_frames`` bound how much UART traffic each
    scenario may generate. Scenario 3 deliberately sends faster than one
    physical refresh so the MagTag must supersede a stale pending viewport;
    every other scenario sends well below the refresh rate.
    """
    return (
        ("paragraph", 1, 60, 3.0, 4, _paragraph_specs(), PARAGRAPH_TEXT),
        ("correction", 2, 60, 3.2, 5, _correction_specs(), CORRECTION_TEXT),
        ("fast_typing", 3, 80, 0.45, 6, _chars(FAST_TEXT), FAST_TEXT),
        ("scrolling", 4, 60, 2.6, 5, _scroll_specs(), SCROLL_TEXT),
        ("journal", 5, 60, 2.6, 6, _chars(JOURNAL_TEXT), JOURNAL_TEXT),
    )


def numbered_scenarios():
    """Assign monotonic sequence numbers and absolute schedules to all events."""
    sequence = 0
    scheduled_ms = 0.0
    result = []
    for name, scenario_id, wpm, min_send, max_frames, specs, expected in (
        scenario_specs()
    ):
        step = interval_ms(wpm)
        events = []
        for kind, value in specs:
            events.append(InputEvent(sequence, name, kind, value, int(scheduled_ms)))
            sequence += 1
            scheduled_ms += step
        result.append(
            (name, scenario_id, wpm, min_send, max_frames, tuple(events), expected)
        )
    if sequence > MAX_EDITOR_EVENTS:
        raise ValueError("editor scenarios exceed the event safety limit")
    if sum(item[4] for item in result) + len(result) > MAX_EDITOR_VIEWPORT_FRAMES:
        raise ValueError("scenario frame budgets exceed the viewport ceiling")
    return tuple(result)


def total_event_count():
    return sum(len(item[5]) for item in numbered_scenarios())


class ScheduledEventProducer:
    """Emits each event once, in order, when its scheduled time is due."""

    def __init__(self, events, wpm, start_ms=0):
        self.step_ms = interval_ms(wpm)
        self.events = events
        self.index = 0
        self.start_ms = start_ms
        self.produced = 0

    @property
    def complete(self):
        return self.index == len(self.events)

    def produce_due(self, now_ms, queue, budget=16):
        """Enqueue every currently due event, bounded by ``budget``."""
        produced = 0
        while produced < budget and not self.complete:
            due = self.start_ms + self.index * self.step_ms
            if now_ms < due:
                break
            queue.put(self.events[self.index])
            self.index += 1
            produced += 1
        self.produced += produced
        return produced
