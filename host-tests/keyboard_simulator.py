"""Host simulation of a real USB keyboard driving the live typing session.

Nothing here models physical e-paper or physical USB. It proves the HID
translation, the input adapter, the scheduling order, the protocol, and the
acknowledgement lifecycle, using the same real code the device runs.

``FakeKeyboardBackend`` replays a scripted list of raw 8-byte boot reports, which
is exactly what the real backend hands back, so the adapter under test never
knows it is not attached to hardware.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if os.path.join(ROOT, "magtag") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "magtag"))
if os.path.join(ROOT, "fruitjam") not in sys.path:
    sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.ack_scheduler import AckDisplayScheduler
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import FrameParser as InputParser
from magwrite.viewport_renderer import render_viewport
from magwrite_transport.hid_keymap import (
    MODIFIER_LEFT_SHIFT, NAMED_USAGES, PRINTABLE_USAGES, USAGE_ESCAPE,
)
from magwrite_transport.live_session import LiveTypingSession
from magwrite_transport.usb_hid_descriptors import (
    UsbKeyboardDisconnected, UsbKeyboardNotFound,
)
from magwrite_transport.usb_keyboard_adapter import UsbKeyboardAdapter

STEP_SECONDS = 0.005
FULL_REFRESH_SECONDS = 3.6
PARTIAL_REFRESH_SECONDS = 0.97

# The exact configuration descriptor read from the receiver used for this phase
# (0x36B0/0x3002, "RDMCTMZT Wireless 2.4G Dongle"): three HID interfaces, of
# which only interface 0 is a boot-protocol keyboard.
REAL_CONFIGURATION_DESCRIPTOR = bytes.fromhex(
    "09026200030100A0FA"
    "09040000010301010009211101000122440007058103080001"
    "090401000203000000092111010001222200070582032000010705030320000109"
    "040200020300000009211101000122D3000705840340000107050503400001"
)

RELEASE_REPORT = bytes(8)

# Reverse lookup: character -> (usage, needs_shift).
_CHARACTER_USAGES = {}
for _usage, (_unshifted, _shifted) in PRINTABLE_USAGES.items():
    if _unshifted is not None and _unshifted not in _CHARACTER_USAGES:
        _CHARACTER_USAGES[_unshifted] = (_usage, False)
    if _shifted is not None and _shifted not in _CHARACTER_USAGES:
        _CHARACTER_USAGES[_shifted] = (_usage, True)
del _usage, _unshifted, _shifted

_KIND_USAGES = {}
for _usage, _kind in NAMED_USAGES.items():
    _KIND_USAGES.setdefault(_kind, _usage)
del _usage, _kind


def report(modifier=0, usages=()):
    """Build one boot keyboard report."""
    raw = bytearray(8)
    raw[0] = modifier
    for index, usage in enumerate(usages[:6]):
        raw[2 + index] = usage
    return bytes(raw)


def press_release(usage, shift=False):
    """The two reports a single keystroke produces."""
    modifier = MODIFIER_LEFT_SHIFT if shift else 0
    return [report(modifier, (usage,)), report(modifier)]


def type_characters(text):
    """Expand text into the report stream a person typing it would produce."""
    reports = []
    for character in text:
        if character == "\n":
            reports.extend(press_release(_KIND_USAGES["ENTER"]))
            continue
        usage, shift = _CHARACTER_USAGES[character]
        reports.extend(press_release(usage, shift))
    return reports


def press_kind(kind, times=1):
    """Reports for pressing a named editing key ``times`` times."""
    reports = []
    for _ in range(times):
        reports.extend(press_release(_KIND_USAGES[kind]))
    return reports


def finish():
    """The Escape keystroke that ends a live run."""
    return press_release(USAGE_ESCAPE)


class SimulatedClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class SimulatedPanel:
    """Models one refresh in flight with a measured busy duration."""

    def __init__(self, clock, full=FULL_REFRESH_SECONDS,
                 partial=PARTIAL_REFRESH_SECONDS):
        self.clock = clock
        self.full_seconds = full
        self.partial_seconds = partial
        self.busy_until = None
        self.starts = []
        self.maximum_concurrent = 0

    def begin_refresh(self, framebuffer, full=False):
        if self.busy_until is not None:
            raise RuntimeError("second physical refresh in flight")
        self.busy_until = self.clock.now + (
            self.full_seconds if full else self.partial_seconds
        )
        self.maximum_concurrent = max(self.maximum_concurrent, 1)
        self.starts.append(full)
        return full

    def is_busy(self):
        if self.busy_until is None:
            return False
        if self.clock.now < self.busy_until:
            return True
        self.busy_until = None
        return False


class FakeKeyboardBackend:
    """Replays scripted raw boot reports with a controllable release rate."""

    def __init__(self, reports=(), descriptor=None, reports_per_poll=1,
                 open_error=None, disconnect_after=None, clock=None,
                 interval_seconds=0.0):
        self.reports = list(reports)
        # A human types at a rate the panel cannot match. Pacing the release of
        # reports against the simulated clock is what makes the host prediction
        # of viewport frames and refreshes comparable to a physical run; with no
        # pacing the whole script arrives faster than one refresh and everything
        # coalesces into a handful of frames.
        self.clock = clock
        self.interval_seconds = interval_seconds
        self.next_release = 0.0
        self.descriptor = descriptor if descriptor is not None else {
            "vendor_id": "36B0", "product_id": "3002", "interface": 0,
            "endpoint": 0x81, "protocol": "boot_keyboard",
        }
        self.reports_per_poll = reports_per_poll
        self.open_error = open_error
        self.disconnect_after = disconnect_after
        self.opens = 0
        self.closes = 0
        self.reads = 0
        self.delivered = 0
        self.opened = False
        self._served_this_poll = 0

    @property
    def drained(self):
        return not self.reports

    def open(self):
        self.opens += 1
        if self.open_error is not None:
            raise self.open_error
        self.opened = True
        return self.descriptor

    def close(self):
        self.closes += 1
        self.opened = False

    def read_report(self):
        self.reads += 1
        if self.disconnect_after is not None and self.delivered >= self.disconnect_after:
            self.disconnect_after = None
            raise UsbKeyboardDisconnected("simulated disconnect")
        if not self.reports:
            return None
        if self.clock is not None and self.interval_seconds:
            now = self.clock()
            if now < self.next_release:
                return None
            self.next_release = now + self.interval_seconds
        # One report per poll by default, so the session's cooperative loop has
        # to run between keystrokes exactly as it does on hardware.
        if self._served_this_poll >= self.reports_per_poll:
            self._served_this_poll = 0
            return None
        self._served_this_poll += 1
        self.delivered += 1
        return self.reports.pop(0)


class KeyboardLink:
    """Wires one live Fruit Jam session to one display-only MagTag scheduler."""

    # Roughly 60 words per minute: five characters per word, two reports per
    # keystroke, so one report every 100 ms of simulated time.
    HUMAN_REPORT_INTERVAL_SECONDS = 0.1

    def __init__(self, reports=(), log=None, render=render_viewport, panel=None,
                 backend=None, status_queue_capacity=32, adapter_options=None,
                 typing_interval_seconds=0.0, **session_options):
        self.clock = SimulatedClock()
        self.records = []
        self.log = log if log is not None else self.records.append
        self.panel = panel or SimulatedPanel(self.clock)
        self.outbox = StatusQueue(status_queue_capacity)
        self.scheduler = AckDisplayScheduler(
            InputParser(), self.panel, render, self.outbox, self.clock,
            completion_capacity=64,
        )
        self.backend = backend if backend is not None else FakeKeyboardBackend(
            reports, clock=self.clock, interval_seconds=typing_interval_seconds
        )
        options = dict(adapter_options or {})
        self.session = LiveTypingSession(
            self.clock, self.log,
            adapter_factory=lambda queue: UsbKeyboardAdapter(
                self.backend, queue, self.log, **options
            ),
            **session_options
        )
        self.adapter = self.session.adapter
        self.status_frames_sent = 0
        self.iterations = 0

    def step(self):
        self.iterations += 1
        self.session.service()
        chunks = self.session.take_outbound()
        self.scheduler.service(chunks)
        while len(self.outbox):
            item = self.outbox.pop()
            self.status_frames_sent += 1
            self.session.feed(item[3])
        self.clock.now += STEP_SECONDS

    def run(self, maximum_iterations=200000):
        while not self.session.complete:
            if self.iterations >= maximum_iterations:
                raise RuntimeError("live keyboard simulation did not converge")
            self.step()
        return self

    def events(self, name):
        return [record for record in self.records if record.get("event") == name]
