"""Boot-protocol HID report parsing and press/release/hold state.

Host-safe. This module owns exactly one thing: turning a stream of 8-byte boot
keyboard reports into ordered *decisions* about what changed. It never touches a
queue, a clock, the editor, or the document.

The report layout was confirmed on the real receiver used for this phase
(0x36B0/0x3002, interface 0, subclass 1, protocol 1, endpoint 0x81, 8-byte
interrupt IN packets):

    byte 0   modifier bitmap
    byte 1   reserved, always zero
    bytes 2-7  up to six concurrently held usage IDs, zero-padded

Three properties matter and are each host-tested:

* an identical repeated report emits nothing, so a keyboard that re-sends its
  state cannot duplicate an edit;
* a rollover or POST-failure usage emits nothing and does not disturb the held
  set, so an overloaded key matrix cannot corrupt the document;
* ``reset()`` forgets every held key, so a reconnect can never replay a key that
  was held when the link dropped.
"""

from magwrite_transport.hid_keymap import (
    CONTROL_CAPS_LOCK, CONTROL_UNSUPPORTED, CONTROL_USAGES, REPEATABLE_KINDS,
    USAGE_NONE, is_error_usage, is_modifier_usage, shift_active, translate,
)
from magwrite_transport.keyboard_layout import STANDARD

REPORT_SIZE = 8
MODIFIER_INDEX = 0
RESERVED_INDEX = 1
FIRST_USAGE_INDEX = 2
USAGE_SLOTS = 6


class HidReportError(Exception):
    """A report was malformed; malformed reports are never interpreted."""


class KeyDecision:
    """One translated key press or repeat.

    ``usage`` is always the raw usage the keyboard sent, so repeat ownership and
    release matching stay in the keyboard's own vocabulary. ``mapped_usage`` is
    what was actually translated, and differs only under a device layout.
    """

    __slots__ = ("kind", "value", "usage", "mapped_usage", "repeat")

    def __init__(self, kind, value, usage, repeat=False, mapped_usage=None):
        self.kind = kind
        self.value = value
        self.usage = usage
        self.mapped_usage = usage if mapped_usage is None else mapped_usage
        self.repeat = repeat

    @property
    def remapped(self):
        return self.mapped_usage != self.usage

    @property
    def repeatable(self):
        return self.kind in REPEATABLE_KINDS


class ReportOutcome:
    """Everything one report changed, in deterministic report order."""

    __slots__ = (
        "modifier", "usages", "pressed", "released", "held", "decisions",
        "controls", "duplicate", "rollover",
    )

    def __init__(
        self, modifier=0, usages=(), pressed=(), released=(), held=(),
        decisions=(), controls=(), duplicate=False, rollover=False,
    ):
        self.modifier = modifier
        self.usages = usages
        self.pressed = pressed
        self.released = released
        self.held = held
        self.decisions = decisions
        self.controls = controls
        self.duplicate = duplicate
        self.rollover = rollover


def parse_report(raw):
    """Return ``(modifier, six_usages)`` from one boot keyboard report.

    Reports longer than the boot format are truncated rather than refused: a
    device that pads its interrupt packet is still a valid boot keyboard.
    """
    if raw is None:
        raise HidReportError("missing HID report")
    if len(raw) < REPORT_SIZE:
        raise HidReportError(
            "boot keyboard report is %d bytes, need %d" % (len(raw), REPORT_SIZE)
        )
    usages = tuple(
        raw[index]
        for index in range(FIRST_USAGE_INDEX, FIRST_USAGE_INDEX + USAGE_SLOTS)
    )
    return raw[MODIFIER_INDEX], usages


class HidKeyboardTranslator:
    """Stateful press/release/hold tracking across consecutive reports."""

    def __init__(self, layout=STANDARD):
        self.layout = layout
        self.caps_lock = False
        self.previous_raw = None
        self.held = ()
        self.reports_parsed = 0
        self.reports_accepted = 0
        self.duplicate_reports = 0
        self.rollover_reports = 0
        self.consecutive_rollover = 0
        self.unsupported_usages = 0
        self.caps_lock_toggles = 0
        self.remapped_usages = 0
        self.resets = 0

    def set_layout(self, layout):
        """Adopt a device layout, normally once, when a keyboard is identified."""
        self.layout = layout

    def reset(self):
        """Forget all transient keyboard state.

        Held keys are dropped so a reconnect cannot replay them. Caps Lock is
        cleared too: after a disconnect the adapter genuinely does not know the
        device's latch state, so it returns to a single known value rather than
        guessing.
        """
        self.previous_raw = None
        self.held = ()
        self.caps_lock = False
        self.consecutive_rollover = 0
        self.resets += 1

    def step(self, raw):
        """Interpret one report and return its :class:`ReportOutcome`."""
        modifier, usages = parse_report(raw)
        self.reports_parsed += 1

        if any(is_error_usage(usage) for usage in usages):
            self.rollover_reports += 1
            self.consecutive_rollover += 1
            return ReportOutcome(
                modifier=modifier, usages=usages, held=self.held, rollover=True
            )
        self.consecutive_rollover = 0

        candidate = bytes(raw[:REPORT_SIZE])
        if candidate == self.previous_raw:
            self.duplicate_reports += 1
            return ReportOutcome(
                modifier=modifier, usages=usages, held=self.held, duplicate=True
            )
        self.previous_raw = candidate
        self.reports_accepted += 1

        active = tuple(
            usage for usage in usages
            if usage != USAGE_NONE and not is_modifier_usage(usage)
        )
        # Report order, not set order: simultaneous presses must resolve the
        # same way on every run and on both the host and the device.
        pressed = tuple(usage for usage in active if usage not in self.held)
        released = tuple(usage for usage in self.held if usage not in active)
        self.held = active

        shift = shift_active(modifier)
        decisions = []
        controls = []
        for usage in pressed:
            # The layout decides *what key this is*; everything downstream still
            # sees the raw usage, so releases and repeats stay consistent.
            mapped = self.layout.usage(usage)
            if mapped != usage:
                self.remapped_usages += 1
            control = CONTROL_USAGES.get(mapped)
            if control == CONTROL_CAPS_LOCK:
                self.caps_lock = not self.caps_lock
                self.caps_lock_toggles += 1
                controls.append((CONTROL_CAPS_LOCK, self.caps_lock))
                continue
            if control is not None:
                controls.append((control, usage))
                continue
            translated = translate(mapped, shift, self.caps_lock)
            if translated is None:
                self.unsupported_usages += 1
                # The raw usage is reported: the diagnostic must say what the
                # keyboard actually sent, not what we hoped it meant.
                controls.append((CONTROL_UNSUPPORTED, usage))
                continue
            kind, value = translated
            decisions.append(
                KeyDecision(kind, value, usage, mapped_usage=mapped)
            )
        return ReportOutcome(
            modifier=modifier, usages=usages, pressed=pressed,
            released=released, held=active, decisions=tuple(decisions),
            controls=tuple(controls),
        )
