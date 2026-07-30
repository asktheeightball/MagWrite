"""Waiting for a MagTag that could not be started first.

One-cable power is what makes this a required behaviour rather than a nicety.
The MagTag is powered from a Fruit Jam USB-A host port, and those ports carry no
5 V while the Fruit Jam is held in reset -- so the documented "restart the MagTag
first, then the Fruit Jam" procedure is not a sequence the hardware can perform.
Both boards cold boot together, the Fruit Jam wins the race because it has no
e-paper panel to initialise, and the first handshake therefore arrives at a board
that is not listening yet.

Every test here drives the real Fruit Jam session, the real frame encoder and
parser, the real acknowledgement tracker, and the real MagTag scheduler. The only
thing simulated is the one thing that is physically true of an unpowered board:
bytes sent to it go nowhere, and are never delivered late.
"""

import ast
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from keyboard_simulator import KeyboardLink, finish, type_characters
from magwrite.ack_scheduler import AckDisplayScheduler, AckSchedulerError
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import HELLO as MAGTAG_HELLO
from magwrite.uart_protocol import STATUS_HELLO as MAGTAG_STATUS_HELLO
from magwrite.uart_protocol import FrameParser as InputParser
from magwrite.viewport_renderer import render_viewport
from magwrite_transport.ack_tracker import AckTracker, AckTimeout
from magwrite_transport.deterministic_viewports import encode_viewport
from magwrite_transport.journal import Snapshot
from magwrite_transport.live_session import HELLO_RETRY_SECONDS
from magwrite_transport.protocol import (
    HELLO, STATUS_HELLO, VERSION, VIEWPORT, FrameParser, encode_frame,
)


def fruitjam_config_values():
    """The Fruit Jam's own ``config.py``, read as source.

    Both boards ship a module named ``config``, so importing one by name here
    would resolve to whichever is earlier on the path. Every other test that
    asserts a Fruit Jam configuration value reads the file for the same reason.
    """
    values = {}
    path = os.path.join(ROOT, "fruitjam", "config.py")
    with open(path, "r") as handle:
        for line in handle.read().splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            name, _, raw = line.partition("=")
            try:
                values[name.strip()] = ast.literal_eval(raw.strip())
            except (SyntaxError, ValueError):
                pass
    return values

# Long enough that the tracker's own five-second hello timeout would have fired
# several times over, so these runs prove the wait is genuinely open-ended rather
# than merely longer than it used to be.
DISPLAY_BOOT_SECONDS = 10.0
RESTORED_TEXT = "the words that were already here"
TYPED_TEXT = " and the ones typed after"


def late_display_link(**options):
    """One session whose panel only powers up part-way through the wait."""
    reports = type_characters(TYPED_TEXT) + finish()
    return KeyboardLink(
        reports,
        display_ready_at=DISPLAY_BOOT_SECONDS,
        typing_interval_seconds=0.05,
        # Comfortably after the handshake can first succeed, so the script is
        # measuring the wait rather than racing it. The keyboard is on the Fruit
        # Jam's own hub and is live from the first moment either way.
        typing_start_seconds=DISPLAY_BOOT_SECONDS + HELLO_RETRY_SECONDS * 2,
        **options
    )


def status_hello_frame(sequence):
    """The reply a freshly booted MagTag sends, numbered from its own start.

    Built with the MagTag's own encoder through its own bounded outbox, so this
    is the real frame rather than a hand-assembled lookalike; only the sequence
    number is chosen, which is the whole point of the test.
    """
    outbox = StatusQueue(4)
    outbox.next_sequence = sequence
    outbox.offer(MAGTAG_STATUS_HELLO, 0, {
        "protocol_version": VERSION,
        "app_version": 1,
        "displayed_revision": 0,
        "receiver_ready": True,
        "display_ready": True,
        "test_id": "MAGWRITE-UART-ACK",
    })
    return outbox.pop()[3]


class LateDisplayRunTest(unittest.TestCase):
    """One shared run: the Fruit Jam starts first and waits for the panel."""

    @classmethod
    def setUpClass(cls):
        link = late_display_link()
        # The document the writer had before the power cut, loaded exactly as
        # ``dev_runtime`` loads a recovered one: before the session runs, and
        # never touched by anything the wait does.
        link.session.restore(
            Snapshot(7, 0, len(RESTORED_TEXT), RESTORED_TEXT)
        )
        cls.link = link.run()
        cls.summary = cls.link.session.summary("PASS")
        cls.records = cls.link.records

    def events(self, name):
        return [r for r in self.records if r.get("event") == name]

    # ------------------------------------------------------- the wait itself

    def test_the_session_survives_the_attempts_that_went_nowhere(self):
        """Requirement 1: one unanswered handshake is not a stopped session."""
        self.assertTrue(self.link.session.complete)
        self.assertGreater(self.link.display_bytes_lost, 0)
        self.assertIsNone(self.link.session.stop_reason)

    def test_the_handshake_is_retried_until_the_panel_answers(self):
        """Requirement 2, and past the point the old single shot gave up."""
        attempts = self.summary["hello_attempts"]
        self.assertGreaterEqual(
            attempts, int(DISPLAY_BOOT_SECONDS / HELLO_RETRY_SECONDS)
        )
        waits = self.events("live_waiting_for_display")
        self.assertEqual(len(waits), attempts - 1)
        self.assertEqual(
            [record["attempt"] for record in waits],
            list(range(2, attempts + 1)),
        )

    def test_the_wait_outlasts_the_trackers_own_hello_timeout(self):
        """The bound that used to end the run is genuinely superseded."""
        tracker_timeout = self.link.session.tracker.hello_timeout
        self.assertGreater(DISPLAY_BOOT_SECONDS, tracker_timeout)
        self.assertGreater(self.summary["display_wait_seconds"], tracker_timeout)

    def test_a_late_display_is_accepted_and_the_session_proceeds(self):
        """Requirement 3: the panel that arrives late is still the panel."""
        started = self.events("live_typing_started")
        self.assertEqual(len(started), 1)
        self.assertGreaterEqual(
            started[0]["display_wait_seconds"], DISPLAY_BOOT_SECONDS
        )
        self.assertEqual(started[0]["hello_attempts"], self.summary["hello_attempts"])
        self.assertGreater(self.summary["viewport_frames_sent"], 0)
        self.assertTrue(self.summary["test_complete"])

    def test_no_sequence_failure_is_latched_on_either_board(self):
        """Requirement 4, from both ends of the same wire."""
        self.assertEqual(self.summary["crc_failures"], 0)
        self.assertEqual(self.summary["status_frames_rejected"], 0)
        self.assertEqual(self.summary["status_duplicates"], 0)
        self.assertEqual(self.summary["status_stale"], 0)
        self.assertEqual(self.summary["status_sequence_gaps"], 0)
        self.assertEqual(self.summary["display_handshake_restarts"], 0)
        self.assertEqual(self.link.scheduler.error_count, 0)

    def test_the_retried_handshake_never_reuses_a_frame_sequence(self):
        """The one property a retry could break on the far board.

        Restarting the count is exactly what produces ``duplicate or reversed
        input sequence`` on the MagTag, so every attempt takes the next number
        and the stream the panel eventually hears is monotonic from wherever it
        happened to start listening.
        """
        parser = FrameParser()
        sequences = []
        for record in self.events("live_waiting_for_display"):
            sequences.append(record["sequence"])
        self.assertEqual(sequences, sorted(set(sequences)))
        self.assertEqual(sequences, list(range(2, len(sequences) + 2)))
        # And the frames themselves say the same thing, decoded rather than
        # taken from a log line.
        parser.feed(encode_frame(HELLO, sequences[-1], 0, b""))
        self.assertEqual(parser.pop().sequence, sequences[-1])

    # ------------------------------------------------------- the document

    def test_the_restored_document_is_not_discarded_by_the_wait(self):
        """Requirement 5. The words are the whole point of waiting at all."""
        self.assertEqual(
            self.summary["final_document_text"], RESTORED_TEXT + TYPED_TEXT
        )
        restored = self.events("live_document_restored")
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["characters"], len(RESTORED_TEXT))

    def test_the_wait_reports_the_document_it_is_holding(self):
        """Requirement 6: a waiting state an operator can read, per attempt."""
        for record in self.events("live_waiting_for_display"):
            self.assertEqual(record["document_characters"], len(RESTORED_TEXT))
            self.assertTrue(record["document_preserved"])
            self.assertGreater(record["waiting_seconds"], 0)

    def test_the_wait_does_not_spend_the_writing_sessions_budget(self):
        """A panel that took ten seconds is not a session that ran long."""
        self.assertGreaterEqual(
            self.link.session.started_at, DISPLAY_BOOT_SECONDS
        )

    # ------------------------------------------------- everything downstream

    def test_the_session_behaves_exactly_as_it_always_did_afterwards(self):
        """Requirement 7. Nothing past the handshake knows a wait happened."""
        self.assertEqual(self.summary["events_rejected"], 0)
        self.assertEqual(self.summary["queue_overflows"], 0)
        self.assertEqual(self.summary["resynchronization_events"], 0)
        self.assertEqual(
            self.summary["final_displayed_revision"],
            self.summary["final_transmitted_revision"],
        )
        self.assertEqual(self.link.scheduler.displayed_revision,
                         self.link.scheduler.latest_revision)


class ReadyDisplayIsUnchangedTest(unittest.TestCase):
    """A panel that was already listening must see no new behaviour at all."""

    @classmethod
    def setUpClass(cls):
        cls.link = KeyboardLink(
            type_characters("ready from the start") + finish()
        ).run()
        cls.summary = cls.link.session.summary("PASS")

    def test_one_handshake_attempt_and_no_wait(self):
        self.assertEqual(self.summary["hello_attempts"], 1)
        self.assertLess(self.summary["display_wait_seconds"], HELLO_RETRY_SECONDS)
        self.assertEqual(self.summary["display_handshake_restarts"], 0)
        self.assertEqual(self.link.display_bytes_lost, 0)

    def test_nothing_reports_a_wait_that_did_not_happen(self):
        self.assertEqual(
            [r for r in self.link.records
             if r.get("event") == "live_waiting_for_display"],
            [],
        )

    def test_the_run_still_completes_normally(self):
        self.assertTrue(self.link.session.complete)
        self.assertTrue(self.summary["test_complete"])
        self.assertEqual(
            self.summary["final_document_text"], "ready from the start"
        )


class DocumentIsUntouchedDuringTheWaitTest(unittest.TestCase):
    """Requirement 5, asserted *during* the wait rather than after it."""

    def test_nothing_edits_saves_or_re_derives_the_document(self):
        link = late_display_link()
        link.session.restore(Snapshot(7, 0, len(RESTORED_TEXT), RESTORED_TEXT))
        revision = link.session.editor.document_revision
        viewport_revision = link.session.editor.viewport_revision
        link.run_until(DISPLAY_BOOT_SECONDS - 1.0)
        self.assertFalse(link.session.complete)
        self.assertEqual(link.session.editor.text, RESTORED_TEXT)
        self.assertEqual(link.session.editor.document_revision, revision)
        self.assertEqual(
            link.session.editor.viewport_revision, viewport_revision
        )
        # And no frame that is not a handshake attempt has been produced.
        self.assertEqual(link.session.viewport_frames_sent, 0)
        self.assertEqual(
            link.session.frame_sequence, link.session.hello_attempts
        )


class HandshakeFaultsAreNotFatalTest(unittest.TestCase):
    """A board that answers badly during the wait costs an attempt, not a run."""

    def setUp(self):
        self.link = late_display_link()

    def test_a_reply_numbered_from_a_restarted_board_is_still_heard(self):
        """The MagTag rebooted mid-wait and started its replies at 1 again."""
        session = self.link.session
        session.service()
        session.take_outbound()
        session.feed(status_hello_frame(9))
        session.service()
        self.assertTrue(session.tracker.hello)

    def test_a_stale_reply_does_not_strand_the_handshake_forever(self):
        """The failure this would be without the re-baseline.

        A board that answers at sequence 1 after the tracker has already seen 9
        would be counted stale and dropped. Re-baselining each attempt is what
        makes the *next* attempt able to hear it.
        """
        session = self.link.session
        session.service()
        session.take_outbound()
        session.feed(status_hello_frame(9))
        session.service()
        session.tracker.hello = False
        session.feed(status_hello_frame(1))
        session.service()
        self.assertFalse(session.tracker.hello)
        session.tracker.restart_handshake(0.0)
        session.feed(status_hello_frame(1))
        session.service()
        self.assertTrue(session.tracker.hello)

    def test_garbage_from_a_powering_up_board_does_not_latch_a_failure(self):
        """Requirement 4 and 6: a bad attempt is abandoned, not remembered."""
        session = self.link.session
        session.service()
        session.take_outbound()
        # A frame with the right shape and the wrong CRC, which is what a
        # half-clocked byte stream looks like once it resynchronises.
        corrupt = bytearray(encode_frame(STATUS_HELLO, 1, 0, b"1;1;0;1;1;X"))
        corrupt[-1] ^= 0xFF
        session.feed(bytes(corrupt))
        session.service()
        self.assertEqual(session.handshake_restarts, 1)
        self.assertEqual(session.parser.crc_failures, 0)
        self.assertFalse(session.complete)
        # The next attempt is a clean one and completes normally.
        session.feed(status_hello_frame(1))
        session.service()
        self.assertTrue(session.tracker.hello)

    def test_the_restart_is_reported_with_its_cause_and_its_document(self):
        session = self.link.session
        session.restore(Snapshot(3, 0, len(RESTORED_TEXT), RESTORED_TEXT))
        session.service()
        session.take_outbound()
        corrupt = bytearray(encode_frame(STATUS_HELLO, 1, 0, b"1;1;0;1;1;X"))
        corrupt[-1] ^= 0xFF
        session.feed(bytes(corrupt))
        session.service()
        restarts = [r for r in self.link.records
                    if r.get("event") == "live_display_handshake_restarted"]
        self.assertEqual(len(restarts), 1)
        self.assertTrue(restarts[0]["detail"])
        self.assertEqual(restarts[0]["document_characters"], len(RESTORED_TEXT))


class TrackerHandshakeRestartTest(unittest.TestCase):
    """The one piece of state a failed attempt leaves behind, in isolation."""

    def test_it_clears_the_status_numbering_and_re_arms_the_timeout(self):
        tracker = AckTracker(start_time=0.0)
        tracker.last_status_sequence = 40
        tracker.hello = True
        tracker.restart_handshake(100.0)
        self.assertIsNone(tracker.last_status_sequence)
        self.assertFalse(tracker.hello)
        self.assertEqual(tracker.started_at, 100.0)

    def test_it_moves_the_hello_timeout_with_the_attempt(self):
        tracker = AckTracker(start_time=0.0)
        with self.assertRaises(AckTimeout):
            tracker.check_timeouts(tracker.hello_timeout + 0.1)
        tracker.restart_handshake(tracker.hello_timeout + 0.1)
        tracker.check_timeouts(tracker.hello_timeout + 0.2)

    def test_it_leaves_transmitted_viewport_state_alone(self):
        tracker = AckTracker(start_time=0.0)
        tracker.sent(1, 1, 0xABCD, 0.0)
        tracker.restart_handshake(1.0)
        self.assertEqual(len(tracker.states), 1)
        self.assertEqual(tracker.latest_sent_revision, 1)


class SchedulerHandshakeRebaselineTest(unittest.TestCase):
    """The MagTag end: which frame may restart the input numbering, and when."""

    def build(self):
        parser = InputParser()
        return parser, AckDisplayScheduler(
            parser, _NeverBusyPanel(), render_viewport, StatusQueue(32),
            lambda: 0.0,
        )

    def feed(self, parser, scheduler, frame):
        scheduler.service((frame,))

    def test_a_handshake_may_arrive_at_any_number(self):
        """The ordinary one-cable case: this board booted last and heard #4."""
        parser, scheduler = self.build()
        self.feed(parser, scheduler, encode_frame(HELLO, 4, 0, b"X"))
        self.assertEqual(scheduler.last_input_sequence, 4)
        self.assertEqual(scheduler.handshake_rebaselines, 0)

    def test_a_repeated_handshake_restarts_the_count_instead_of_failing(self):
        """The Fruit Jam restarted before anything was ever displayed."""
        parser, scheduler = self.build()
        self.feed(parser, scheduler, encode_frame(HELLO, 6, 0, b"X"))
        self.feed(parser, scheduler, encode_frame(HELLO, 1, 0, b"X"))
        self.assertEqual(scheduler.last_input_sequence, 1)
        self.assertEqual(scheduler.handshake_rebaselines, 1)

    def test_a_handshake_after_a_dropped_frame_restarts_the_count_too(self):
        parser, scheduler = self.build()
        self.feed(parser, scheduler, encode_frame(HELLO, 2, 0, b"X"))
        self.feed(parser, scheduler, encode_frame(HELLO, 9, 0, b"X"))
        self.assertEqual(scheduler.last_input_sequence, 9)
        self.assertEqual(scheduler.handshake_rebaselines, 1)

    def test_every_handshake_is_answered(self):
        parser, scheduler = self.build()
        for sequence in (6, 1, 2):
            self.feed(parser, scheduler, encode_frame(HELLO, sequence, 0, b"X"))
        replies = [scheduler.outbox.pop() for _ in range(len(scheduler.outbox))]
        self.assertEqual(len(replies), 3)

    def test_sequence_discipline_is_absolute_once_a_viewport_arrives(self):
        """The narrowness of the rule is the point: a live session is strict."""
        parser, scheduler = self.build()
        self.feed(parser, scheduler, encode_frame(HELLO, 1, 0, b"X"))
        self.feed(parser, scheduler, _viewport_frame(2, 1))
        with self.assertRaises(AckSchedulerError) as caught:
            self.feed(parser, scheduler, encode_frame(HELLO, 1, 0, b"X"))
        self.assertEqual(
            str(caught.exception), "duplicate or reversed input sequence"
        )
        self.assertEqual(scheduler.handshake_rebaselines, 0)

    def test_a_viewport_may_never_restart_the_numbering(self):
        parser, scheduler = self.build()
        self.feed(parser, scheduler, encode_frame(HELLO, 5, 0, b"X"))
        with self.assertRaises(AckSchedulerError):
            self.feed(parser, scheduler, _viewport_frame(2, 1))

    def test_the_frame_type_is_the_one_both_boards_agree_on(self):
        """The boards share no import, so the constant is asserted equal."""
        self.assertEqual(MAGTAG_HELLO, HELLO)


class ConfiguredRetryIntervalTest(unittest.TestCase):
    """One source of truth for the interval, as with every other bound here."""

    def test_the_fruit_jam_config_mirrors_the_module_constant(self):
        values = fruitjam_config_values()
        self.assertEqual(
            values["DISPLAY_HANDSHAKE_RETRY_SECONDS"], HELLO_RETRY_SECONDS
        )

    def test_the_interval_is_shorter_than_the_wait_it_replaces(self):
        """A retry that is slower than the old give-up would be no improvement."""
        values = fruitjam_config_values()
        self.assertLess(
            values["DISPLAY_HANDSHAKE_RETRY_SECONDS"],
            values["STATUS_HELLO_TIMEOUT_SECONDS"],
        )

    def test_the_runtime_passes_it_rather_than_a_literal(self):
        path = os.path.join(ROOT, "fruitjam", "dev_runtime.py")
        with open(path, "r") as handle:
            source = handle.read()
        self.assertIn(
            "hello_retry_seconds=config.DISPLAY_HANDSHAKE_RETRY_SECONDS", source
        )


class _NeverBusyPanel:
    """A panel that completes instantly; refresh timing is not under test."""

    def begin_refresh(self, framebuffer, full=False):
        return full

    def is_busy(self):
        return False


def _viewport_frame(sequence, revision):
    """One minimal but real viewport frame, encoded the way the session does."""
    payload = encode_viewport(1, "MAGWRITE", ("a line",), 0, 6, "R1")
    return encode_frame(VIEWPORT, sequence, revision, payload)


if __name__ == "__main__":
    unittest.main()
