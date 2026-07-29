"""USB keyboard adapter, connection state machine, and backend contract.

Every failure path exercised here is a *device-entry* path. Two prior physical
blockers happened in code the host suite never reached, so the connection,
descriptor, endpoint, and queue failures are all driven from CPython.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from keyboard_simulator import (
    FakeKeyboardBackend, RELEASE_REPORT, press_release, report, type_characters,
)
from magwrite_transport.editor import BoundedEventQueue, CHAR, ENTER
from magwrite_transport.hid_keymap import (
    USAGE_APPLICATION, USAGE_CAPS_LOCK, USAGE_ERROR_ROLLOVER, USAGE_ESCAPE,
)
from magwrite_transport.keyboard_repeat import (
    REPEAT_DELAY_MS, REPEAT_INTERVAL_MS, KeyRepeat,
)
from magwrite_transport.usb_device_state import (
    DISCONNECTED, ENUMERATING, ERROR, NO_DEVICE, READY, STATES, UsbDeviceState,
)
from magwrite_transport.usb_hid_descriptors import (
    EndpointInitializationError, UnsupportedKeyboardInterface,
    UsbHostUnavailable, UsbKeyboardDisconnected, UsbKeyboardNotFound,
)
from magwrite_transport.usb_host_backend import UsbHostKeyboardBackend
from magwrite_transport.usb_keyboard_adapter import (
    UsbKeyboardAdapter, UsbKeyboardAdapterError,
)

USAGE_A = 0x04
USAGE_B = 0x05
USAGE_BACKSPACE = 0x2A
USAGE_LEFT = 0x50
USAGE_HOME = 0x4A


def build(reports=(), queue_capacity=64, records=None, **options):
    """One adapter over a scripted backend.

    The default poll budget is widened so a test that means "drain the whole
    script" reads that way; the tests that are *about* bounding pass their own.
    """
    backend = FakeKeyboardBackend(reports, reports_per_poll=32)
    queue = BoundedEventQueue(queue_capacity)
    log = records.append if records is not None else (lambda record: None)
    options.setdefault("poll_budget", 32)
    adapter = UsbKeyboardAdapter(backend, queue, log, **options)
    return adapter, queue, backend


def drain(queue):
    out = []
    while True:
        event = queue.get()
        if event is None:
            return out
        out.append(event)


class AdapterEventTest(unittest.TestCase):
    def test_typing_produces_normalized_events_in_order(self):
        adapter, queue, _ = build(type_characters("Hi!"))
        adapter.poll(0.0)
        events = drain(queue)
        self.assertEqual([e.kind for e in events], [CHAR] * 3)
        self.assertEqual([e.value for e in events], ["H", "i", "!"])
        self.assertEqual([e.sequence for e in events], [0, 1, 2])

    def test_sequences_stay_monotonic_across_polls(self):
        adapter, queue, _ = build(
            type_characters("ab") + type_characters("cd")
        )
        for step in range(4):
            adapter.poll(step * 0.1)
        self.assertEqual([e.sequence for e in drain(queue)], [0, 1, 2, 3])

    def test_events_carry_the_poll_time_as_scheduled_ms(self):
        adapter, queue, _ = build(type_characters("a"))
        adapter.poll(1.25)
        self.assertEqual(drain(queue)[0].scheduled_ms, 1250)

    def test_enter_and_editing_keys_normalize(self):
        adapter, queue, _ = build(
            type_characters("a\n") + press_release(USAGE_BACKSPACE)
            + press_release(USAGE_HOME)
        )
        adapter.poll(0.0)
        self.assertEqual(
            [e.kind for e in drain(queue)], [CHAR, ENTER, "BACKSPACE", "HOME"]
        )

    def test_a_duplicate_report_produces_no_second_event(self):
        adapter, queue, _ = build([
            report(0, (USAGE_A,)), report(0, (USAGE_A,)), RELEASE_REPORT,
        ])
        adapter.poll(0.0)
        self.assertEqual(len(drain(queue)), 1)
        self.assertEqual(adapter.duplicate_reports, 1)

    def test_a_held_key_alone_produces_no_second_event(self):
        adapter, queue, _ = build([report(0, (USAGE_A,))] * 5)
        adapter.poll(0.0)
        self.assertEqual(len(drain(queue)), 1)

    def test_modifiers_alone_produce_no_event(self):
        adapter, queue, _ = build([report(0x02), report(0x22), report(0x00)])
        adapter.poll(0.0)
        self.assertEqual(drain(queue), [])
        self.assertEqual(adapter.events_generated, 0)

    def test_caps_lock_produces_no_event_but_changes_later_characters(self):
        adapter, queue, _ = build(
            press_release(USAGE_CAPS_LOCK) + press_release(USAGE_A)
        )
        adapter.poll(0.0)
        events = drain(queue)
        self.assertEqual([e.value for e in events], ["A"])
        self.assertTrue(adapter.caps_lock)

    def test_a_rollover_report_produces_no_event(self):
        adapter, queue, _ = build([
            report(0, (USAGE_ERROR_ROLLOVER,) * 6), RELEASE_REPORT,
        ])
        adapter.poll(0.0)
        self.assertEqual(drain(queue), [])
        self.assertEqual(adapter.rollover_reports, 1)

    def test_persistent_rollover_beyond_tolerance_stops_the_adapter(self):
        adapter, _, _ = build(
            [report(0, (USAGE_ERROR_ROLLOVER,))] * 12,
            rollover_tolerance=3, poll_budget=12,
        )
        with self.assertRaises(UsbKeyboardAdapterError) as caught:
            adapter.poll(0.0)
        self.assertIn("rollover", str(caught.exception))

    def test_an_unsupported_usage_is_ignored_and_counted(self):
        adapter, queue, _ = build(
            press_release(0x3A) + press_release(USAGE_A)      # F1, then "a"
        )
        adapter.poll(0.0)
        self.assertEqual([e.value for e in drain(queue)], ["a"])
        self.assertEqual(adapter.unsupported_usages, 1)

    def test_escape_requests_finish_without_producing_an_event(self):
        adapter, queue, _ = build(press_release(USAGE_ESCAPE))
        adapter.poll(0.0)
        self.assertTrue(adapter.finish_requested)
        self.assertEqual(drain(queue), [])

    def test_the_application_key_requests_finish_the_same_way(self):
        """The physical keyboard can only finish a run with 0x65."""
        adapter, queue, _ = build(press_release(USAGE_APPLICATION))
        adapter.poll(0.0)
        self.assertTrue(adapter.finish_requested)
        self.assertEqual(drain(queue), [])
        self.assertEqual(adapter.unsupported_usages, 0)

    def test_typing_then_the_application_key_keeps_the_typed_events(self):
        adapter, queue, _ = build(
            type_characters("Hi") + press_release(USAGE_APPLICATION)
        )
        for _ in range(8):
            adapter.poll(0.0)
        self.assertTrue(adapter.finish_requested)
        self.assertEqual([e.value for e in drain(queue)], ["H", "i"])

    def test_polling_is_bounded_by_the_report_budget(self):
        adapter, queue, _ = build(type_characters("abcdef"), poll_budget=2)
        adapter.poll(0.0)
        # Two reports per poll: the press of "a" and its release.
        self.assertEqual(len(drain(queue)), 1)
        adapter.poll(0.1)
        self.assertEqual(len(drain(queue)), 1)

    def test_the_event_ceiling_is_enforced(self):
        adapter, _, _ = build(type_characters("abcd"), max_events=2,
                              poll_budget=16)
        with self.assertRaises(UsbKeyboardAdapterError) as caught:
            adapter.poll(0.0)
        self.assertIn("event limit", str(caught.exception))


class AdapterQueueTest(unittest.TestCase):
    def test_queue_overflow_is_explicit_and_counted(self):
        adapter, _, _ = build(type_characters("abcd"), queue_capacity=2,
                              poll_budget=16)
        with self.assertRaises(UsbKeyboardAdapterError) as caught:
            adapter.poll(0.0)
        self.assertIn("overflow", str(caught.exception))
        self.assertEqual(adapter.queue_overflows, 1)

    def test_queue_depth_is_reported_with_each_event(self):
        records = []
        adapter, _, _ = build(type_characters("abc"), records=records,
                              poll_budget=16)
        adapter.poll(0.0)
        depths = [
            r["queue_depth"] for r in records
            if r.get("event") == "keyboard_event_normalized"
        ]
        self.assertEqual(depths, [1, 2, 3])


class AdapterRepeatTest(unittest.TestCase):
    def test_a_held_printable_repeats_after_the_delay(self):
        adapter, queue, _ = build([report(0, (USAGE_A,))])
        adapter.poll(0.0)
        self.assertEqual(len(drain(queue)), 1)
        adapter.poll((REPEAT_DELAY_MS - 1) / 1000.0)
        self.assertEqual(drain(queue), [])
        adapter.poll(REPEAT_DELAY_MS / 1000.0)
        repeated = drain(queue)
        self.assertEqual([e.value for e in repeated], ["a"])
        self.assertEqual(adapter.repeat_events, 1)

    def test_repeats_follow_the_configured_interval(self):
        adapter, queue, _ = build([report(0, (USAGE_LEFT,))])
        adapter.poll(0.0)
        drain(queue)
        adapter.poll(REPEAT_DELAY_MS / 1000.0)
        self.assertEqual(len(drain(queue)), 1)
        adapter.poll((REPEAT_DELAY_MS + REPEAT_INTERVAL_MS - 1) / 1000.0)
        self.assertEqual(drain(queue), [])
        adapter.poll((REPEAT_DELAY_MS + REPEAT_INTERVAL_MS) / 1000.0)
        self.assertEqual([e.kind for e in drain(queue)], ["LEFT"])

    def test_release_cancels_the_repeat(self):
        adapter, queue, _ = build([report(0, (USAGE_A,)), RELEASE_REPORT])
        adapter.poll(0.0)
        drain(queue)
        adapter.poll(REPEAT_DELAY_MS / 1000.0)
        self.assertEqual(drain(queue), [])
        self.assertEqual(adapter.repeat_events, 0)

    def test_repeated_events_are_flagged_in_diagnostics(self):
        records = []
        adapter, queue, _ = build([report(0, (USAGE_A,))], records=records)
        adapter.poll(0.0)
        adapter.poll(REPEAT_DELAY_MS / 1000.0)
        flags = [
            r["repeat"] for r in records
            if r.get("event") == "keyboard_event_normalized"
        ]
        self.assertEqual(flags, [False, True])
        self.assertTrue(
            [r for r in records if r.get("event") == "keyboard_repeat_started"]
        )

    def test_home_does_not_repeat(self):
        adapter, queue, _ = build([report(0, (USAGE_HOME,))])
        adapter.poll(0.0)
        self.assertEqual(len(drain(queue)), 1)
        adapter.poll(10.0)
        self.assertEqual(drain(queue), [])

    def test_the_newest_held_key_owns_the_repeat(self):
        adapter, queue, _ = build([
            report(0, (USAGE_A,)), report(0, (USAGE_A, USAGE_B)),
        ])
        adapter.poll(0.0)
        drain(queue)
        adapter.poll(REPEAT_DELAY_MS / 1000.0)
        self.assertEqual([e.value for e in drain(queue)], ["b"])


class ConnectionStateTest(unittest.TestCase):
    def test_the_declared_states_are_the_documented_five(self):
        self.assertEqual(
            sorted(STATES),
            sorted([NO_DEVICE, ENUMERATING, READY, DISCONNECTED, ERROR]),
        )

    def test_a_successful_open_reaches_ready_and_logs_the_descriptor(self):
        records = []
        adapter, _, backend = build(records=records)
        self.assertTrue(adapter.connect(0.0))
        self.assertTrue(adapter.ready)
        self.assertEqual(backend.opens, 1)
        connected = [
            r for r in records if r.get("event") == "usb_keyboard_connected"
        ]
        self.assertEqual(len(connected), 1)
        self.assertEqual(connected[0]["vendor_id"], "36B0")
        self.assertEqual(connected[0]["endpoint"], 0x81)

    def test_no_keyboard_connected_fails_closed_without_raising(self):
        backend = FakeKeyboardBackend(open_error=UsbKeyboardNotFound("none"))
        adapter = UsbKeyboardAdapter(
            backend, BoundedEventQueue(8), lambda r: None
        )
        self.assertFalse(adapter.connect(0.0))
        self.assertEqual(adapter.state.state, NO_DEVICE)
        self.assertEqual(adapter.poll(0.0), 0)

    def test_reconnect_attempts_are_rate_limited_and_bounded(self):
        backend = FakeKeyboardBackend(open_error=UsbKeyboardNotFound("none"))
        state = UsbDeviceState(0.0, retry_interval=1.0, max_attempts=3)
        adapter = UsbKeyboardAdapter(
            backend, BoundedEventQueue(8), lambda r: None, state=state
        )
        adapter.connect(0.0)
        # Same second: no second attempt.
        adapter.connect(0.5)
        self.assertEqual(backend.opens, 1)
        adapter.connect(1.0)
        adapter.connect(2.0)
        self.assertEqual(backend.opens, 3)
        # Bounded: attempts are exhausted, so it latches ERROR rather than spin.
        adapter.connect(3.0)
        adapter.connect(4.0)
        self.assertEqual(backend.opens, 3)
        self.assertEqual(adapter.state.state, ERROR)

    def test_missing_usb_host_module_fails_closed_as_a_stop_condition(self):
        backend = FakeKeyboardBackend(
            open_error=UsbHostUnavailable("usb.core is unavailable")
        )
        adapter = UsbKeyboardAdapter(
            backend, BoundedEventQueue(8), lambda r: None
        )
        with self.assertRaises(UsbKeyboardAdapterError):
            adapter.connect(0.0)
        self.assertEqual(adapter.state.state, ERROR)

    def test_an_unsupported_interface_fails_closed(self):
        backend = FakeKeyboardBackend(
            open_error=UnsupportedKeyboardInterface("no boot keyboard")
        )
        adapter = UsbKeyboardAdapter(
            backend, BoundedEventQueue(8), lambda r: None
        )
        with self.assertRaises(UsbKeyboardAdapterError):
            adapter.connect(0.0)
        self.assertEqual(adapter.state.state, ERROR)

    def test_an_endpoint_failure_fails_closed(self):
        backend = FakeKeyboardBackend(
            open_error=EndpointInitializationError("no interrupt IN endpoint")
        )
        adapter = UsbKeyboardAdapter(
            backend, BoundedEventQueue(8), lambda r: None
        )
        with self.assertRaises(UsbKeyboardAdapterError):
            adapter.connect(0.0)

    def test_a_disconnect_clears_held_keys_and_never_replays_them(self):
        records = []
        adapter, queue, backend = build(
            [report(0, (USAGE_A,))], records=records, poll_budget=4
        )
        adapter.poll(0.0)
        self.assertEqual(len(drain(queue)), 1)
        self.assertEqual(adapter.translator.held, (USAGE_A,))
        backend.disconnect_after = 0
        backend.reports = [report(0, (USAGE_A,))]
        adapter.poll(0.1)
        self.assertEqual(adapter.state.state, DISCONNECTED)
        self.assertEqual(adapter.translator.held, ())
        self.assertFalse(adapter.repeat.armed)
        self.assertEqual(drain(queue), [])
        self.assertTrue(
            [r for r in records if r.get("event") == "usb_keyboard_disconnected"]
        )

    def test_a_reconnect_returns_to_ready_with_no_stale_state(self):
        adapter, queue, backend = build([report(0, (USAGE_A,))])
        adapter.poll(0.0)
        drain(queue)
        backend.disconnect_after = 0
        adapter.poll(0.1)
        self.assertEqual(adapter.state.state, DISCONNECTED)
        # The still-queued report must be a fresh press, not a replay.
        backend.reports = [report(0, (USAGE_A,))]
        adapter.poll(2.0)
        self.assertEqual(adapter.state.state, READY)
        self.assertEqual([e.value for e in drain(queue)], ["a"])
        self.assertEqual(adapter.state.disconnects, 1)
        self.assertEqual(adapter.state.connects, 2)
        self.assertFalse(adapter.caps_lock)

    def test_a_disconnect_produces_no_editor_event_at_all(self):
        adapter, queue, backend = build(type_characters("ab"))
        backend.disconnect_after = 0
        adapter.poll(0.0)
        self.assertEqual(drain(queue), [])
        self.assertEqual(adapter.events_generated, 0)

    def test_state_transitions_are_validated(self):
        state = UsbDeviceState(0.0)
        with self.assertRaises(ValueError):
            state._enter("SOMETHING_ELSE", 0.0)
        for bad in ({"retry_interval": 0}, {"max_attempts": 0}):
            with self.assertRaises(ValueError):
                UsbDeviceState(0.0, **bad)

    def test_state_transitions_are_logged(self):
        records = []
        state = UsbDeviceState(0.0, records.append)
        state.begin_attempt(0.0)
        state.opened(0.1)
        state.disconnected(0.2)
        kinds = [(r["from"], r["to"]) for r in records]
        self.assertEqual(kinds, [
            (NO_DEVICE, ENUMERATING), (ENUMERATING, READY),
            (READY, DISCONNECTED),
        ])


class BackendContractTest(unittest.TestCase):
    """The real backend, with the CircuitPython import injected."""

    def test_a_missing_usb_core_module_raises_usb_host_unavailable(self):
        def missing():
            raise UsbHostUnavailable("usb.core is unavailable: no module")

        backend = UsbHostKeyboardBackend(lambda r: None, load=missing)
        with self.assertRaises(UsbHostUnavailable):
            backend.open()
        self.assertFalse(backend.connected)

    def test_reading_without_a_claimed_endpoint_reports_disconnected(self):
        backend = UsbHostKeyboardBackend(lambda r: None, load=lambda: None)
        with self.assertRaises(UsbKeyboardDisconnected):
            backend.read_report()

    def test_close_is_safe_when_nothing_was_ever_opened(self):
        backend = UsbHostKeyboardBackend(lambda r: None, load=lambda: None)
        backend.close()
        self.assertFalse(backend.connected)

    def test_an_empty_bus_raises_keyboard_not_found(self):
        class EmptyBus:
            USBTimeoutError = TimeoutError

            @staticmethod
            def find(find_all=False):
                return []

        backend = UsbHostKeyboardBackend(lambda r: None, load=lambda: EmptyBus)
        with self.assertRaises(UsbKeyboardNotFound):
            backend.open()


class AdapterSummaryTest(unittest.TestCase):
    def test_the_summary_reports_every_required_counter(self):
        adapter, queue, _ = build(
            type_characters("Hi") + press_release(USAGE_ESCAPE)
        )
        adapter.poll(0.0)
        summary = adapter.summary()
        for field in (
            "reports_received", "normalized_events", "duplicate_reports",
            "rollover_reports", "repeat_events", "unsupported_usages",
            "queue_overflows", "held_key_resets", "usb_device",
            "usb_descriptor", "caps_lock_toggles",
        ):
            self.assertIn(field, summary)
        self.assertEqual(summary["normalized_events"], 2)
        self.assertEqual(summary["usb_device"]["state"], READY)

    def test_the_summary_is_json_serializable(self):
        import json
        adapter, _, _ = build(type_characters("a"))
        adapter.poll(0.0)
        json.loads(json.dumps(adapter.summary()))

    def test_a_poll_budget_below_one_is_refused(self):
        with self.assertRaises(ValueError):
            build(poll_budget=0)


if __name__ == "__main__":
    unittest.main()
