"""Bounded acknowledgement lifecycle and timeout state machine."""

from magwrite_transport.protocol import (
    BUTTON_EVENT, DISPLAY_CAUGHT_UP, DISPLAY_ERROR, FRAME_ACCEPTED,
    FRAME_REJECTED, REFRESH_COMPLETED, REFRESH_STARTED, STATUS_HELLO,
    TEST_COMPLETE, VERSION,
)
from magwrite_transport.status_message import decode_status

MAX_TRACKED_REVISIONS = 16
STATUS_HELLO_TIMEOUT = 5.0
FRAME_ACCEPTED_TIMEOUT = 3.0
REFRESH_STARTED_TIMEOUT = 8.0
REFRESH_COMPLETED_TIMEOUT = 15.0
DISPLAY_CAUGHT_UP_TIMEOUT = 18.0


class AckError(Exception):
    pass


class AckTimeout(AckError):
    def __init__(self, category):
        super().__init__(category + " timeout")
        self.category = category


class AckTrackerOverflow(AckError):
    pass


class RevisionState:
    def __init__(self, revision, sequence, viewport_hash, now):
        self.revision = revision
        self.sequence = sequence
        self.viewport_hash = viewport_hash
        self.sent_at = now
        self.accepted = False
        self.refresh_started = False
        self.refresh_completed = False
        self.displayed = False
        self.rejected = False
        self.failed = False
        self.superseded = False
        self.accepted_at = None
        self.started_at = None
        self.completed_at = None


class AckTracker:
    def __init__(
        self, capacity=MAX_TRACKED_REVISIONS, start_time=0.0,
        hello_timeout=STATUS_HELLO_TIMEOUT,
        accepted_timeout=FRAME_ACCEPTED_TIMEOUT,
        started_timeout=REFRESH_STARTED_TIMEOUT,
        completed_timeout=REFRESH_COMPLETED_TIMEOUT,
        caught_up_timeout=DISPLAY_CAUGHT_UP_TIMEOUT,
        allow_intermediate_catch_up=False,
    ):
        # The proven lock-step acknowledgement harness sends one viewport at a
        # time, so any catch-up below the latest transmitted revision is an
        # error. An editor keeps typing while the panel is busy, so it may
        # legitimately transmit a newer revision before an older catch-up
        # arrives. That is only permitted when explicitly opted in, and a
        # catch-up may still never claim a revision that was never sent, nor
        # mark any other revision displayed.
        self.allow_intermediate_catch_up = allow_intermediate_catch_up
        self.intermediate_catch_ups = 0
        self.capacity = capacity
        self.states = []
        self.started_at = start_time
        self.hello = False
        self.last_status_sequence = None
        self.status_duplicates = 0
        self.status_stale = 0
        self.status_sequence_gaps = 0
        self.errors = 0
        self.button_events = 0
        self.final_complete = False
        self.final_displayed_revision = 0
        self.final_hash = 0
        self.hello_timeout = hello_timeout
        self.accepted_timeout = accepted_timeout
        self.started_timeout = started_timeout
        self.completed_timeout = completed_timeout
        self.caught_up_timeout = caught_up_timeout

    def sent(self, revision, sequence, viewport_hash, now):
        if self.find(revision) is not None:
            raise AckError("duplicate sent revision")
        if len(self.states) >= self.capacity:
            removable = next(
                (state for state in self.states
                 if state.displayed or state.superseded),
                None,
            )
            if removable is None:
                raise AckTrackerOverflow("ack tracker capacity exceeded")
            self.states.remove(removable)
        state = RevisionState(revision, sequence, viewport_hash, now)
        self.states.append(state)
        return state

    def find(self, revision):
        for state in self.states:
            if state.revision == revision:
                return state
        return None

    @property
    def latest_sent_revision(self):
        return self.states[-1].revision if self.states else 0

    def _sequence_accept(self, sequence):
        if self.last_status_sequence is not None:
            if sequence == self.last_status_sequence:
                self.status_duplicates += 1
                return False
            if sequence < self.last_status_sequence:
                self.status_stale += 1
                return False
            if sequence != self.last_status_sequence + 1:
                self.status_sequence_gaps += 1
        self.last_status_sequence = sequence
        return True

    def apply(self, frame, now):
        if not self._sequence_accept(frame.sequence):
            return None
        fields = decode_status(frame.message_type, frame.payload)
        revision = frame.revision
        if frame.message_type == BUTTON_EVENT:
            # V1.5. Handled first and returned immediately: a button says nothing
            # about any viewport, so it must not be looked up against a revision
            # and must never mark one accepted, started, or displayed. It shares
            # this channel's sequence numbering -- which is what gives it
            # duplicate and gap detection for free -- and nothing else.
            self.button_events += 1
            return fields
        if frame.message_type == STATUS_HELLO:
            if fields["protocol_version"] != VERSION:
                raise AckError("status hello protocol mismatch")
            if not fields["receiver_ready"] or not fields["display_ready"]:
                raise AckError("status hello not ready")
            self.hello = True
            return fields
        if frame.message_type in (FRAME_REJECTED, DISPLAY_ERROR):
            self.errors += 1
            state = self.find(revision)
            if state:
                state.rejected = frame.message_type == FRAME_REJECTED
                state.failed = True
            raise AckError(fields["reason"])
        if frame.message_type == TEST_COMPLETE:
            if fields["displayed_revision"] != self.latest_sent_revision:
                raise AckError("test complete revision mismatch")
            state = self.find(fields["displayed_revision"])
            if state is None or fields["viewport_hash"] != state.viewport_hash:
                raise AckError("test complete hash mismatch")
            self.final_complete = True
            self.final_displayed_revision = fields["displayed_revision"]
            self.final_hash = fields["viewport_hash"]
            return fields
        state = self.find(revision)
        if state is None:
            raise AckError("status for unknown revision")
        if frame.message_type == FRAME_ACCEPTED:
            if fields["received_sequence"] != state.sequence:
                raise AckError("accepted sequence mismatch")
            state.accepted = True
            state.accepted_at = now
            if fields["superseded"]:
                candidates = [
                    item for item in self.states
                    if item.revision < revision
                    and item.accepted
                    and not item.refresh_started
                    and not item.displayed
                ]
                if candidates:
                    candidates[-1].superseded = True
        elif frame.message_type == REFRESH_STARTED:
            if not state.accepted:
                raise AckError("refresh started before acceptance")
            state.refresh_started = True
            state.started_at = now
        elif frame.message_type == REFRESH_COMPLETED:
            if not state.refresh_started:
                raise AckError("refresh completed before start")
            state.refresh_completed = True
            state.completed_at = now
        elif frame.message_type == DISPLAY_CAUGHT_UP:
            displayed = fields["displayed_revision"]
            latest = fields["latest_received_revision"]
            if displayed > self.latest_sent_revision:
                raise AckError("displayed revision exceeds transmitted revision")
            if displayed != latest:
                raise AckError("stale or impossible caught-up revision")
            if displayed != self.latest_sent_revision:
                if not self.allow_intermediate_catch_up:
                    raise AckError("stale or impossible caught-up revision")
                self.intermediate_catch_ups += 1
            if fields["viewport_hash"] != state.viewport_hash:
                raise AckError("caught-up hash mismatch")
            if not state.refresh_completed:
                raise AckError("caught up before refresh completion")
            state.displayed = True
            self.final_displayed_revision = displayed
            self.final_hash = fields["viewport_hash"]
        else:
            raise AckError("unexpected status type")
        return fields

    def check_timeouts(self, now):
        if not self.hello and now - self.started_at > self.hello_timeout:
            raise AckTimeout("status_hello")
        for state in self.states:
            if not state.accepted and now - state.sent_at > self.accepted_timeout:
                raise AckTimeout("frame_accepted")
            if state.accepted and not state.refresh_started and not state.superseded and (
                now - state.accepted_at > self.started_timeout
            ):
                raise AckTimeout("refresh_started")
            if state.refresh_started and not state.refresh_completed and (
                now - state.started_at > self.completed_timeout
            ):
                raise AckTimeout("refresh_completed")
        if self.states:
            latest = self.states[-1]
            if latest.refresh_completed and not latest.displayed and (
                now - latest.completed_at > self.caught_up_timeout
            ):
                raise AckTimeout("display_caught_up")
