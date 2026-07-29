"""Deliberate key repeat for one held key.

Host-safe, and the single home for every keyboard timing constant so a physical
run never has two disagreeing sources of truth.

Repeat is deliberate, not incidental: identical HID reports never repeat
anything by themselves (``hid_keyboard`` suppresses them). A repeat only happens
because a key is *still held* and the configured delay has elapsed. The newest
press always owns the repeat, and releasing that key cancels it immediately.

Catch-up is bounded. If the cooperative loop stalls — a full refresh, a long
UART drain — the repeat does not silently accumulate an unbounded burst of
edits; it emits at most ``max_catch_up`` and resynchronizes.
"""

REPEAT_DELAY_MS = 500
REPEAT_INTERVAL_MS = 80
MAX_CATCH_UP = 4


class KeyRepeat:
    def __init__(
        self, delay_ms=REPEAT_DELAY_MS, interval_ms=REPEAT_INTERVAL_MS,
        max_catch_up=MAX_CATCH_UP,
    ):
        if delay_ms <= 0 or interval_ms <= 0 or max_catch_up < 1:
            raise ValueError("repeat timings must be positive")
        self.delay_ms = delay_ms
        self.interval_ms = interval_ms
        self.max_catch_up = max_catch_up
        self.usage = None
        self.decision = None
        self.next_due_ms = None
        self.armed_count = 0
        self.repeats_emitted = 0
        self.resynchronizations = 0

    @property
    def armed(self):
        return self.usage is not None

    def arm(self, usage, decision, now_ms):
        """Make ``usage`` the repeat owner. The newest press always wins."""
        self.usage = usage
        self.decision = decision
        self.next_due_ms = now_ms + self.delay_ms
        self.armed_count += 1

    def cancel(self):
        self.usage = None
        self.decision = None
        self.next_due_ms = None

    def cancel_if_released(self, released):
        """Cancel when the repeating key appears in ``released``."""
        if self.usage is not None and self.usage in released:
            self.cancel()
            return True
        return False

    def due(self, now_ms):
        """Return how many repeats are due now, bounded by ``max_catch_up``."""
        if self.next_due_ms is None or now_ms < self.next_due_ms:
            return 0
        count = 0
        while count < self.max_catch_up and now_ms >= self.next_due_ms:
            count += 1
            self.next_due_ms += self.interval_ms
        if now_ms >= self.next_due_ms:
            self.next_due_ms = now_ms + self.interval_ms
            self.resynchronizations += 1
        self.repeats_emitted += count
        return count
