"""Bounded USB keyboard connection state machine.

Host-safe. An open attempt may only be made once per ``retry_interval`` seconds,
and — for a guarded harness — only ``max_attempts`` times in total. Once attempts
are exhausted the machine latches ``ERROR`` and the harness fails closed rather
than spinning.

``max_attempts=None``: the standalone appliance — V1.6
------------------------------------------------------

The attempt *count* is removed, and only for the standalone runtime. The rate
bound is untouched, so this is not the unbounded reconnect loop the harnesses
refuse: it is still at most one open attempt per second, forever, which costs one
bounded USB enumeration on a board that has nothing else to do.

The count had to go because it made "no keyboard yet" terminal. Thirty attempts
at one second each is thirty seconds, after which ``ERROR`` latches and
:meth:`retry_due` refuses every further attempt for the life of the session — so
a device powered on before its keyboard was plugged in would never see that
keyboard, and the only cure was a reset. On a bench with a console that is a
diagnostic; on a writing appliance with one power cable it is a device that does
not work. A writer who plugs the keyboard in afterwards is not a fault condition,
and thirty seconds is not a deadline anybody agreed to.

Nothing about the harness path changes: ``max_attempts`` keeps its default and
every guarded run keeps the exact behaviour it was verified with.
"""

NO_DEVICE = "NO_DEVICE"
ENUMERATING = "ENUMERATING"
READY = "READY"
DISCONNECTED = "DISCONNECTED"
ERROR = "ERROR"
STATES = (NO_DEVICE, ENUMERATING, READY, DISCONNECTED, ERROR)

RETRY_INTERVAL_SECONDS = 1.0
MAX_OPEN_ATTEMPTS = 30


class UsbDeviceState:
    def __init__(
        self, now=0.0, log=None, retry_interval=RETRY_INTERVAL_SECONDS,
        max_attempts=MAX_OPEN_ATTEMPTS,
    ):
        if retry_interval <= 0:
            raise ValueError("retry bounds must be positive")
        if max_attempts is not None and max_attempts < 1:
            raise ValueError("retry bounds must be positive")
        self.log = log
        self.retry_interval = retry_interval
        self.max_attempts = max_attempts
        self.state = NO_DEVICE
        self.entered_at = now
        self.last_attempt_at = None
        self.open_attempts = 0
        self.connects = 0
        self.disconnects = 0
        self.errors = 0
        self.transitions = 0
        self.last_reason = None

    @property
    def ready(self):
        return self.state == READY

    @property
    def exhausted(self):
        if self.max_attempts is None:
            # Standalone: there is no attempt budget to exhaust. The device
            # keeps offering to find a keyboard for as long as it has power.
            return False
        return self.open_attempts >= self.max_attempts

    def _enter(self, state, now, reason=None):
        if state not in STATES:
            raise ValueError("unknown USB device state: " + str(state))
        if state == self.state and reason is None:
            return self.state
        previous = self.state
        self.state = state
        self.entered_at = now
        self.transitions += 1
        self.last_reason = reason
        if self.log is not None:
            self.log({
                "event": "usb_keyboard_state",
                "from": previous, "to": state, "reason": reason,
                "open_attempts": self.open_attempts,
            })
        return state

    def retry_due(self, now):
        """True when another bounded open attempt is permitted right now."""
        if self.state in (READY, ERROR):
            return False
        if self.exhausted:
            return False
        if self.last_attempt_at is None:
            return True
        return now - self.last_attempt_at >= self.retry_interval

    def begin_attempt(self, now):
        """Record one bounded open attempt and enter ``ENUMERATING``."""
        self.open_attempts += 1
        self.last_attempt_at = now
        if self.max_attempts is None:
            reason = "open attempt %d, unbounded" % (self.open_attempts,)
        else:
            reason = "open attempt %d of %d" % (
                self.open_attempts, self.max_attempts)
        return self._enter(ENUMERATING, now, reason=reason)

    def opened(self, now):
        self.connects += 1
        return self._enter(READY, now)

    def not_found(self, now, reason="no device attached"):
        if self.exhausted:
            return self.failed(now, "open attempts exhausted: " + reason)
        return self._enter(NO_DEVICE, now, reason=reason)

    def disconnected(self, now, reason="device disconnected"):
        self.disconnects += 1
        self.last_attempt_at = None
        return self._enter(DISCONNECTED, now, reason=reason)

    def failed(self, now, reason):
        self.errors += 1
        return self._enter(ERROR, now, reason=reason)

    def describe(self):
        return {
            "state": self.state,
            "open_attempts": self.open_attempts,
            "max_open_attempts": self.max_attempts,
            "connects": self.connects,
            "disconnects": self.disconnects,
            "errors": self.errors,
            "transitions": self.transitions,
            "last_reason": self.last_reason,
        }
