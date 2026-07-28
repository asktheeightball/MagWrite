import importlib
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.ack_scheduler import AckDisplayScheduler, AckSchedulerError
from magwrite.status_message import decode_status, encode_status
from magwrite.status_queue import StatusQueue, StatusQueueOverflow
from magwrite.uart_protocol import (
    DISPLAY_CAUGHT_UP, DISPLAY_ERROR, END_OF_TEST, FRAME_ACCEPTED,
    FRAME_REJECTED, Frame, FrameParser, HELLO, MAX_RECEIVE_BUFFER,
    REFRESH_COMPLETED, REFRESH_STARTED, STATUS_HELLO, TEST_COMPLETE,
    VERSION, VIEWPORT, encode_frame,
)
from magwrite.viewport_message import ViewportMessage
from magwrite_transport.ack_tracker import (
    AckError, AckTimeout, AckTracker, AckTrackerOverflow,
    DISPLAY_CAUGHT_UP_TIMEOUT, FRAME_ACCEPTED_TIMEOUT,
    REFRESH_COMPLETED_TIMEOUT, REFRESH_STARTED_TIMEOUT,
    STATUS_HELLO_TIMEOUT,
)
from magwrite_transport.ack_viewports import (
    MAX_ACK_TOTAL_INPUT_FRAMES, MAX_ACK_VIEWPORT_FRAMES, ack_test_messages,
)
from magwrite_transport import protocol as tx_protocol
from magwrite_transport.status_message import (
    decode_status as tx_decode_status,
    encode_status as tx_encode_status,
)


FIELDS = {
    STATUS_HELLO: {
        "protocol_version": VERSION, "app_version": 1, "displayed_revision": 0,
        "receiver_ready": True, "display_ready": True, "test_id": "ACK",
    },
    FRAME_ACCEPTED: {
        "received_sequence": 7, "pending_revision": 3, "superseded": True,
    },
    REFRESH_STARTED: {
        "viewport_sequence": 7, "refresh_mode": 0,
        "latest_received_revision": 3, "previous_displayed_revision": 2,
    },
    REFRESH_COMPLETED: {
        "viewport_sequence": 7, "duration_ms": 701,
        "latest_received_revision": 4, "stale": True,
    },
    DISPLAY_CAUGHT_UP: {
        "displayed_revision": 4, "latest_received_revision": 4,
        "viewport_hash": 0x12345678,
    },
    FRAME_REJECTED: {
        "received_sequence": 7, "received_revision": 4, "code": 2,
        "displayed_revision": 3, "reason": "bad viewport",
    },
    DISPLAY_ERROR: {
        "code": 4, "inflight_revision": 4, "latest_received_revision": 5,
        "displayed_revision": 3, "reason": "busy timeout",
    },
    TEST_COMPLETE: {
        "displayed_revision": 6, "viewport_hash": 0x12345678,
        "accepted_count": 6, "rendered_count": 4, "superseded_count": 2,
        "refresh_count": 4, "error_count": 0,
    },
}


def status_frame(kind, sequence, revision, fields=None):
    return Frame(kind, sequence, revision, encode_status(kind, fields or FIELDS[kind]))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeDisplay:
    def __init__(self):
        self.busy = False
        self.calls = []

    def begin_refresh(self, framebuffer, full=False):
        self.calls.append((framebuffer, full))
        self.busy = True
        return full

    def is_busy(self):
        return self.busy


class StatusProtocolTests(unittest.TestCase):
    def test_every_status_type_round_trips_deterministically(self):
        for kind, fields in FIELDS.items():
            with self.subTest(kind=kind):
                payload = encode_status(kind, fields)
                self.assertEqual(payload, encode_status(kind, fields))
                self.assertEqual(decode_status(kind, payload), fields)

    def test_sender_receiver_status_payload_parity(self):
        for kind, fields in FIELDS.items():
            payload = encode_status(kind, fields)
            self.assertEqual(payload, tx_encode_status(kind, fields))
            self.assertEqual(tx_decode_status(kind, payload), fields)

    def test_status_crc_and_chunked_parsing(self):
        wire = encode_frame(REFRESH_COMPLETED, 1, 3,
                            encode_status(REFRESH_COMPLETED, FIELDS[REFRESH_COMPLETED]))
        parser = FrameParser()
        for byte in wire:
            parser.feed(bytes((byte,)))
        self.assertEqual(parser.pop().message_type, REFRESH_COMPLETED)

    def test_multiple_status_frames_one_chunk(self):
        parser = FrameParser()
        parser.feed(
            encode_frame(STATUS_HELLO, 1, 0, encode_status(STATUS_HELLO, FIELDS[STATUS_HELLO]))
            + encode_frame(FRAME_ACCEPTED, 2, 1, encode_status(FRAME_ACCEPTED, FIELDS[FRAME_ACCEPTED]))
        )
        self.assertEqual(parser.pop().sequence, 1)
        self.assertEqual(parser.pop().sequence, 2)

    def test_garbage_prefix_is_counted_and_bounded(self):
        parser = FrameParser()
        parser.feed(b"x" * 296 + encode_frame(STATUS_HELLO, 1, 0,
                                              encode_status(STATUS_HELLO, FIELDS[STATUS_HELLO])))
        frame = parser.pop()
        self.assertEqual(frame.message_type, STATUS_HELLO)
        self.assertEqual(parser.bytes_discarded_before_magic, 296)
        self.assertEqual(parser.resynchronization_events, 1)
        self.assertEqual(parser.maximum_discarded_prefix, 296)

    def test_bad_crc_version_and_unknown_type_reject(self):
        bad_crc = bytearray(encode_frame(STATUS_HELLO, 1, 0,
                                         encode_status(STATUS_HELLO, FIELDS[STATUS_HELLO])))
        bad_crc[-1] ^= 1
        parser = FrameParser()
        parser.feed(bad_crc)
        self.assertIsNone(parser.pop())
        self.assertEqual(parser.crc_failures, 1)
        bad_version = bytearray(encode_frame(STATUS_HELLO, 2, 0, b""))
        bad_version[2] = 99
        parser.feed(bad_version)
        parser.pop()
        self.assertEqual(parser.version_failures, 1)
        bad_type = bytearray(encode_frame(STATUS_HELLO, 3, 0, b""))
        bad_type[3] = 99
        parser.feed(bad_type)
        parser.pop()
        self.assertEqual(parser.type_failures, 1)

    def test_malformed_status_payloads_reject(self):
        for kind in FIELDS:
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    decode_status(kind, b"")

    def test_parser_overflow_explicit(self):
        parser = FrameParser()
        parser.feed(b"x" * (MAX_RECEIVE_BUFFER + 20))
        self.assertEqual(parser.buffer_overflows, 1)
        self.assertLessEqual(len(parser.buffer), MAX_RECEIVE_BUFFER)

    def test_protocol_constant_parity(self):
        module = importlib.import_module("magwrite.uart_protocol")
        for name in (
            "STATUS_HELLO", "FRAME_ACCEPTED", "REFRESH_STARTED",
            "REFRESH_COMPLETED", "DISPLAY_CAUGHT_UP", "FRAME_REJECTED",
            "DISPLAY_ERROR", "TEST_COMPLETE", "MAX_PAYLOAD_SIZE",
        ):
            self.assertEqual(getattr(module, name), getattr(tx_protocol, name))


class AckTrackerTests(unittest.TestCase):
    def ready_tracker(self):
        tracker = AckTracker(start_time=0)
        tracker.apply(status_frame(STATUS_HELLO, 1, 0), 0.1)
        return tracker

    def test_acceptance_and_started_do_not_mark_displayed(self):
        tracker = self.ready_tracker()
        state = tracker.sent(1, 2, 0xAABBCCDD, 1)
        tracker.apply(status_frame(FRAME_ACCEPTED, 2, 1, {
            "received_sequence": 2, "pending_revision": 1, "superseded": False,
        }), 1.1)
        self.assertFalse(state.displayed)
        tracker.apply(status_frame(REFRESH_STARTED, 3, 1, {
            "viewport_sequence": 2, "refresh_mode": 1,
            "latest_received_revision": 1, "previous_displayed_revision": 0,
        }), 1.2)
        self.assertFalse(state.displayed)

    def test_completed_stale_does_not_catch_up(self):
        tracker = self.ready_tracker()
        first = tracker.sent(1, 2, 1, 1)
        tracker.sent(2, 3, 2, 1.1)
        first.accepted = True
        first.refresh_started = True
        tracker.apply(status_frame(REFRESH_COMPLETED, 2, 1, {
            "viewport_sequence": 2, "duration_ms": 700,
            "latest_received_revision": 2, "stale": True,
        }), 2)
        self.assertFalse(first.displayed)

    def test_exact_caught_up_and_hash_required(self):
        tracker = self.ready_tracker()
        state = tracker.sent(1, 2, 0x1234, 1)
        state.accepted = state.refresh_started = state.refresh_completed = True
        tracker.apply(status_frame(DISPLAY_CAUGHT_UP, 2, 1, {
            "displayed_revision": 1, "latest_received_revision": 1,
            "viewport_hash": 0x1234,
        }), 2)
        self.assertTrue(state.displayed)

    def test_stale_caught_up_cannot_advance(self):
        tracker = self.ready_tracker()
        one = tracker.sent(1, 2, 1, 1)
        tracker.sent(2, 3, 2, 1.1)
        one.refresh_completed = True
        with self.assertRaises(AckError):
            tracker.apply(status_frame(DISPLAY_CAUGHT_UP, 2, 1, {
                "displayed_revision": 1, "latest_received_revision": 1,
                "viewport_hash": 1,
            }), 2)

    def test_duplicate_stale_and_gap_status_sequences(self):
        tracker = self.ready_tracker()
        duplicate = status_frame(STATUS_HELLO, 1, 0)
        self.assertIsNone(tracker.apply(duplicate, 1))
        self.assertEqual(tracker.status_duplicates, 1)
        tracker.apply(status_frame(STATUS_HELLO, 3, 0), 1)
        self.assertEqual(tracker.status_sequence_gaps, 1)
        self.assertIsNone(tracker.apply(status_frame(STATUS_HELLO, 2, 0), 1))
        self.assertEqual(tracker.status_stale, 1)

    def test_rejected_and_display_error_stop(self):
        tracker = self.ready_tracker()
        tracker.sent(1, 2, 1, 1)
        with self.assertRaises(AckError):
            tracker.apply(status_frame(FRAME_REJECTED, 2, 1), 2)
        tracker = self.ready_tracker()
        tracker.sent(1, 2, 1, 1)
        with self.assertRaises(AckError):
            tracker.apply(status_frame(DISPLAY_ERROR, 2, 1), 2)

    def test_tracker_bounded_and_overflow_explicit(self):
        tracker = AckTracker(capacity=2)
        tracker.sent(1, 1, 1, 0)
        tracker.sent(2, 2, 2, 0)
        with self.assertRaises(AckTrackerOverflow):
            tracker.sent(3, 3, 3, 0)
        tracker.states[0].displayed = True
        tracker.sent(3, 3, 3, 0)
        self.assertEqual(len(tracker.states), 2)

    def test_timeout_categories_are_distinct(self):
        tracker = AckTracker(start_time=0)
        with self.assertRaises(AckTimeout) as caught:
            tracker.check_timeouts(STATUS_HELLO_TIMEOUT + 0.1)
        self.assertEqual(caught.exception.category, "status_hello")
        tracker = self.ready_tracker()
        state = tracker.sent(1, 2, 1, 0)
        with self.assertRaises(AckTimeout) as caught:
            tracker.check_timeouts(FRAME_ACCEPTED_TIMEOUT + 0.1)
        self.assertEqual(caught.exception.category, "frame_accepted")
        state.accepted = True
        state.accepted_at = 0
        with self.assertRaises(AckTimeout) as caught:
            tracker.check_timeouts(REFRESH_STARTED_TIMEOUT + 0.1)
        self.assertEqual(caught.exception.category, "refresh_started")
        state.refresh_started = True
        state.started_at = 0
        with self.assertRaises(AckTimeout) as caught:
            tracker.check_timeouts(REFRESH_COMPLETED_TIMEOUT + 0.1)
        self.assertEqual(caught.exception.category, "refresh_completed")
        state.refresh_completed = True
        state.completed_at = 0
        with self.assertRaises(AckTimeout) as caught:
            tracker.check_timeouts(DISPLAY_CAUGHT_UP_TIMEOUT + 0.1)
        self.assertEqual(caught.exception.category, "display_caught_up")

    def test_superseded_revision_does_not_timeout_for_start(self):
        tracker = self.ready_tracker()
        one = tracker.sent(1, 2, 1, 0)
        one.accepted = True
        one.accepted_at = 0
        tracker.sent(2, 3, 2, 0)
        tracker.apply(status_frame(FRAME_ACCEPTED, 2, 2, {
            "received_sequence": 3, "pending_revision": 2, "superseded": True,
        }), 0.1)
        tracker.check_timeouts(REFRESH_STARTED_TIMEOUT + 0.1)
        self.assertTrue(one.superseded)


class QueueAndSchedulerTests(unittest.TestCase):
    def make_scheduler(self):
        clock = FakeClock()
        display = FakeDisplay()
        outbox = StatusQueue(32)
        scheduler = AckDisplayScheduler(
            FrameParser(), display, lambda viewport: viewport.revision,
            outbox, clock,
        )
        return clock, display, outbox, scheduler

    def test_status_queue_overflow_explicit(self):
        queue = StatusQueue(1)
        queue.offer(STATUS_HELLO, 0, FIELDS[STATUS_HELLO])
        with self.assertRaises(StatusQueueOverflow):
            queue.offer(STATUS_HELLO, 0, FIELDS[STATUS_HELLO])

    def test_input_drained_and_stale_pending_superseded_before_render(self):
        clock, display, outbox, scheduler = self.make_scheduler()
        one = ViewportMessage(1, 1, "A", ("ONE",), 0, 3, "")
        two = ViewportMessage(2, 1, "A", ("TWO",), 0, 3, "")
        scheduler.service([
            encode_frame(HELLO, 1, 0)
            + encode_frame(VIEWPORT, 2, 1, one.encode())
            + encode_frame(VIEWPORT, 3, 2, two.encode())
        ])
        self.assertEqual(scheduler.pending[0].revision, 2)
        self.assertEqual(scheduler.superseded_count, 1)
        self.assertEqual(display.calls, [])

    def test_started_status_leaves_before_physical_begin(self):
        clock, display, outbox, scheduler = self.make_scheduler()
        view = ViewportMessage(1, 1, "A", ("ONE",), 0, 3, "")
        scheduler.service([encode_frame(VIEWPORT, 1, 1, view.encode())])
        while outbox.pop() is not None:
            pass
        scheduler.service()
        self.assertEqual(len(outbox), 1)
        self.assertEqual(display.calls, [])
        self.assertEqual(outbox.pop()[0], REFRESH_STARTED)
        scheduler.service()
        self.assertEqual(len(display.calls), 1)

    def test_at_most_one_refresh_and_final_catch_up(self):
        clock, display, outbox, scheduler = self.make_scheduler()
        view = ViewportMessage(1, 1, "A", ("ONE",), 0, 3, "")
        scheduler.service([encode_frame(VIEWPORT, 1, 1, view.encode())])
        while outbox.pop() is not None:
            pass
        scheduler.service()
        outbox.pop()
        scheduler.service()
        self.assertIsNotNone(scheduler.inflight)
        scheduler.service()
        self.assertEqual(len(display.calls), 1)
        display.busy = False
        clock.now = 0.7
        scheduler.service()
        kinds = []
        item = outbox.pop()
        while item:
            kinds.append(item[0])
            item = outbox.pop()
        self.assertIn(REFRESH_COMPLETED, kinds)
        self.assertIn(DISPLAY_CAUGHT_UP, kinds)
        self.assertEqual(scheduler.displayed_revision, 1)

    def test_end_to_end_final_test_complete(self):
        clock, display, outbox, scheduler = self.make_scheduler()
        messages = ack_test_messages()
        sequence = 1
        for kind, revision, payload in messages:
            scheduler.service([encode_frame(kind, sequence, revision, payload)])
            sequence += 1
            while outbox.pop() is not None:
                pass
        for _ in range(30):
            scheduler.service()
            while outbox.pop() is not None:
                pass
            if scheduler.inflight:
                display.busy = False
                clock.now += 0.7
            if scheduler.test_complete_sent:
                break
        self.assertTrue(scheduler.test_complete_sent)
        self.assertEqual(scheduler.displayed_revision, 6)
        self.assertLessEqual(scheduler.rendered_count, 6)

    def test_end_after_catch_up_still_emits_test_complete(self):
        clock, display, outbox, scheduler = self.make_scheduler()
        view = ViewportMessage(1, 4, "A", ("FINAL",), 0, 5, "")
        scheduler.service([encode_frame(VIEWPORT, 1, 1, view.encode())])
        while outbox.pop() is not None:
            pass
        scheduler.service()
        outbox.pop()
        scheduler.service()
        display.busy = False
        scheduler.service()
        while outbox.pop() is not None:
            pass
        payload = ("1;1;%s" % view.digest()).encode("ascii")
        scheduler.service([encode_frame(END_OF_TEST, 2, 1, payload)])
        self.assertTrue(scheduler.test_complete_sent)
        self.assertEqual(outbox.pop()[0], TEST_COMPLETE)

    def test_sequence_gap_and_stale_viewport_stop(self):
        clock, display, outbox, scheduler = self.make_scheduler()
        scheduler.service([encode_frame(HELLO, 1, 0)])
        with self.assertRaises(AckSchedulerError):
            scheduler.service([encode_frame(HELLO, 3, 0)])
        clock, display, outbox, scheduler = self.make_scheduler()
        one = ViewportMessage(1, 1, "A", ("ONE",), 0, 3, "")
        scheduler.service([encode_frame(VIEWPORT, 1, 1, one.encode())])
        with self.assertRaises(AckSchedulerError):
            scheduler.service([encode_frame(VIEWPORT, 2, 1, one.encode())])

    def test_physical_scenarios_and_frame_limits(self):
        messages = ack_test_messages()
        views = [item for item in messages if item[0] == VIEWPORT]
        scenarios = {ViewportMessage.decode(revision, payload).scenario_id
                     for kind, revision, payload in views}
        self.assertEqual(scenarios, {2, 3, 4})
        self.assertLessEqual(len(messages), MAX_ACK_TOTAL_INPUT_FRAMES)
        self.assertLessEqual(len(views), MAX_ACK_VIEWPORT_FRAMES)
        self.assertLessEqual(len(messages), 100)
        self.assertLessEqual(len(views), 50)

    def test_host_imports_do_not_load_hardware(self):
        for module in (
            "magwrite.status_message", "magwrite.status_queue",
            "magwrite.ack_scheduler", "magwrite_transport.ack_tracker",
            "magwrite_transport.ack_viewports",
        ):
            importlib.import_module(module)
        self.assertNotIn("board", sys.modules)
        self.assertNotIn("busio", sys.modules)

    def test_bidirectional_physical_defaults_are_disabled(self):
        with open(os.path.join(ROOT, "magtag", "config.py"), encoding="utf-8") as handle:
            magtag_config = handle.read()
        with open(os.path.join(ROOT, "fruitjam", "config.py"), encoding="utf-8") as handle:
            fruitjam_config = handle.read()
        self.assertIn("ENABLE_UART_STATUS_TX = False", magtag_config)
        self.assertIn('BIDIRECTIONAL_UART_TEST_MODE = "DISABLED"', magtag_config)
        self.assertIn("ENABLE_BIDIRECTIONAL_UART_TEST = False", fruitjam_config)
        self.assertIn('BIDIRECTIONAL_UART_TEST_MODE = "DISABLED"', fruitjam_config)

    def test_new_guards_are_independent_and_completion_blocks_rerun(self):
        with open(
            os.path.join(ROOT, "magtag", "hardware_uart_ack_test.py"),
            encoding="utf-8",
        ) as handle:
            magtag = handle.read()
        with open(
            os.path.join(ROOT, "fruitjam", "hardware_uart_ack_test.py"),
            encoding="utf-8",
        ) as handle:
            fruitjam = handle.read()
        self.assertIn('START = "/magwrite_uart_ack_rx.started"', magtag)
        self.assertIn('COMPLETE = "/magwrite_uart_ack_rx.complete"', magtag)
        self.assertIn("if exists(START) or exists(COMPLETE)", magtag)
        self.assertIn('START = "/magwrite_uart_ack_tx.started"', fruitjam)
        self.assertIn('COMPLETE = "/magwrite_uart_ack_tx.complete"', fruitjam)
        self.assertIn("if exists(START) or exists(COMPLETE)", fruitjam)
        self.assertNotIn('"/magwrite_uart_rx.started"', magtag)
        self.assertNotIn('"/magwrite_uart_tx.started"', fruitjam)


if __name__ == "__main__":
    unittest.main()
