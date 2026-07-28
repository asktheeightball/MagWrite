import importlib
import os
import random
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.display_adapter import UART_VIEWPORT_RX_MODE, validate_physical_test_activation
from magwrite.transport_scheduler import TransportScheduler
from magwrite.uart_protocol import (
    END_OF_TEST, HEADER_SIZE, MAGIC, MAX_PAYLOAD_SIZE, MAX_RECEIVE_BUFFER,
    VERSION, VIEWPORT, FrameParser, crc32, encode_frame,
)
from magwrite.uart_receiver import UartReceiver
from magwrite.viewport_message import ViewportMessage
from magwrite_transport.deterministic_viewports import (
    MAX_TOTAL_FRAMES, MAX_VIEWPORT_FRAMES, deterministic_messages,
)
from magwrite_transport import protocol as tx_protocol


def viewport(revision=1, text="HELLO"):
    return ViewportMessage(revision, 1, "UART", (text,), 0, len(text), "OK")


def parsed(frame):
    parser = FrameParser()
    parser.feed(frame)
    return parser.pop()


def ready_receiver():
    receiver = UartReceiver()
    receiver.accept(parsed(encode_frame(1, 0, 0)))
    return receiver


class FakeDisplay:
    def __init__(self):
        self.busy = False
        self.calls = []

    def is_busy(self):
        return self.busy

    def begin_refresh(self, framebuffer, full=False):
        self.calls.append((framebuffer, full))
        self.busy = True
        return full


class ProtocolTests(unittest.TestCase):
    def test_deterministic_encoding(self):
        self.assertEqual(encode_frame(VIEWPORT, 1, 2, b"x"), encode_frame(VIEWPORT, 1, 2, b"x"))

    def test_byte_layout(self):
        wire = encode_frame(VIEWPORT, 0x01020304, 5, b"x")
        self.assertEqual(wire[:4], MAGIC + bytes((VERSION, VIEWPORT)))
        self.assertEqual(wire[4:8], b"\x01\x02\x03\x04")
        self.assertEqual(int.from_bytes(wire[12:14], "big"), 1)

    def test_decode(self):
        frame = parsed(encode_frame(VIEWPORT, 3, 7, b"abc"))
        self.assertEqual((frame.sequence, frame.revision, frame.payload), (3, 7, b"abc"))

    def test_crc_known_vector(self):
        self.assertEqual(crc32(b"123456789"), 0xCBF43926)

    def test_bad_crc_rejected(self):
        wire = bytearray(encode_frame(VIEWPORT, 1, 1, b"x"))
        wire[-1] ^= 1
        parser = FrameParser()
        parser.feed(wire)
        self.assertIsNone(parser.pop())
        self.assertEqual(parser.crc_failures, 1)

    def test_byte_at_a_time(self):
        parser = FrameParser()
        wire = encode_frame(VIEWPORT, 1, 1, b"abc")
        for byte in wire[:-1]:
            parser.feed(bytes((byte,)))
            self.assertIsNone(parser.pop())
        parser.feed(wire[-1:])
        self.assertEqual(parser.pop().payload, b"abc")

    def test_random_chunks(self):
        random.seed(7)
        wire = encode_frame(VIEWPORT, 1, 1, b"abcdef")
        parser = FrameParser()
        at = 0
        while at < len(wire):
            size = random.randint(1, 4)
            parser.feed(wire[at:at + size])
            at += size
        self.assertEqual(parser.pop().payload, b"abcdef")

    def test_two_frames_one_chunk(self):
        parser = FrameParser()
        parser.feed(encode_frame(VIEWPORT, 1, 1) + encode_frame(VIEWPORT, 2, 2))
        self.assertEqual(parser.pop().sequence, 1)
        self.assertEqual(parser.pop().sequence, 2)

    def test_garbage_resync(self):
        parser = FrameParser()
        parser.feed(b"noise!" + encode_frame(VIEWPORT, 9, 9))
        self.assertEqual(parser.pop().sequence, 9)

    def test_truncated_buffering(self):
        parser = FrameParser()
        parser.feed(encode_frame(VIEWPORT, 1, 1)[:-2])
        self.assertIsNone(parser.pop())
        self.assertTrue(parser.buffer)

    def test_oversized_header_rejected(self):
        parser = FrameParser()
        parser.feed(MAGIC + bytes((VERSION, VIEWPORT)) + b"\0" * 8
                    + (MAX_PAYLOAD_SIZE + 1).to_bytes(2, "big"))
        self.assertIsNone(parser.pop())
        self.assertEqual(parser.oversized, 1)

    def test_buffer_bounded_under_garbage(self):
        parser = FrameParser()
        parser.feed(b"x" * 1000)
        parser.pop()
        self.assertLessEqual(len(parser.buffer), MAX_RECEIVE_BUFFER)
        self.assertEqual(parser.buffer_overflows, 1)

    def test_bad_version(self):
        wire = bytearray(encode_frame(VIEWPORT, 1, 1))
        wire[2] = VERSION + 1
        parser = FrameParser()
        parser.feed(wire)
        parser.pop()
        self.assertEqual(parser.version_failures, 1)

    def test_unknown_type(self):
        wire = bytearray(encode_frame(VIEWPORT, 1, 1))
        wire[3] = 99
        parser = FrameParser()
        parser.feed(wire)
        parser.pop()
        self.assertEqual(parser.type_failures, 1)

    def test_oversized_encode(self):
        with self.assertRaises(ValueError):
            encode_frame(VIEWPORT, 1, 1, b"x" * (MAX_PAYLOAD_SIZE + 1))

    def test_sender_receiver_constant_parity(self):
        for name in ("MAGIC", "VERSION", "HEADER_SIZE", "CRC_SIZE",
                     "MAX_PAYLOAD_SIZE", "HELLO", "VIEWPORT", "END_OF_SCENARIO", "END_OF_TEST"):
            self.assertEqual(getattr(tx_protocol, name), globals().get(name, getattr(importlib.import_module("magwrite.uart_protocol"), name)))


class ViewportTests(unittest.TestCase):
    def test_round_trip(self):
        original = viewport()
        decoded = ViewportMessage.decode(1, original.encode())
        self.assertEqual((decoded.title, decoded.lines, decoded.cursor_column),
                         ("UART", ("HELLO",), 5))

    def test_title_bound(self):
        with self.assertRaises(ValueError):
            ViewportMessage(1, 1, "X" * 21, ("A",), 0, 0, "")

    def test_line_bound(self):
        with self.assertRaises(ValueError):
            ViewportMessage(1, 1, "", ("X" * 29,), 0, 0, "")

    def test_line_count_bound(self):
        with self.assertRaises(ValueError):
            ViewportMessage(1, 1, "", ("A", "B", "C", "D"), 0, 0, "")

    def test_cursor_row_bound(self):
        with self.assertRaises(ValueError):
            ViewportMessage(1, 1, "", ("A",), 1, 0, "")

    def test_cursor_column_bound(self):
        with self.assertRaises(ValueError):
            ViewportMessage(1, 1, "", ("A",), 0, 2, "")

    def test_ascii_only(self):
        with self.assertRaises(ValueError):
            ViewportMessage(1, 1, "é", ("A",), 0, 0, "")


class ReceiverSchedulerTests(unittest.TestCase):
    def test_duplicate_sequence(self):
        receiver = ready_receiver()
        frame = parsed(encode_frame(VIEWPORT, 1, 1, viewport().encode()))
        receiver.accept(frame)
        receiver.accept(frame)
        self.assertEqual(receiver.duplicates, 1)

    def test_stale_revision(self):
        receiver = ready_receiver()
        receiver.accept(parsed(encode_frame(VIEWPORT, 1, 2, viewport(2).encode())))
        receiver.accept(parsed(encode_frame(VIEWPORT, 2, 1, viewport(1).encode())))
        self.assertEqual(receiver.stale, 1)

    def test_sequence_gap(self):
        receiver = ready_receiver()
        receiver.accept(parsed(encode_frame(1, 1, 0)))
        receiver.accept(parsed(encode_frame(1, 3, 0)))
        self.assertEqual(receiver.sequence_gaps, 1)

    def test_newest_coalesces(self):
        receiver = ready_receiver()
        receiver.accept(parsed(encode_frame(VIEWPORT, 1, 1, viewport(1, "A").encode())))
        receiver.accept(parsed(encode_frame(VIEWPORT, 2, 2, viewport(2, "B").encode())))
        self.assertEqual(receiver.take_pending().lines, ("B",))
        self.assertEqual(receiver.superseded, 1)

    def test_drain_before_render(self):
        parser, receiver, display = FrameParser(), ready_receiver(), FakeDisplay()
        scheduler = TransportScheduler(parser, receiver, display, lambda view: view.revision)
        chunks = [encode_frame(VIEWPORT, 1, 1, viewport(1, "A").encode())
                  + encode_frame(VIEWPORT, 2, 2, viewport(2, "B").encode())]
        scheduler.service(chunks)
        self.assertEqual(display.calls[0][0], 2)
        self.assertEqual(scheduler.rendered, 1)

    def test_one_refresh_inflight(self):
        parser, receiver, display = FrameParser(), ready_receiver(), FakeDisplay()
        scheduler = TransportScheduler(parser, receiver, display, lambda view: view.revision)
        scheduler.service([encode_frame(VIEWPORT, 1, 1, viewport().encode())])
        scheduler.service([encode_frame(VIEWPORT, 2, 2, viewport(2).encode())])
        self.assertEqual(len(display.calls), 1)

    def test_catch_up_after_busy(self):
        parser, receiver, display = FrameParser(), ready_receiver(), FakeDisplay()
        scheduler = TransportScheduler(parser, receiver, display, lambda view: view.revision)
        scheduler.service([encode_frame(VIEWPORT, 1, 1, viewport().encode())])
        scheduler.service([encode_frame(VIEWPORT, 2, 2, viewport(2).encode())])
        display.busy = False
        scheduler.service()
        self.assertEqual(scheduler.inflight_revision, 2)
        display.busy = False
        scheduler.service()
        self.assertEqual(scheduler.displayed_revision, 2)

    def test_display_never_exceeds_received(self):
        parser, receiver, display = FrameParser(), ready_receiver(), FakeDisplay()
        scheduler = TransportScheduler(parser, receiver, display, lambda view: view.revision)
        scheduler.service([encode_frame(VIEWPORT, 1, 4, viewport(4).encode())])
        display.busy = False
        scheduler.service()
        self.assertLessEqual(scheduler.displayed_revision, receiver.latest_revision)

    def test_final_hash_reconciliation(self):
        receiver = ready_receiver()
        view = viewport(3)
        receiver.accept(parsed(encode_frame(VIEWPORT, 1, 3, view.encode())))
        end = ("3;1;%s" % view.digest()).encode("ascii")
        receiver.accept(parsed(encode_frame(END_OF_TEST, 2, 3, end)))
        self.assertTrue(receiver.final_hash_valid)


class ScenarioAndSafetyTests(unittest.TestCase):
    def test_four_scenarios_and_limits(self):
        messages = deterministic_messages()
        viewports = [item for item in messages if item[0] == VIEWPORT]
        scenarios = {ViewportMessage.decode(revision, payload).scenario_id
                     for kind, revision, payload in viewports}
        self.assertEqual(scenarios, {1, 2, 3, 4})
        self.assertLessEqual(len(messages), MAX_TOTAL_FRAMES)
        self.assertLessEqual(len(viewports), MAX_VIEWPORT_FRAMES)
        self.assertEqual(len(viewports), 11)

    def test_deterministic_scenarios(self):
        self.assertEqual(deterministic_messages(), deterministic_messages())

    def test_final_scenario_pre_windowed(self):
        views = [ViewportMessage.decode(r, p) for k, r, p in deterministic_messages() if k == VIEWPORT]
        self.assertEqual(views[-1].lines[0], "< FIVE DOZEN LIQUOR JUGS")
        self.assertIn("J", views[-1].lines[1])

    def test_activation_fail_closed(self):
        cfg = types.SimpleNamespace(HARDWARE_COMPATIBILITY_DECISION="COMPATIBLE",
                                    DISPLAY_CONTROLLER="UC8151D",
                                    ENABLE_PHYSICAL_DISPLAY=False)
        with self.assertRaises(RuntimeError):
            validate_physical_test_activation(cfg, UART_VIEWPORT_RX_MODE)

    def test_defaults_disabled(self):
        for path, names in (
            ("magtag/config.py", ("ENABLE_PHYSICAL_DISPLAY = False", "ENABLE_UART_RECEIVER = False")),
            ("fruitjam/config.py", ("ENABLE_UART_TEST = False", 'UART_TEST_MODE = "DISABLED"')),
        ):
            with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
                text = handle.read()
            for name in names:
                self.assertIn(name, text)

    def test_independent_guards_and_previous_preserved(self):
        with open(os.path.join(ROOT, "fruitjam/code.py"), encoding="utf-8") as handle:
            tx = handle.read()
        with open(os.path.join(ROOT, "magtag/hardware_uart_viewport_test.py"), encoding="utf-8") as handle:
            rx = handle.read()
        self.assertIn("magwrite_uart_tx.started", tx)
        self.assertIn("magwrite_uart_rx.started", rx)
        for old in ("magwrite_refresh_test_20", "magwrite_refresh_test_50",
                    "magwrite_refresh_test_100", "magwrite_single_line_typing"):
            self.assertNotIn(old, tx + rx)

    def test_hardware_imports_isolated(self):
        for module in ("magwrite.uart_protocol", "magwrite.viewport_message",
                       "magwrite.uart_receiver", "magwrite.transport_scheduler",
                       "magwrite_transport.protocol",
                       "magwrite_transport.deterministic_viewports"):
            importlib.import_module(module)


if __name__ == "__main__":
    unittest.main()
