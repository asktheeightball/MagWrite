"""Measured end-to-end latency for one live typing session.

Host-safe, bounded, and entirely passive: it observes the scheduler and never
influences a single scheduling decision. Removing it would change no behaviour.

Why this exists
---------------

The adaptive pacing policy in ``pacing`` is an argument that typing should feel
better. An argument is not evidence. The physical run for this phase has to
produce *numbers*, and the completed USB-keyboard run cannot supply a baseline
for comparison because its records carry no timestamps at all — it logged the
order of events, not when they happened.

So this module timestamps the chain a writer actually experiences:

    keypress -> viewport transmitted -> refresh started -> refresh completed

Each metric is anchored to the *first keypress that made the display stale*
since the last transmission, because that is the keystroke whose result the
writer is waiting to see. A later keystroke in the same burst has waited less,
and averaging it in would flatter the result.

What each metric means
----------------------

``keypress_to_send``
    First stale-making keypress to the viewport frame leaving the Fruit Jam.
    This is the part the pacing policy owns.

``keypress_to_refresh_start``
    Adds the MagTag accepting the frame and beginning to drive the panel.

``keypress_to_refresh_complete``
    Adds the panel's own refresh time. This is the number that corresponds to
    "when could the writer read it".

Samples are additionally split by the pacing regime that released them, so the
two cases the phase is really about can be reported separately:

* ``CAUGHT_UP`` samples answer "pause to catch-up transmission";
* ``SUSTAINED`` samples answer "maximum visible lag during sustained typing".

Bounded by construction: at most ``capacity`` frames are tracked at once, and a
frame is discarded once its refresh completes. Aggregates are running values,
so nothing grows with session length.
"""

REFRESH_STARTED = 7
REFRESH_COMPLETED = 8
DISPLAY_CAUGHT_UP = 9

TRACKING_CAPACITY = 128


class Series:
    """Count, minimum, maximum and mean of one metric, without a sample list."""

    __slots__ = ("count", "minimum", "maximum", "total")

    def __init__(self):
        self.count = 0
        self.minimum = None
        self.maximum = None
        self.total = 0.0

    def add(self, value):
        self.count += 1
        self.total += value
        if self.minimum is None or value < self.minimum:
            self.minimum = value
        if self.maximum is None or value > self.maximum:
            self.maximum = value

    @property
    def mean(self):
        if not self.count:
            return None
        return self.total / self.count

    def describe(self, places=3):
        if not self.count:
            return {"count": 0, "min": None, "mean": None, "max": None}
        return {
            "count": self.count,
            "min": round(self.minimum, places),
            "mean": round(self.mean, places),
            "max": round(self.maximum, places),
        }


class LatencyRecorder:
    """Passive observer of the keypress-to-visible chain."""

    def __init__(self, capacity=TRACKING_CAPACITY):
        if capacity < 1:
            raise ValueError("latency capacity must be positive")
        self.capacity = capacity
        self.first_input_since_send = None
        self.last_input_at = None
        self.pending = {}
        self.overflowed = 0
        self.to_send = Series()
        self.to_refresh_start = Series()
        self.to_refresh_complete = Series()
        self.by_reason = {}
        self.sends = 0
        self.pauses_observed = 0
        self.frames_after_pause = 0

    # ------------------------------------------------------------ observation

    def note_input(self, now, quiet_before=False):
        """One input event was applied to the authoritative document.

        ``quiet_before`` marks the first keystroke after the writer had stopped,
        which is what makes "frame count under several short pauses" countable
        rather than a matter of interpretation.
        """
        if self.first_input_since_send is None:
            self.first_input_since_send = now
        if quiet_before:
            self.pauses_observed += 1
        self.last_input_at = now

    def note_sent(self, now, revision, reason=None):
        anchor = self.first_input_since_send
        self.sends += 1
        if anchor is not None:
            elapsed = now - anchor
            self.to_send.add(elapsed)
            series = self.by_reason.get(reason)
            if series is None:
                series = self.by_reason[reason] = Series()
            series.add(elapsed)
        if len(self.pending) >= self.capacity:
            # Bounded: drop the oldest rather than grow. A dropped frame loses
            # its refresh timings only; its send timing is already aggregated.
            self.overflowed += 1
            oldest = min(self.pending)
            del self.pending[oldest]
        if anchor is not None:
            self.pending[revision] = (anchor, now, reason)
        self.first_input_since_send = None

    def note_status(self, now, message_type, revision):
        record = self.pending.get(revision)
        if record is None:
            return
        anchor = record[0]
        if message_type == REFRESH_STARTED:
            self.to_refresh_start.add(now - anchor)
        elif message_type in (REFRESH_COMPLETED, DISPLAY_CAUGHT_UP):
            self.to_refresh_complete.add(now - anchor)
            del self.pending[revision]

    def note_frame_after_pause(self):
        self.frames_after_pause += 1

    # ----------------------------------------------------------------- summary

    def summary(self):
        record = {
            "latency_keypress_to_send": self.to_send.describe(),
            "latency_keypress_to_refresh_start":
                self.to_refresh_start.describe(),
            "latency_keypress_to_refresh_complete":
                self.to_refresh_complete.describe(),
            "latency_sends": self.sends,
            "latency_pauses_observed": self.pauses_observed,
            "latency_frames_after_pause": self.frames_after_pause,
            "latency_tracking_overflows": self.overflowed,
        }
        for reason, series in sorted(
            self.by_reason.items(), key=lambda item: str(item[0])
        ):
            name = reason if reason is not None else "FORCED"
            record["latency_keypress_to_send_" + name.lower()] = (
                series.describe()
            )
        return record
