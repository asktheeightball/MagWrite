"""USB HID keyboard input adapter.

Host-safe. The backend is injected, so every path in this module — including
every failure path — runs under CPython host tests with no CircuitPython import.

This is the *input adapter* in the architecture. It replaces
``editor_scenarios.ScheduledEventProducer`` and nothing else: it produces the
same normalized ``InputEvent`` objects, with the same monotonic sequence
numbering, into the same bounded queue. It owns no document, cursor, layout, or
revision state, and the editor never sees a USB or HID concept.

    real keyboard -> backend -> HidKeyboardTranslator -> InputEvent -> queue

Polling is bounded twice over: at most ``poll_budget`` reports are drained per
call, and each backend read uses a short timeout, so a silent keyboard can never
block the display half of the scheduler.
"""

from magwrite_transport.editor import InputEvent, QueueOverflow
from magwrite_transport.hid_keyboard import HidKeyboardTranslator
from magwrite_transport.hid_keymap import (
    CONTROL_CAPS_LOCK, CONTROL_FINISH, CONTROL_SAVE, CONTROL_UNSUPPORTED,
)
from magwrite_transport.keyboard_layout import AUTO, resolve
from magwrite_transport.keyboard_repeat import KeyRepeat
from magwrite_transport.usb_device_state import (
    ERROR, MAX_OPEN_ATTEMPTS, UsbDeviceState,
)
from magwrite_transport.usb_hid_descriptors import (
    UsbKeyboardDisconnected, UsbKeyboardError, UsbKeyboardNotFound,
)

LIVE_SCENARIO = "live"
REPORT_POLL_BUDGET = 4
ROLLOVER_TOLERANCE = 8
MAX_KEYBOARD_EVENTS = 500


class UsbKeyboardAdapterError(Exception):
    """A stop condition fired. The physical harness never retries."""


class UsbKeyboardAdapter:
    def __init__(
        self, backend, queue, log, scenario=LIVE_SCENARIO, translator=None,
        repeat=None, state=None, poll_budget=REPORT_POLL_BUDGET,
        rollover_tolerance=ROLLOVER_TOLERANCE,
        max_events=MAX_KEYBOARD_EVENTS, now=0.0, layout=AUTO,
        max_open_attempts=MAX_OPEN_ATTEMPTS, optional=False,
    ):
        if poll_budget < 1:
            raise ValueError("poll budget must be positive")
        # Fail closed on a misspelled layout now, at construction, rather than
        # midway through an armed physical run.
        resolve(layout, None)
        self.layout_selection = layout
        self.backend = backend
        self.queue = queue
        self.log = log
        self.scenario = scenario
        self.translator = translator or HidKeyboardTranslator()
        self.repeat = repeat or KeyRepeat()
        self.state = state or UsbDeviceState(
            now, log, max_attempts=max_open_attempts
        )
        self.poll_budget = poll_budget
        self.rollover_tolerance = rollover_tolerance
        # ``None`` is unbounded, and only the standalone runtime passes it. See
        # ``usb_device_state`` for the argument, which is the same one: a bound
        # that exists to end a one-shot run must not be able to end a writing
        # appliance that is doing exactly what it was switched on to do.
        self.max_events = max_events
        # V1.6. With ``optional`` set, a keyboard that cannot be opened or that
        # stops answering is a *degraded mode* rather than a stop condition: the
        # panel says so, the MagTag buttons still reach the menu, and the next
        # poll tries again. Without it -- every guarded harness -- an open or read
        # failure is the fatal condition it has always been, because a
        # certification run with no keyboard has nothing to certify.
        self.optional = optional
        self.open_failures = 0
        self.read_failures = 0
        self.sequence = 0
        self.reports_received = 0
        self.events_generated = 0
        self.repeat_events = 0
        self.finish_requested = False
        # The same gesture counted as well as latched. The latch is what every
        # one-shot harness reads -- for a run that ends once, "has it been asked
        # to stop" is the whole question -- and it is left exactly as it was so
        # those harnesses keep the behaviour they were verified with. The shell
        # asks a different question: the finish gesture is *back*, pressed many
        # times in one session, and a latch cannot tell one press from four. This
        # is the counter the save control already uses, for the reason recorded
        # immediately below it.
        self.finish_requests = 0
        # A monotonic count rather than a flag the session has to clear. Two
        # objects sharing a mutable boolean is how a save request gets lost or
        # serviced twice; a counter lets the consumer track what it has honoured
        # without ever writing to the producer.
        self.save_requests = 0
        self.queue_overflows = 0
        self.last_activity_at = now
        self.descriptor = None

    # ------------------------------------------------------------- properties

    @property
    def ready(self):
        return self.state.ready

    @property
    def duplicate_reports(self):
        return self.translator.duplicate_reports

    @property
    def rollover_reports(self):
        return self.translator.rollover_reports

    @property
    def unsupported_usages(self):
        return self.translator.unsupported_usages

    @property
    def caps_lock(self):
        return self.translator.caps_lock

    # ------------------------------------------------------------- connection

    def connect(self, now):
        """Make at most one bounded open attempt. Returns True when READY."""
        if self.state.ready:
            return True
        if not self.state.retry_due(now):
            if self.state.exhausted and self.state.state != ERROR:
                self.state.failed(now, "open attempts exhausted")
            return False
        self.state.begin_attempt(now)
        try:
            self.descriptor = self.backend.open()
        except UsbKeyboardNotFound as error:
            self.state.not_found(now, str(error))
            return False
        except UsbKeyboardError as error:
            self.open_failures += 1
            if self.optional:
                # Something is attached that this board cannot drive as a boot
                # keyboard -- a hub, a receiver, a composite device. On an
                # appliance that is a keyboard the writer has not plugged in
                # yet, not a reason to refuse to be a writing device.
                self.log({"event": "usb_keyboard_open_failed",
                          "detail": str(error), "fatal": False,
                          "open_failures": self.open_failures})
                self.state.not_found(now, str(error))
                return False
            self.state.failed(now, str(error))
            raise UsbKeyboardAdapterError("usb keyboard open failed: " + str(error))
        # A fresh session must never inherit held keys or a guessed latch state.
        self.translator.reset()
        self.repeat.cancel()
        # The layout is chosen from the descriptor of the keyboard actually
        # attached, so an unrecognised device always gets standard HID.
        layout = resolve(self.layout_selection, self.descriptor)
        self.translator.set_layout(layout)
        self.state.opened(now)
        record = {"event": "usb_keyboard_connected"}
        if isinstance(self.descriptor, dict):
            record.update(self.descriptor)
        self.log(record)
        self.log({
            "event": "usb_keyboard_layout_selected",
            "selection": self.layout_selection,
            "layout": layout.describe(),
            "note": layout.note,
        })
        self.last_activity_at = now
        return True

    def _disconnected(self, now, reason):
        self.translator.reset()
        self.repeat.cancel()
        self.state.disconnected(now, reason)
        self.log({
            "event": "usb_keyboard_disconnected", "reason": reason,
            "held_keys_cleared": True, "reports_received": self.reports_received,
        })
        try:
            self.backend.close()
        except UsbKeyboardError:
            pass

    # ------------------------------------------------------------------ events

    def _emit(self, decision, scheduled_ms, repeat):
        if self.max_events is not None and self.events_generated >= self.max_events:
            raise UsbKeyboardAdapterError("normalized keyboard event limit exceeded")
        event = InputEvent(
            self.sequence, self.scenario, decision.kind, decision.value,
            int(scheduled_ms),
        )
        try:
            depth = self.queue.put(event)
        except QueueOverflow:
            self.queue_overflows += 1
            self.log({
                "event": "usb_keyboard_queue_overflow",
                "sequence": self.sequence, "kind": decision.kind,
                "capacity": self.queue.capacity,
            })
            raise UsbKeyboardAdapterError("keyboard input queue overflow")
        self.sequence += 1
        self.events_generated += 1
        if repeat:
            self.repeat_events += 1
        self.log({
            "event": "keyboard_event_normalized",
            "sequence": event.sequence, "kind": event.kind,
            "value": event.value, "usage": decision.usage,
            "mapped_usage": decision.mapped_usage,
            "repeat": repeat, "queue_depth": depth,
        })
        return 1

    def _handle_controls(self, controls):
        for control, detail in controls:
            if control == CONTROL_FINISH:
                self.finish_requested = True
                self.finish_requests += 1
                self.log({"event": "usb_keyboard_finish_requested",
                          "usage": detail,
                          "finish_requests": self.finish_requests})
            elif control == CONTROL_SAVE:
                self.save_requests += 1
                self.log({"event": "usb_keyboard_save_requested",
                          "usage": detail, "save_requests": self.save_requests})
            elif control == CONTROL_CAPS_LOCK:
                self.log({"event": "usb_keyboard_caps_lock", "enabled": detail})
            elif control == CONTROL_UNSUPPORTED:
                self.log({"event": "usb_keyboard_unsupported_usage",
                          "usage": detail,
                          "unsupported_usages": self.unsupported_usages})

    # -------------------------------------------------------------- main poll

    def poll(self, now):
        """Drain a bounded burst of reports and repeats. Returns events queued."""
        if not self.state.ready and not self.connect(now):
            return 0
        scheduled_ms = now * 1000.0
        produced = 0
        for _ in range(self.poll_budget):
            try:
                raw = self.backend.read_report()
            except UsbKeyboardDisconnected as error:
                self._disconnected(now, str(error))
                return produced
            except UsbKeyboardError as error:
                self.read_failures += 1
                if self.optional:
                    # Treated as the unplug it almost always is. The held keys
                    # are cleared, the state machine goes to DISCONNECTED, and
                    # the next poll starts looking again.
                    self.log({"event": "usb_keyboard_read_failed",
                              "detail": str(error), "fatal": False,
                              "read_failures": self.read_failures})
                    self._disconnected(now, str(error))
                    return produced
                self.state.failed(now, str(error))
                raise UsbKeyboardAdapterError("usb keyboard read failed: " + str(error))
            if raw is None:
                break
            self.reports_received += 1
            self.last_activity_at = now
            outcome = self.translator.step(raw)
            self.log({
                "event": "hid_report_received",
                "modifier": outcome.modifier, "keys": list(outcome.usages),
                "duplicate": outcome.duplicate, "rollover": outcome.rollover,
            })
            if outcome.rollover:
                if self.translator.consecutive_rollover > self.rollover_tolerance:
                    raise UsbKeyboardAdapterError(
                        "rollover reports persisted beyond tolerance"
                    )
                continue
            if outcome.duplicate:
                continue
            self.repeat.cancel_if_released(outcome.released)
            for decision in outcome.decisions:
                produced += self._emit(decision, scheduled_ms, False)
                if decision.repeatable:
                    self.repeat.arm(decision.usage, decision, scheduled_ms)
                    self.log({
                        "event": "keyboard_repeat_started",
                        "usage": decision.usage,
                        "delay_ms": self.repeat.delay_ms,
                        "interval_ms": self.repeat.interval_ms,
                    })
            self._handle_controls(outcome.controls)

        decision = self.repeat.decision
        if decision is not None:
            for _ in range(self.repeat.due(scheduled_ms)):
                produced += self._emit(decision, scheduled_ms, True)
        return produced

    # ---------------------------------------------------------------- summary

    def summary(self):
        return {
            "reports_received": self.reports_received,
            "normalized_events": self.events_generated,
            "duplicate_reports": self.duplicate_reports,
            "rollover_reports": self.rollover_reports,
            "repeat_events": self.repeat_events,
            "repeat_resynchronizations": self.repeat.resynchronizations,
            "unsupported_usages": self.unsupported_usages,
            "save_requests": self.save_requests,
            "finish_requests": self.finish_requests,
            "caps_lock_toggles": self.translator.caps_lock_toggles,
            "keyboard_layout": self.translator.layout.name,
            "remapped_usages": self.translator.remapped_usages,
            "queue_overflows": self.queue_overflows,
            "keyboard_optional": self.optional,
            "keyboard_open_failures": self.open_failures,
            "keyboard_read_failures": self.read_failures,
            "held_key_resets": self.translator.resets,
            "usb_device": self.state.describe(),
            "usb_descriptor": self.descriptor,
        }
