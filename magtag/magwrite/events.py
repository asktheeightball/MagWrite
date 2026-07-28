"""Bounded key events and deterministic typing simulation."""


class KeyEvent:
    __slots__ = ("sequence", "kind", "value")

    def __init__(self, sequence, kind, value=""):
        self.sequence = sequence
        self.kind = kind
        self.value = value


class QueueOverflow(Exception):
    pass


class BoundedEventQueue:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._items = [None] * capacity
        self._head = 0
        self._size = 0
        self.overflow_count = 0

    @property
    def capacity(self):
        return len(self._items)

    def __len__(self):
        return self._size

    def put(self, event):
        if self._size == self.capacity:
            self.overflow_count += 1
            raise QueueOverflow("event queue full")
        index = (self._head + self._size) % self.capacity
        self._items[index] = event
        self._size += 1

    def get(self):
        if not self._size:
            return None
        event = self._items[self._head]
        self._items[self._head] = None
        self._head = (self._head + 1) % self.capacity
        self._size -= 1
        return event


class DeterministicProducer:
    """Produces one character event per due time using five chars/word."""

    SUPPORTED_WPM = (40, 60, 80)

    def __init__(self, text, wpm, repeat=False):
        if wpm not in self.SUPPORTED_WPM:
            raise ValueError("wpm must be 40, 60, or 80")
        if not text:
            raise ValueError("text must not be empty")
        self.text = text
        self.interval_ms = 60000.0 / (wpm * 5)
        self.repeat = repeat
        self.sequence = 0
        self.index = 0
        self.next_due_ms = 0.0

    def produce_due(self, now_ms, queue):
        produced = 0
        while now_ms >= self.next_due_ms:
            if self.index >= len(self.text):
                if not self.repeat:
                    break
                self.index = 0
            value = self.text[self.index]
            queue.put(KeyEvent(self.sequence, "insert", value))
            self.sequence += 1
            self.index += 1
            self.next_due_ms += self.interval_ms
            produced += 1
        return produced
