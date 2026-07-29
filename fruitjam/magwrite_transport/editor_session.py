"""Host-safe orchestration of the authoritative Fruit Jam editor session.

This module contains no hardware imports. The armed hardware entry point owns
UART bytes only; every scheduling, editing, viewport, and acknowledgement
decision lives here so the identical logic runs under CPython host tests.

Loop order is input-first and is never inverted: due local input events are
drained and applied to the authoritative editor before any viewport is built or
serialized, so display timing can never block or reorder an edit.
"""

from magwrite_transport.ack_tracker import AckTracker
from magwrite_transport.editor import (
    BoundedEventQueue, EditRejected, MultilineEditor, QueueOverflow,
    SequenceTracker,
)
from magwrite_transport.editor_scenarios import (
    MAX_EDITOR_INPUT_FRAMES, MAX_EDITOR_VIEWPORT_FRAMES, ScheduledEventProducer,
    numbered_scenarios,
)
from magwrite_transport.editor_viewport import EditorViewport
from magwrite_transport.protocol import (
    END_OF_TEST, HELLO, VIEWPORT, FrameParser, crc32, encode_frame,
)

HELLO_PAYLOAD = b"FRUITJAM-EDITOR/1"
SEND_WINDOW = 3
EVENT_QUEUE_CAPACITY = 64
INPUT_DRAIN_BUDGET = 16
STATUS_FRAME_BUDGET = 16
# One state per transmitted viewport is retained for the whole run so a
# refresh-completed revision can never be evicted before its catch-up arrives.
# The scenario budgets cap transmissions far below this bound.
ACK_TRACKER_CAPACITY = 96

PHASE_HELLO = "HELLO"
PHASE_SCENARIO = "SCENARIO"
PHASE_DRAIN = "DRAIN"
PHASE_END = "END"
PHASE_DONE = "DONE"


class EditorSessionError(Exception):
    """A stop condition fired; the physical test never retries automatically."""


class EditorSession:
    def __init__(
        self, monotonic, log, timeout_seconds=240.0,
        queue_capacity=EVENT_QUEUE_CAPACITY,
        tracker_capacity=ACK_TRACKER_CAPACITY,
        send_window=SEND_WINDOW, viewport=None, tracker=None, editor=None,
    ):
        self.monotonic = monotonic
        self.log = log
        self.timeout_seconds = timeout_seconds
        self.send_window = send_window
        self.viewport = viewport or EditorViewport()
        self.editor = editor or MultilineEditor(layout=self.viewport.layout)
        self.queue = BoundedEventQueue(queue_capacity)
        self.sequence_tracker = SequenceTracker()
        self.parser = FrameParser()
        self.tracker = tracker or AckTracker(
            tracker_capacity, monotonic(), allow_intermediate_catch_up=True
        )
        self.scenarios = numbered_scenarios()
        self.scenario_index = 0
        self.producer = None
        self.scenario_started = None
        self.phase = PHASE_HELLO
        self.outbound = []
        self.frame_sequence = 0
        self.viewport_frames_sent = 0
        self.scenario_frames_sent = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.events_processed = 0
        self.events_rejected = 0
        self.queue_overflows = 0
        self.last_sent_payload = None
        self.last_sent_revision = 0
        self.last_sent_hash = 0
        self.last_send_at = None
        self.built_revision = None
        self.viewports_built = 0
        self.viewports_superseded_locally = 0
        self.final_texts = {}
        self.status_counts = {}
        self.started_at = monotonic()
        self.stop_reason = None

    # ---------------------------------------------------------------- helpers

    @property
    def scenario(self):
        return self.scenarios[self.scenario_index]

    @property
    def complete(self):
        return self.phase == PHASE_DONE

    def take_outbound(self):
        frames = self.outbound
        self.outbound = []
        return frames

    def feed(self, chunk):
        if chunk:
            self.bytes_received += len(chunk)
            self.parser.feed(chunk)

    def _emit(self, message_type, revision, payload):
        self.frame_sequence += 1
        if self.frame_sequence > MAX_EDITOR_INPUT_FRAMES:
            raise EditorSessionError("input frame limit exceeded")
        frame = encode_frame(message_type, self.frame_sequence, revision, payload)
        self.outbound.append(frame)
        self.bytes_sent += len(frame)
        return frame

    def _outstanding(self):
        """Transmitted viewports the panel has not finished refreshing.

        A revision whose refresh has completed no longer occupies the send
        window even though it is not yet confirmed caught up, because
        REFRESH_COMPLETED does not mean displayed and the MagTag only reports
        catch-up once it is fully quiescent.
        """
        return sum(
            1 for state in self.tracker.states
            if not (
                state.refresh_completed or state.displayed
                or state.superseded or state.failed
            )
        )

    # ------------------------------------------------------------ input stage

    def _drain_input(self, now):
        """Stage 1 and 2: produce due events, then apply them to the editor."""
        if self.producer is not None:
            now_ms = (now - self.scenario_started) * 1000.0
            try:
                self.producer.produce_due(now_ms, self.queue, INPUT_DRAIN_BUDGET)
            except QueueOverflow:
                self.queue_overflows += 1
                raise EditorSessionError("editor event queue overflow")
        applied = 0
        while applied < INPUT_DRAIN_BUDGET:
            event = self.queue.get()
            if event is None:
                break
            self.sequence_tracker.accept(event)
            before_document = self.editor.document_revision
            try:
                self.editor.apply(event)
            except EditRejected as error:
                self.events_rejected += 1
                self.log({
                    "event": "editor_event_rejected", "scenario": event.scenario,
                    "sequence": event.sequence, "kind": event.kind,
                    "value": event.value, "reason": str(error),
                })
                raise EditorSessionError("unexpected rejected edit: " + str(error))
            self.events_processed += 1
            applied += 1
            self.log({
                "event": "editor_event_processed", "scenario": event.scenario,
                "sequence": event.sequence, "kind": event.kind,
                "value": event.value,
                "cursor_row": self.editor.row, "cursor_column": self.editor.column,
                "document_revision": self.editor.document_revision,
                "viewport_revision": self.editor.viewport_revision,
                "queue_depth": len(self.queue),
            })
            if self.editor.document_revision != before_document:
                self.log({
                    "event": "editor_document_revision_changed",
                    "scenario": event.scenario,
                    "document_revision": self.editor.document_revision,
                    "lines": len(self.editor.lines),
                    "characters": self.editor.character_count(),
                })
        return applied

    # ----------------------------------------------------------- status stage

    def _drain_status(self, now):
        """Stages 4 to 6: parse bounded status frames and update ack state."""
        for _ in range(STATUS_FRAME_BUDGET):
            frame = self.parser.pop()
            if frame is None:
                break
            fields = self.tracker.apply(frame, now)
            self.status_counts[frame.message_type] = (
                self.status_counts.get(frame.message_type, 0) + 1
            )
            self.log({
                "event": "editor_status_received",
                "message_type": frame.message_type, "sequence": frame.sequence,
                "revision": frame.revision, "fields": fields,
            })
            state = self.tracker.find(frame.revision)
            if state is not None:
                self.log({
                    "event": "editor_viewport_ack_state",
                    "revision": state.revision, "accepted": state.accepted,
                    "refresh_started": state.refresh_started,
                    "refresh_completed": state.refresh_completed,
                    "displayed": state.displayed,
                    "superseded": state.superseded,
                })
        if (
            self.parser.crc_failures
            or self.parser.version_failures
            or self.parser.type_failures
            or self.parser.oversized
            or self.parser.buffer_overflows
        ):
            raise EditorSessionError("fatal status parser integrity failure")

    # --------------------------------------------------------- viewport stage

    def _build_viewport(self):
        """Stage 7: build only the newest required viewport."""
        scenario_id = self.scenario[1]
        revision = self.editor.viewport_revision
        if revision == 0:
            return None
        return revision, self.viewport.payload(self.editor, scenario_id)

    def _maybe_send_viewport(self, now, force=False):
        """Stage 8: transmit at most one newest viewport per iteration.

        Only the newest viewport state is ever a candidate. When editing has
        moved on before a built state could be transmitted, that older state is
        counted as locally superseded and is never sent, which is what keeps the
        viewport count far below the input event count.
        """
        built = self._build_viewport()
        if built is None:
            return False
        revision, payload = built
        if payload == self.last_sent_payload:
            self.built_revision = None
            return False
        if self.built_revision is None:
            self.viewports_built += 1
        elif self.built_revision != revision:
            self.viewports_superseded_locally += 1
            self.viewports_built += 1
            self.log({
                "event": "editor_viewport_superseded",
                "superseded_revision": self.built_revision,
                "newest_revision": revision,
            })
        self.built_revision = revision
        if self._outstanding() >= self.send_window:
            return False
        if not force:
            _, _, _, min_send, max_frames, _, _ = self.scenario
            if self.last_send_at is not None and now - self.last_send_at < min_send:
                return False
            if self.scenario_frames_sent >= max_frames:
                return False
        if self.viewport_frames_sent >= MAX_EDITOR_VIEWPORT_FRAMES:
            raise EditorSessionError("viewport frame limit exceeded")
        self._emit(VIEWPORT, revision, payload)
        digest = crc32(payload)
        self.tracker.sent(revision, self.frame_sequence, digest, now)
        self.viewport_frames_sent += 1
        self.scenario_frames_sent += 1
        self.last_sent_payload = payload
        self.last_sent_revision = revision
        self.last_sent_hash = digest
        self.last_send_at = now
        self.built_revision = None
        self.log({
            "event": "editor_viewport_sent", "scenario": self.scenario[0],
            "sequence": self.frame_sequence, "revision": revision,
            "document_revision": self.editor.document_revision,
            "text_hash": "%08X" % digest,
            "outstanding": self._outstanding(),
        })
        return True

    def _final_viewport_displayed(self):
        if self.last_sent_payload is None:
            return False
        built = self._build_viewport()
        if built is not None and built[1] != self.last_sent_payload:
            return False
        state = self.tracker.find(self.last_sent_revision)
        return state is not None and state.displayed

    # ------------------------------------------------------------- main cycle

    def _start_scenario(self, now):
        name, scenario_id, wpm, _, _, events, _ = self.scenario
        self.producer = ScheduledEventProducer(events, wpm)
        self.scenario_started = now
        self.scenario_frames_sent = 0
        self.phase = PHASE_SCENARIO
        self.log({
            "event": "editor_scenario_started", "scenario": name,
            "scenario_id": scenario_id, "wpm": wpm, "events": len(events),
        })

    def service(self):
        """One cooperative iteration of the input-first scheduler."""
        now = self.monotonic()
        if self.phase == PHASE_DONE:
            return

        # Stages 1 to 3: input always drains and applies before any viewport.
        if self.phase == PHASE_SCENARIO:
            self._drain_input(now)

        # Stages 4 to 6: bounded status parsing and acknowledgement updates.
        self._drain_status(now)

        # Stages 7 and 8: build and conditionally transmit the newest viewport.
        if self.phase == PHASE_HELLO:
            if self.frame_sequence == 0:
                self._emit(HELLO, 0, HELLO_PAYLOAD)
            elif self.tracker.hello:
                self._start_scenario(now)
        elif self.phase == PHASE_SCENARIO:
            self._maybe_send_viewport(now)
            if self.producer.complete and not len(self.queue):
                self.phase = PHASE_DRAIN
        elif self.phase == PHASE_DRAIN:
            self._maybe_send_viewport(now, force=True)
            if self._final_viewport_displayed():
                self._finish_scenario(now)
        elif self.phase == PHASE_END:
            if self.tracker.final_complete:
                self.phase = PHASE_DONE
                self.log({"event": "editor_test_complete",
                          "displayed_revision": self.tracker.final_displayed_revision,
                          "final_hash": "%08X" % self.tracker.final_hash})

        # Stage 9: timeouts and stop conditions.
        self.tracker.check_timeouts(now)
        if now - self.started_at > self.timeout_seconds:
            raise EditorSessionError("editor test timeout")

    def _finish_scenario(self, now):
        name, scenario_id, _, _, _, _, expected = self.scenario
        self.final_texts[name] = self.editor.text
        if self.editor.text != expected:
            raise EditorSessionError(
                "scenario %s final text mismatch" % name
            )
        self.log({
            "event": "editor_scenario_complete", "scenario": name,
            "scenario_id": scenario_id, "text": self.editor.text,
            "document_revision": self.editor.document_revision,
            "viewport_revision": self.editor.viewport_revision,
            "displayed_revision": self.tracker.final_displayed_revision,
        })
        self.producer = None
        if self.scenario_index + 1 < len(self.scenarios):
            self.scenario_index += 1
            self.editor.reset_document()
            self._start_scenario(now)
            return
        self._emit(END_OF_TEST, self.last_sent_revision, (
            "%d;%d;%08X" % (
                self.last_sent_revision, self.viewport_frames_sent,
                self.last_sent_hash,
            )
        ).encode("ascii"))
        self.phase = PHASE_END

    # ---------------------------------------------------------------- summary

    def summary(self, result):
        return {
            "event": "editor_physical_test_summary",
            "result": result,
            "stop_reason": self.stop_reason,
            "events_generated": self.sequence_tracker.expected,
            "events_processed": self.events_processed,
            "events_rejected": self.events_rejected,
            "queue_overflows": self.queue_overflows,
            "maximum_queue_depth": self.queue.maximum_depth,
            "document_revision": self.editor.document_revision,
            "final_viewport_revision": self.editor.viewport_revision,
            "final_document_lines": len(self.editor.lines),
            "final_document_characters": self.editor.character_count(),
            "final_cursor_row": self.editor.row,
            "final_cursor_column": self.editor.column,
            "viewports_built": self.viewports_built,
            "viewports_superseded_locally": self.viewports_superseded_locally,
            "viewport_frames_sent": self.viewport_frames_sent,
            "viewport_frames_accepted": sum(
                1 for state in self.tracker.states if state.accepted
            ),
            "frame_accepted_received": self.status_counts.get(6, 0),
            "refresh_started_received": self.status_counts.get(7, 0),
            "refresh_completed_received": self.status_counts.get(8, 0),
            "display_caught_up_received": self.status_counts.get(9, 0),
            "intermediate_catch_ups": self.tracker.intermediate_catch_ups,
            "final_transmitted_revision": self.tracker.latest_sent_revision,
            "final_displayed_revision": self.tracker.final_displayed_revision,
            "final_hash": "%08X" % self.tracker.final_hash,
            "test_complete": self.tracker.final_complete,
            "scenario_final_texts": self.final_texts,
            "input_frames_sent": self.frame_sequence,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "status_sequence_gaps": self.tracker.status_sequence_gaps,
            "status_duplicates": self.tracker.status_duplicates,
            "status_stale": self.tracker.status_stale,
            "discarded_prefix_bytes": self.parser.bytes_discarded_before_magic,
            "resynchronization_events": self.parser.resynchronization_events,
            "maximum_discarded_prefix": self.parser.maximum_discarded_prefix,
            "status_frames_rejected": self.parser.rejected,
            "crc_failures": self.parser.crc_failures,
            "timeouts": (
                1 if self.stop_reason and "timeout" in self.stop_reason else 0
            ),
        }
