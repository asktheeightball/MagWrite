"""MagTag button events, received and made safe to act on. V1.5.

Host-safe. The MagTag decides only that a button went down and gives the press a
monotonic ordinal; this module is where the Fruit Jam decides whether to believe
it. Nothing here knows what an action *means* — that is the shell's, and only the
shell's, because the Fruit Jam is the sole owner of shell and document state.

Three defences, and each exists because of a different failure
--------------------------------------------------------------

1. **An unknown action code is refused, not guessed.** A code this build does not
   recognise is a MagTag running different firmware, and acting on a guess would
   be the display board choosing a product behaviour;
2. **an ordinal at or below the highest one already accepted is a duplicate.**
   The transport's own sequence numbering already rejects a replayed *frame*, but
   a resynchronisation after line noise can legitimately redeliver one, and a
   press applied twice moves the selection two items past what the writer saw;
3. **the queue is bounded and drops the oldest.** A writer leaning on a button
   while the panel is a second behind must not be able to grow a backlog that
   plays out after they stop. The newest presses are the writer's most recent
   intention, exactly as the shell's single pending request is.

Every refusal is counted. A button press that vanished silently would be
indistinguishable from a broken switch, and the two want very different fixes.
"""

MENU = "MENU"
UP = "UP"
DOWN = "DOWN"
SELECT = "SELECT"
ACTIONS = (MENU, UP, DOWN, SELECT)

# The wire codes, identical to ``magtag/magwrite/buttons.py``. Two copies for the
# same reason the protocol constants have two copies -- the boards share no
# import -- and a host test asserts the two tables agree.
ACTION_CODES = {MENU: 1, UP: 2, DOWN: 3, SELECT: 4}
ACTION_FOR_CODE = {code: action for action, code in ACTION_CODES.items()}

# Four buttons and a panel that trails by about a second: a writer cannot get
# meaningfully further ahead than this, and anything beyond it is a stuck switch
# rather than an intention.
MAX_PENDING = 8


class ButtonInbox:
    """Bounded, duplicate-suppressing intake for normalized button events."""

    def __init__(self, capacity=MAX_PENDING, log=None):
        if capacity < 1:
            raise ValueError("the button inbox needs a positive capacity")
        self.capacity = capacity
        self.log = log
        self.pending = []
        self.highest_ordinal = 0
        self.received = 0
        self.accepted = 0
        self.duplicates = 0
        self.unknown = 0
        self.dropped = 0
        self.applied = 0
        self.ignored = 0
        self.maximum_depth = 0

    def offer(self, fields):
        """Take one decoded ``BUTTON_EVENT`` payload. Returns the action or None."""
        self.received += 1
        action = ACTION_FOR_CODE.get(fields.get("action_code"))
        if action is None:
            self.unknown += 1
            self._log({"event": "button_event_unknown",
                       "action_code": fields.get("action_code")})
            return None
        ordinal = fields.get("ordinal", 0)
        if ordinal <= self.highest_ordinal:
            self.duplicates += 1
            self._log({"event": "button_event_duplicate", "action": action,
                       "ordinal": ordinal, "highest": self.highest_ordinal})
            return None
        self.highest_ordinal = ordinal
        if len(self.pending) >= self.capacity:
            # Oldest first: a backlog is stale intention, and the writer's most
            # recent press is the one they still mean.
            self.pending.pop(0)
            self.dropped += 1
            self._log({"event": "button_event_dropped", "capacity": self.capacity})
        self.pending.append((action, ordinal))
        self.accepted += 1
        if len(self.pending) > self.maximum_depth:
            self.maximum_depth = len(self.pending)
        self._log({"event": "button_event_received", "action": action,
                   "ordinal": ordinal, "pressed_ms": fields.get("pressed_ms"),
                   "queue_depth": len(self.pending)})
        return action

    def take(self):
        """Remove and return the oldest pending action, or ``None``."""
        if not self.pending:
            return None
        action, ordinal = self.pending.pop(0)
        self.applied += 1
        return action, ordinal

    def note_ignored(self):
        """An accepted press the shell had no use for in its current state."""
        self.ignored += 1

    def __len__(self):
        return len(self.pending)

    def _log(self, record):
        if self.log is not None:
            self.log(record)

    def summary(self):
        return {
            "button_events_received": self.received,
            "button_events_accepted": self.accepted,
            "button_events_applied": self.applied,
            "button_events_ignored": self.ignored,
            "button_events_duplicate": self.duplicates,
            "button_events_unknown": self.unknown,
            "button_events_dropped": self.dropped,
            "button_queue_maximum_depth": self.maximum_depth,
        }
