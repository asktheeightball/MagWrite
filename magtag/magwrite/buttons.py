"""The MagTag's four front buttons, debounced into normalized actions.

Host-safe. Every pin is injected as a plain callable returning ``True`` when the
button is physically down, so every path here — including every bounce, every
held key, and every simultaneous press — runs under CPython host tests with no
CircuitPython import. The CircuitPython half is six lines in
``dev_display_runtime.py`` and owns nothing but ``DigitalInOut``.

What the MagTag is allowed to decide
------------------------------------

Only that a button went down. It emits a **normalized action** — ``MENU``,
``UP``, ``DOWN``, ``SELECT`` — and a monotonic ordinal, and it stops there. It
does not know what state the shell is in, which menu item is selected, whether a
document is open, or what any of the four actions will do; the Fruit Jam decides
all of that, because the Fruit Jam is the sole owner of shell and document state
and a second opinion about where the writer is would eventually disagree with
the first.

That is why the action names are ``UP`` and ``DOWN`` rather than ``B`` and
``C``. A raw button identity would force the Fruit Jam to know the panel's
physical layout, and a semantic one that meant "next journal entry" would be the
MagTag deciding product behaviour. "The writer asked to move down" is the
narrowest honest thing this board knows.

Debouncing, and why it is stability rather than a lockout
---------------------------------------------------------

A mechanical contact chatters for a few milliseconds on both edges. The rule
here is that a **reading must be stable for ``DEBOUNCE_SECONDS`` before it is
believed at all**, which rejects chatter on the release edge as well as the
press edge. A press-and-lock-out scheme only handles the press edge, and the
release bounce then arrives after the lockout expired and reads as a second
press — which is precisely the duplicate this phase was asked to prevent.

One press produces exactly one event. A held button does **not** repeat: this is
a menu of four items on a panel that takes about a second to redraw, so auto
repeat could only ever overshoot something the writer cannot yet see.

``MINIMUM_INTERVAL_SECONDS`` is a second, independent guard on top of that:
the same action is refused twice inside it however clean the edges looked. It is
deliberately close to one panel refresh, so the writer never moves the selection
twice for one visible frame.

Bounded, like everything on the return channel
----------------------------------------------

``poll`` returns at most one event per button per call, so the list it returns
can never be longer than the number of buttons. It allocates nothing that
persists and counts everything it refuses.
"""

MENU = "MENU"
UP = "UP"
DOWN = "DOWN"
SELECT = "SELECT"
ACTIONS = (MENU, UP, DOWN, SELECT)

# The wire codes. Fixed for the same reason the message types are fixed: a
# renumbering is a protocol change, not an edit. ``button_input`` on the Fruit
# Jam carries the identical table and a host test asserts the two agree.
ACTION_CODES = {MENU: 1, UP: 2, DOWN: 3, SELECT: 4}

# Long enough to outlast the contact chatter on these switches, short enough to
# be invisible to a person. A tap is tens of milliseconds of contact; this is
# well inside that, so no deliberate press is ever missed.
DEBOUNCE_SECONDS = 0.025
# One panel refresh is roughly a second. Two presses of the same button closer
# together than this are two presses the writer made before seeing the first one
# land, so the second is refused rather than queued.
MINIMUM_INTERVAL_SECONDS = 0.25


class ButtonPad:
    """Four physical buttons, one debounced normalized action stream."""

    def __init__(self, buttons, debounce_seconds=DEBOUNCE_SECONDS,
                 minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS):
        """``buttons`` is a sequence of ``(action, is_pressed)`` pairs."""
        if not buttons:
            raise ValueError("a button pad needs at least one button")
        if debounce_seconds <= 0 or minimum_interval_seconds < 0:
            raise ValueError("button intervals must be positive")
        self.debounce_seconds = debounce_seconds
        self.minimum_interval_seconds = minimum_interval_seconds
        self.buttons = []
        for action, is_pressed in buttons:
            if action not in ACTIONS:
                raise ValueError("unknown button action: " + str(action))
            self.buttons.append((action, is_pressed))
        # Per button, in the same order: the believed state, the last raw
        # reading, when that raw reading was first seen, and when this action
        # last produced an event.
        self.settled = [False] * len(self.buttons)
        self.candidate = [False] * len(self.buttons)
        self.candidate_since = [0.0] * len(self.buttons)
        self.last_event_at = [None] * len(self.buttons)
        self.ordinal = 0
        self.presses = 0
        self.bounces_rejected = 0
        self.repeats_suppressed = 0

    def poll(self, now):
        """Return the actions whose buttons went down since the last call.

        A list of ``(action, ordinal, pressed_ms)``, at most one entry per
        button. Empty on the overwhelming majority of calls, which is the
        expected case: this runs inside the display loop.
        """
        events = []
        for index, (action, is_pressed) in enumerate(self.buttons):
            raw = bool(is_pressed())
            if raw != self.candidate[index]:
                # The reading changed. Start its clock over; a bounce never
                # survives to be believed.
                if self.candidate[index] != self.settled[index]:
                    self.bounces_rejected += 1
                self.candidate[index] = raw
                self.candidate_since[index] = now
                continue
            if raw == self.settled[index]:
                continue
            if now - self.candidate_since[index] < self.debounce_seconds:
                continue
            # Stable long enough to believe. Both edges are adopted; only the
            # press edge is an event.
            self.settled[index] = raw
            if not raw:
                continue
            previous = self.last_event_at[index]
            if (
                previous is not None
                and now - previous < self.minimum_interval_seconds
            ):
                self.repeats_suppressed += 1
                continue
            self.last_event_at[index] = now
            self.ordinal += 1
            self.presses += 1
            events.append((action, self.ordinal, int(now * 1000) & 0xFFFFFFFF))
        return events

    def summary(self):
        return {
            "button_presses": self.presses,
            "button_bounces_rejected": self.bounces_rejected,
            "button_repeats_suppressed": self.repeats_suppressed,
            "button_ordinal": self.ordinal,
        }
