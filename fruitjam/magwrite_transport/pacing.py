"""Adaptive display pacing: when the newest pending viewport may be sent.

Host-safe, and the single home for every *display* timing constant, exactly as
``keyboard_repeat`` is the single home for every *keyboard* timing constant. A
physical run must never have two disagreeing sources of truth, so nothing
downstream may hard-code a send interval.

The values below are chosen from measured panel behaviour, not from taste. The
guarded run recorded in ``docs/FRUITJAM_USB_KEYBOARD_TEST.md`` measured, on the
real UC8151D MagTag:

    full refresh      3500 ms   (once, at start)
    partial refresh    873 ms   fastest observed
    partial refresh   1122 ms   slowest observed
    partial refresh   ~1050 ms  mean over 48 refreshes

So the panel itself cannot show more than roughly one new state per second. Any
policy that transmits faster than that is not producing visible updates; it is
producing frames the MagTag has to queue or drop.

Why the fixed 2.6 s interval it replaces was wrong
--------------------------------------------------

The old policy was a single floor measured from the previous send. It had one
virtue — it fits the authorised refresh budget — and one serious defect: it
applied the same floor to the two cases a writer actually perceives.

* **Typing begins.** The first character of a session, or of a paragraph after
  a pause, waited out the whole interval before anything appeared.
* **Typing stops.** The writer stops to read, and the last thing they typed sat
  unsent for up to the whole interval while the panel was completely idle.

Both are pure latency: in each case the MagTag was free and the newest state was
already built. The panel was not the bottleneck; the fixed number was.

The policy
----------

Three gates, checked in order, on the *newest* pending viewport only:

1. **Busy gate.** Never transmit while the MagTag has an unfinished refresh.
   With ``SEND_WINDOW`` of 1 this is absolute: at most one viewport is ever in
   flight, so a refresh is never started while the panel is busy, and whatever
   is sent next is the newest state at the moment the panel came free rather
   than something built and queued while it was working.

2. **Coalescing gate.** A pending change must have existed for at least
   ``COALESCE_SECONDS`` before it may be sent. At 60 WPM a keystroke arrives
   about every 100 ms, so this window always contains several keystrokes and a
   single keypress can never earn its own frame.

3. **Interval gate**, whose floor depends on what the writer is doing:

   * **Onset** — nothing has ever been sent. Send as soon as gates 1 and 2
     allow, so the first text appears in about ``COALESCE_SECONDS`` instead of
     a full interval.
   * **Caught up** — no input for ``QUIET_SECONDS``. The writer has paused, so
     the floor drops to ``CAUGHT_UP_MIN_SEND_SECONDS``, just past the slowest
     measured partial refresh. This is the catch-up path, and it costs at most
     one frame per pause: once the pending state is sent there is nothing left
     pending until typing resumes.
   * **Sustained** — input is still arriving. The floor is
     ``SUSTAINED_MIN_SEND_SECONDS``, the interval the guarded run already
     proved fits the authorised partial-refresh ceiling. The display keeps
     advancing during a long burst rather than stalling until the end of it.

The resulting worst case for a change being *transmitted* is given by
``maximum_pending_seconds``: the sustained floor or an in-flight refresh the
busy gate has to wait out, whichever is longer, plus the coalescing window. Add
one partial refresh for when it becomes physically visible. That worst case only
applies while the writer is still typing — the moment they pause, the catch-up
path takes over and the floor drops to a single refresh.

This module decides *when*. It never decides *what*: coalescing to the newest
state, revision numbering, hashing, acknowledgement, and the fail-closed
ceilings all stay where they already are.
"""

# ------------------------------------------------------- measured panel facts

# From the guarded live run; see the module docstring. Recorded here so a later
# phase re-measuring the panel has one place to update and one place to compare.
MEASURED_FULL_REFRESH_SECONDS = 3.5
MEASURED_PARTIAL_REFRESH_FASTEST_SECONDS = 0.873
MEASURED_PARTIAL_REFRESH_SLOWEST_SECONDS = 1.122
MEASURED_PARTIAL_REFRESH_MEAN_SECONDS = 1.05

# ------------------------------------------------------------ policy constants

# At most one viewport in flight, so a refresh is never started while the panel
# is busy and a queued frame can never be obsolete by the time it is rendered.
SEND_WINDOW = 1

# Long enough to contain several keystrokes at any human typing rate, short
# enough to be imperceptible at the start of a burst.
COALESCE_SECONDS = 0.25

# Longer than an inter-word hesitation, shorter than a real pause to read.
QUIET_SECONDS = 0.6

# Just past the slowest measured partial refresh, so the catch-up path can never
# ask the panel for a refresh sooner than the panel could have finished one.
CAUGHT_UP_MIN_SEND_SECONDS = 1.3

# The interval the guarded run proved fits the authorised partial-refresh
# ceiling for a full-length session of continuous typing.
SUSTAINED_MIN_SEND_SECONDS = 2.6

# The policy's own worst-case contribution to how long a change stays pending,
# which applies only while the writer is still typing. It is *not* the whole
# story: the busy gate can also hold a change while the panel finishes a refresh
# it already started, and a full refresh is far longer than this floor. Use
# ``maximum_pending_seconds`` for the real bound rather than this constant alone.
MAX_VISIBLE_LAG_SECONDS = SUSTAINED_MIN_SEND_SECONDS


def maximum_pending_seconds(longest_refresh_seconds):
    """Worst case a change can sit unsent, given the longest possible refresh.

    Two things can hold a pending change, and only the longer of them applies:
    the sustained interval floor, or an in-flight refresh the busy gate must
    wait out. Coalescing adds its window on top, because a change that arrives
    at the very start of one still waits it out.
    """
    return (
        max(SUSTAINED_MIN_SEND_SECONDS, longest_refresh_seconds)
        + COALESCE_SECONDS
    )

REASON_BUSY = "BUSY"
REASON_NOTHING_PENDING = "NOTHING_PENDING"
REASON_COALESCING = "COALESCING"
REASON_ONSET = "ONSET"
REASON_CAUGHT_UP = "CAUGHT_UP"
REASON_SUSTAINED = "SUSTAINED"
REASON_WAITING = "WAITING"

SENDING_REASONS = (REASON_ONSET, REASON_CAUGHT_UP, REASON_SUSTAINED)


class DisplayPacer:
    """Adaptive send policy for one live session.

    Pure timing state. It owns no viewport, revision, hash, or frame, and it is
    told about the world through four notifications, so every branch is
    reachable from a host test with an ordinary float clock.
    """

    def __init__(
        self, coalesce_seconds=COALESCE_SECONDS, quiet_seconds=QUIET_SECONDS,
        caught_up_min_send_seconds=CAUGHT_UP_MIN_SEND_SECONDS,
        sustained_min_send_seconds=SUSTAINED_MIN_SEND_SECONDS,
    ):
        if coalesce_seconds < 0 or quiet_seconds <= 0:
            raise ValueError("pacing windows must be positive")
        if caught_up_min_send_seconds <= 0 or sustained_min_send_seconds <= 0:
            raise ValueError("pacing intervals must be positive")
        if caught_up_min_send_seconds > sustained_min_send_seconds:
            raise ValueError(
                "the catch-up floor must not exceed the sustained floor"
            )
        self.coalesce_seconds = coalesce_seconds
        self.quiet_seconds = quiet_seconds
        self.caught_up_min_send_seconds = caught_up_min_send_seconds
        self.sustained_min_send_seconds = sustained_min_send_seconds
        self.pending_since = None
        self.last_input_at = None
        self.last_send_at = None
        self.onset_sends = 0
        self.caught_up_sends = 0
        self.sustained_sends = 0
        self.forced_sends = 0
        self.maximum_pending_seconds = 0.0

    # ------------------------------------------------------------ notifications

    def note_input(self, now):
        """An input event was applied to the authoritative document."""
        self.last_input_at = now

    def note_pending(self, now):
        """The built viewport differs from the last one transmitted.

        The timestamp is kept from the *first* moment the display fell behind,
        not the newest change, so the coalescing window bounds visible lag
        rather than sliding forward with every keystroke.
        """
        if self.pending_since is None:
            self.pending_since = now

    def clear_pending(self):
        """The built viewport matches what was last transmitted."""
        self.pending_since = None

    def note_sent(self, now, reason=None):
        self.last_send_at = now
        if self.pending_since is not None:
            self.maximum_pending_seconds = max(
                self.maximum_pending_seconds, now - self.pending_since
            )
        self.pending_since = None
        if reason == REASON_ONSET:
            self.onset_sends += 1
        elif reason == REASON_CAUGHT_UP:
            self.caught_up_sends += 1
        elif reason == REASON_SUSTAINED:
            self.sustained_sends += 1
        else:
            self.forced_sends += 1

    # ------------------------------------------------------------------ policy

    def quiet(self, now):
        """True when the writer has stopped typing for long enough to catch up."""
        if self.last_input_at is None:
            return True
        return now - self.last_input_at >= self.quiet_seconds

    def floor(self, now):
        """The interval that applies right now, in seconds."""
        if self.quiet(now):
            return self.caught_up_min_send_seconds
        return self.sustained_min_send_seconds

    def decide(self, now, busy):
        """Return why the newest pending viewport may or may not be sent."""
        if busy:
            return REASON_BUSY
        if self.pending_since is None:
            return REASON_NOTHING_PENDING
        if now - self.pending_since < self.coalesce_seconds:
            return REASON_COALESCING
        if self.last_send_at is None:
            return REASON_ONSET
        if now - self.last_send_at < self.floor(now):
            return REASON_WAITING
        return REASON_CAUGHT_UP if self.quiet(now) else REASON_SUSTAINED

    def due(self, now, busy):
        return self.decide(now, busy) in SENDING_REASONS

    # ----------------------------------------------------------------- summary

    def summary(self):
        return {
            "pacing_onset_sends": self.onset_sends,
            "pacing_caught_up_sends": self.caught_up_sends,
            "pacing_sustained_sends": self.sustained_sends,
            "pacing_forced_sends": self.forced_sends,
            "pacing_maximum_pending_seconds": round(
                self.maximum_pending_seconds, 3
            ),
            "pacing_coalesce_seconds": self.coalesce_seconds,
            "pacing_quiet_seconds": self.quiet_seconds,
            "pacing_caught_up_min_send_seconds": self.caught_up_min_send_seconds,
            "pacing_sustained_min_send_seconds": self.sustained_min_send_seconds,
        }
