"""Separates the arming wait from the measured test run.

The MagTag is armed and reset first, then reports ready, and only then is the
Fruit Jam armed and reset. That ordering is deliberate, but it means the MagTag
sits idle for however long the operator takes. Charging that wait to the test
budget makes a run fail for reasons that have nothing to do with the test, so
the idle wait gets its own separate and far more generous bound.
"""


ARMING_TIMEOUT = "editor display arming timeout"
RUN_TIMEOUT = "editor display test timeout"


class RunClock:
    """Two-phase deadline: an arming wait, then the measured run."""

    def __init__(self, monotonic, arming_timeout, run_timeout):
        self.monotonic = monotonic
        self.arming_timeout = arming_timeout
        self.run_timeout = run_timeout
        self.armed_at = monotonic()
        self.run_started_at = None

    @property
    def running(self):
        return self.run_started_at is not None

    def start_run(self):
        """Begin the measured run. Idempotent; returns the arming wait."""
        if self.run_started_at is None:
            self.run_started_at = self.monotonic()
        return self.run_started_at - self.armed_at

    def elapsed(self):
        """Seconds inside the current phase."""
        base = self.run_started_at if self.running else self.armed_at
        return self.monotonic() - base

    def expired(self):
        """Return the stop reason for the current phase, or ``None``."""
        limit = self.run_timeout if self.running else self.arming_timeout
        if self.elapsed() > limit:
            return RUN_TIMEOUT if self.running else ARMING_TIMEOUT
        return None
