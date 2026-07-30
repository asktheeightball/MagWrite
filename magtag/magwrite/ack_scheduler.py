"""Host-safe bidirectional display scheduler with bounded status output."""

from magwrite.status_message import FULL_REFRESH, PARTIAL_REFRESH
from magwrite.uart_protocol import (
    DISPLAY_CAUGHT_UP,
    END_OF_TEST,
    FRAME_ACCEPTED,
    HELLO,
    REFRESH_COMPLETED,
    REFRESH_STARTED,
    STATUS_HELLO,
    TEST_COMPLETE,
    VERSION,
    VIEWPORT,
)
from magwrite.viewport_message import ViewportMessage


class AckSchedulerError(Exception):
    pass


class AckDisplayScheduler:
    def __init__(
        self, parser, display, render, outbox, monotonic, frame_budget=16,
        completion_capacity=32,
    ):
        self.parser = parser
        self.display = display
        self.render = render
        self.outbox = outbox
        self.monotonic = monotonic
        self.frame_budget = frame_budget
        self.completion_capacity = completion_capacity
        self.pending = None
        self.ready_to_start = None
        self.inflight = None
        self.displayed_revision = 0
        self.latest_revision = 0
        self.latest_hash = 0
        self.last_input_sequence = None
        self.accepted_count = 0
        self.rendered_count = 0
        self.superseded_count = 0
        self.refresh_count = 0
        self.error_count = 0
        self.last_caught_up = 0
        self.end_received = False
        self.expected_final_revision = None
        self.expected_final_hash = None
        self.test_complete_sent = False
        self.completions = []
        # Counted so a run that needed one says so. See ``_may_rebaseline``.
        self.handshake_rebaselines = 0

    def feed_chunks(self, chunks):
        for chunk in chunks:
            self.parser.feed(chunk)

    def _may_rebaseline(self, frame):
        """Whether this frame is allowed to restart the input numbering.

        Exactly one frame ever is: a ``HELLO`` that arrives before this session
        has accepted a single viewport. That is the handshake, and a handshake is
        by definition the start of a count rather than a continuation of one.

        Added for one-cable power. The MagTag is powered from a Fruit Jam USB-A
        port, so it cannot be started first and both boards cold boot together;
        the Fruit Jam therefore retries its handshake while this board's panel
        initialises, and either board may restart during that window. Before this
        rule, the second board to boot would refuse the first frame it ever saw
        because the numbers did not begin where it expected -- reported as
        ``duplicate or reversed input sequence``, which named the symptom and
        nothing about the cause. It cost false starts in three bench runs.

        The rule is narrow on purpose. Once a viewport has been accepted, or one
        is pending, in flight, or about to start, sequence discipline is absolute
        again: that is a session with the writer's words moving through it, and a
        gap or a repeat there is a real transport fault.
        """
        return (
            frame.message_type == HELLO
            and self.latest_revision == 0
            and self.pending is None
            and self.ready_to_start is None
            and self.inflight is None
        )

    def _accept_sequence(self, frame):
        if self.last_input_sequence is not None:
            if frame.sequence <= self.last_input_sequence:
                if not self._may_rebaseline(frame):
                    raise AckSchedulerError("duplicate or reversed input sequence")
                self.handshake_rebaselines += 1
            elif frame.sequence != self.last_input_sequence + 1:
                if not self._may_rebaseline(frame):
                    raise AckSchedulerError("input sequence gap")
                self.handshake_rebaselines += 1
        self.last_input_sequence = frame.sequence

    def _status(self, message_type, revision, fields):
        self.outbox.offer(message_type, revision, fields)

    def _accept_frame(self, frame):
        self._accept_sequence(frame)
        if frame.message_type == HELLO:
            self._status(STATUS_HELLO, self.displayed_revision, {
                "protocol_version": VERSION,
                "app_version": 1,
                "displayed_revision": self.displayed_revision,
                "receiver_ready": True,
                "display_ready": True,
                "test_id": "MAGWRITE-UART-ACK",
            })
            return
        if frame.message_type == VIEWPORT:
            viewport = ViewportMessage.decode(frame.revision, frame.payload)
            if frame.revision <= self.latest_revision:
                raise AckSchedulerError("stale viewport revision")
            superseded = self.pending is not None
            if superseded:
                self.superseded_count += 1
            self.pending = (viewport, frame.sequence)
            self.latest_revision = frame.revision
            self.latest_hash = int(viewport.digest(), 16)
            self.accepted_count += 1
            self._status(FRAME_ACCEPTED, frame.revision, {
                "received_sequence": frame.sequence,
                "pending_revision": frame.revision,
                "superseded": superseded,
            })
            return
        if frame.message_type == END_OF_TEST:
            try:
                revision, count, digest = frame.payload.decode("ascii").split(";")
                self.expected_final_revision = int(revision)
                expected_count = int(count)
                self.expected_final_hash = int(digest, 16)
            except (UnicodeError, ValueError):
                raise AckSchedulerError("malformed END_OF_TEST")
            if expected_count != self.accepted_count:
                raise AckSchedulerError("final viewport count mismatch")
            self.end_received = True

    def _complete_if_idle(self, now):
        if self.inflight is None or self.display.is_busy():
            return False
        viewport, sequence, started, full = self.inflight
        duration_ms = int((now - started) * 1000)
        self.inflight = None
        self.displayed_revision = viewport.revision
        self.refresh_count += 1
        stale = viewport.revision != self.latest_revision
        if len(self.completions) >= self.completion_capacity:
            raise AckSchedulerError("completion history overflow")
        self.completions.append((viewport.revision, duration_ms, full, stale))
        self._status(REFRESH_COMPLETED, viewport.revision, {
            "viewport_sequence": sequence,
            "duration_ms": duration_ms,
            "latest_received_revision": self.latest_revision,
            "stale": stale,
        })
        return True

    def _caught_up_if_ready(self):
        if (
            self.inflight is None
            and self.ready_to_start is None
            and self.pending is None
            and self.latest_revision
            and self.displayed_revision == self.latest_revision
            and self.last_caught_up != self.displayed_revision
        ):
            self.last_caught_up = self.displayed_revision
            self._status(DISPLAY_CAUGHT_UP, self.displayed_revision, {
                "displayed_revision": self.displayed_revision,
                "latest_received_revision": self.latest_revision,
                "viewport_hash": self.latest_hash,
            })

    def _test_complete_if_ready(self):
        if (
            not self.end_received
            or self.test_complete_sent
            or self.inflight is not None
            or self.ready_to_start is not None
            or self.pending is not None
            or self.displayed_revision != self.latest_revision
        ):
            return
        if (
            self.displayed_revision != self.expected_final_revision
            or self.latest_hash != self.expected_final_hash
        ):
            raise AckSchedulerError("final revision/hash mismatch")
        self._status(TEST_COMPLETE, self.displayed_revision, {
            "displayed_revision": self.displayed_revision,
            "viewport_hash": self.latest_hash,
            "accepted_count": self.accepted_count,
            "rendered_count": self.rendered_count,
            "superseded_count": self.superseded_count,
            "refresh_count": self.refresh_count,
            "error_count": self.error_count,
        })
        self.test_complete_sent = True

    def service(self, chunks=()):
        self.feed_chunks(chunks)
        for _ in range(self.frame_budget):
            frame = self.parser.pop()
            if frame is None:
                break
            self._accept_frame(frame)

        now = self.monotonic()
        completed = self._complete_if_idle(now)
        self._caught_up_if_ready()
        self._test_complete_if_ready()

        # REFRESH_STARTED must leave the bounded outbox before the physical
        # begin call. The caller drains statuses between service calls.
        if self.ready_to_start is not None and len(self.outbox) == 0:
            viewport, sequence, full = self.ready_to_start
            self.ready_to_start = None
            started = self.monotonic()
            actual_full = self.display.begin_refresh(
                self.render(viewport), full=full
            )
            self.inflight = (viewport, sequence, started, actual_full)
            self.rendered_count += 1
            return

        if (
            not completed
            and self.inflight is None
            and self.ready_to_start is None
            and self.pending is not None
            and len(self.outbox) == 0
        ):
            viewport, sequence = self.pending
            self.pending = None
            full = self.rendered_count == 0
            self.ready_to_start = (viewport, sequence, full)
            self._status(REFRESH_STARTED, viewport.revision, {
                "viewport_sequence": sequence,
                "refresh_mode": FULL_REFRESH if full else PARTIAL_REFRESH,
                "latest_received_revision": self.latest_revision,
                "previous_displayed_revision": self.displayed_revision,
            })
