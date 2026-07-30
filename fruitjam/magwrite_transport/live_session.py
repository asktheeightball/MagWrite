"""Live typing session: the same scheduler, driven by a real keyboard.

Host-safe, and deliberately a sibling of ``editor_session.py`` rather than a
change to it. The proven scenario-driven session keeps working untouched; this
module swaps *only* the input source, from a scripted producer to the USB HID
adapter, and drops the scripted expected-text reconciliation that a live run
cannot have.

Everything downstream is the already-verified code, unchanged: ``MultilineEditor``
for the authoritative document, ``Layout``/``EditorViewport`` for wrapping and
windowing, ``protocol``/``AckTracker`` for transport and acknowledgements.

The loop order is input-first and is never inverted:

    1. poll the USB host adapter within a bounded report budget
    2. normalize new keyboard events into the bounded queue
    3. drain queued events, routing each to the shell or the editor
    4. drain bounded MagTag status frames and update acknowledgement state
    5. run autosave, checkpoint, and manual save work when due
    6. apply the shell's own control gesture and adopt the resulting screen
    7. build only the newest required viewport, coalescing stale states
    8. transmit at most one newest pending viewport
    9. check timeouts and stop conditions

Neither half blocks the other: the USB read timeout is milliseconds, and a
display refresh in flight never suspends polling.

The optional shell
------------------

``shell`` is optional on the same terms ``persistence`` is, and for the same
reason: with it absent every stage behaves exactly as it did for the runs that
produced the existing physical evidence, so those payloads and CRC-32s stay
reproducible. With it present three things change, and nothing else does:

* input is *routed* rather than assumed to belong to the editor;
* the shell may put its own screen on the panel, through the same encoder,
  revision, pacing, and acknowledgement path the document uses;
* the finish gesture means **back**, and only the shell reaching its terminal
  state ends the session.

There is still exactly one editor for the life of the session. The shell never
constructs, clears, or reloads it, which is why no transition can lose unsaved
work: nothing is closed.
"""

from magwrite_transport.ack_tracker import AckTracker
from magwrite_transport.editor import (
    BoundedEventQueue, EditRejected, MultilineEditor, QueueOverflow,
    SequenceTracker,
)
from magwrite_transport.editor_viewport import EditorViewport
from magwrite_transport.latency import LatencyRecorder
from magwrite_transport.pacing import (
    CAUGHT_UP_MIN_SEND_SECONDS, COALESCE_SECONDS, MAX_VISIBLE_LAG_SECONDS,
    QUIET_SECONDS, REASON_CAUGHT_UP, SEND_WINDOW, SENDING_REASONS,
    SUSTAINED_MIN_SEND_SECONDS, DisplayPacer,
)
from magwrite_transport.protocol import (
    END_OF_TEST, HELLO, VIEWPORT, FrameParser, crc32, encode_frame,
)
from magwrite_transport.shell import (
    REQUEST_JOURNAL, REQUEST_OPEN, REQUEST_QUICK_NOTE, REQUEST_RECENT,
    ROUTE_EDITOR, STATE_DRAFTS, STATE_EDITOR, STATE_SAVE_STATUS,
)
from magwrite_transport.shell_viewport import payload as shell_payload
from magwrite_transport.usb_keyboard_adapter import (
    MAX_KEYBOARD_EVENTS, UsbKeyboardAdapterError,
)

HELLO_PAYLOAD = b"FRUITJAM-USBKBD/1"
LIVE_SCENARIO_ID = 6

# Authorised physical ceilings for this phase. The event ceiling is owned by the
# adapter that enforces it and re-exported here so there is one source of truth.
# The MagTag entry point declares matching ceilings and a host test asserts the
# two sets agree.
MAX_VIEWPORT_FRAMES = 100
MAX_PROTOCOL_FRAMES = 200
MAX_PARTIAL_REFRESHES = 50

EVENT_QUEUE_CAPACITY = 64
ACK_TRACKER_CAPACITY = 128
INPUT_DRAIN_BUDGET = 16
STATUS_FRAME_BUDGET = 16

# Display pacing lives in one place, ``pacing``, so a physical run can never
# have two disagreeing send intervals. Re-exported here because this is where a
# reader of the scheduler looks for them.
#
# The 100-frame viewport ceiling is not the binding one. Almost every accepted
# frame is rendered, so 100 frames would demand ~99 partial refreshes against a
# ceiling of 50, and ~400 status frames against a ceiling of 200 per direction.
# Fifty refreshes is therefore the real bound, and transmission stays paced to
# the panel rather than to the typing rate so a whole session fits inside it. A
# keypress never gets its own frame, and a pause costs at most one catch-up
# frame because a frame is only ever built when the viewport state changed.
# Operator-paced: a live run is only abandoned after a long silence, never on a
# fixed schedule, because a person pausing to read the panel is not a fault.
IDLE_TIMEOUT_SECONDS = 600.0
SESSION_TIMEOUT_SECONDS = 2700.0

PHASE_HELLO = "HELLO"
PHASE_LIVE = "LIVE"
PHASE_DRAIN = "DRAIN"
PHASE_END = "END"
PHASE_DONE = "DONE"


class LiveSessionError(Exception):
    """A stop condition fired; the physical test never retries automatically."""


class LiveTypingSession:
    def __init__(
        self, monotonic, log, adapter=None, adapter_factory=None,
        queue_capacity=EVENT_QUEUE_CAPACITY,
        tracker_capacity=ACK_TRACKER_CAPACITY, send_window=SEND_WINDOW,
        idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
        session_timeout_seconds=SESSION_TIMEOUT_SECONDS,
        viewport=None, tracker=None, editor=None, pacer=None, latency=None,
        max_viewport_frames=MAX_VIEWPORT_FRAMES,
        max_protocol_frames=MAX_PROTOCOL_FRAMES, persistence=None, shell=None,
        library=None,
    ):
        self.monotonic = monotonic
        self.log = log
        self.viewport = viewport or EditorViewport()
        self.editor = editor or MultilineEditor(layout=self.viewport.layout)
        self.queue = BoundedEventQueue(queue_capacity)
        self.sequence_tracker = SequenceTracker()
        self.parser = FrameParser()
        self.tracker = tracker or AckTracker(
            tracker_capacity, monotonic(), allow_intermediate_catch_up=True
        )
        self.adapter = adapter if adapter is not None else adapter_factory(self.queue)
        self.send_window = send_window
        # The authorised physical ceilings, as parameters rather than constants,
        # so a repeatable development session is not stopped by a budget that
        # exists to bound a one-shot certification run. The defaults are the
        # module constants, so every guarded harness keeps the exact behaviour it
        # was verified with; a host test asserts that.
        self.max_viewport_frames = max_viewport_frames
        self.max_protocol_frames = max_protocol_frames
        self.pacer = pacer or DisplayPacer()
        # Passive measurement only. It observes and never decides.
        self.latency = latency if latency is not None else LatencyRecorder()
        # Optional, and ``None`` is a first-class value: every guarded harness
        # that produced the existing physical evidence runs without it, and with
        # it absent no save indicator is drawn, so the viewport payloads and
        # CRC-32s those runs measured stay exactly reproducible.
        self.persistence = persistence
        self.save_indicator = None if persistence is None else persistence.indicator
        self.save_requests_serviced = 0
        self.manual_saves = 0
        # Optional on exactly the same terms as persistence, and for the same
        # reason: with it absent every stage below behaves as it did for the runs
        # that produced the existing physical evidence, so those payloads and
        # CRC-32s stay reproducible. With it present the finish gesture means
        # *back*, the shell decides which screen is on the panel, and input is
        # routed rather than assumed to belong to the editor.
        self.shell = shell
        # Optional on the same terms again. With it absent the shell's four items
        # all route into the one document exactly as they did in V1.3, which is
        # what a card-less or persistence-disabled build gets, and what keeps the
        # V1.3 evidence reproducible.
        self.library = library
        self.documents_opened = 0
        self.document_switches = 0
        self.document_open_failures = 0
        self.finish_requests_serviced = 0
        self.shell_visible_revision = None if shell is None else shell.visible_revision
        self.shell_state_seen = None if shell is None else shell.state
        if shell is not None:
            # The shell has a screen from the moment it exists, and the send path
            # treats viewport revision 0 as "nothing has ever been visible" and
            # declines to build a frame for it. Without this the opening menu
            # would never be drawn.
            self.editor.note_visible_change()
        self.idle_timeout_seconds = idle_timeout_seconds
        self.session_timeout_seconds = session_timeout_seconds
        self.phase = PHASE_HELLO
        self.outbound = []
        self.frame_sequence = 0
        self.viewport_frames_sent = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.events_processed = 0
        self.events_rejected = 0
        self.shell_events = 0
        self.queue_overflows = 0
        self.last_sent_payload = None
        self.last_sent_revision = 0
        self.last_sent_hash = 0
        self.last_send_at = None
        self.built_revision = None
        self.viewports_built = 0
        self.viewports_superseded_locally = 0
        self.status_counts = {}
        self.started_at = monotonic()
        self.last_activity_at = self.started_at
        self.stop_reason = None

    # ---------------------------------------------------------------- helpers

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
        if self.frame_sequence > self.max_protocol_frames:
            raise LiveSessionError("input frame limit exceeded")
        frame = encode_frame(message_type, self.frame_sequence, revision, payload)
        self.outbound.append(frame)
        self.bytes_sent += len(frame)
        return frame

    def _outstanding(self):
        """Transmitted viewports the panel has not finished refreshing."""
        return sum(
            1 for state in self.tracker.states
            if not (
                state.refresh_completed or state.displayed
                or state.superseded or state.failed
            )
        )

    # ------------------------------------------------------------ input stage

    def _poll_keyboard(self, now):
        """Stages 1 and 2: bounded USB polling into the bounded input queue."""
        try:
            produced = self.adapter.poll(now)
        except UsbKeyboardAdapterError as error:
            raise LiveSessionError("usb keyboard: " + str(error))
        except QueueOverflow:
            self.queue_overflows += 1
            raise LiveSessionError("keyboard input queue overflow")
        if produced:
            self.last_activity_at = now
        return produced

    def _drain_input(self, now):
        """Stage 3: route queued events, applying editor ones to the editor."""
        applied = 0
        while applied < INPUT_DRAIN_BUDGET:
            event = self.queue.get()
            if event is None:
                break
            self.sequence_tracker.accept(event)
            applied += 1
            self.last_activity_at = now
            if self.shell is not None and self.shell.route(event) != ROUTE_EDITOR:
                # The shell consumed it. Nothing reaches the document, so a
                # keystroke aimed at a menu can never appear in the draft, and
                # pacing is deliberately not told the writer is typing: menu
                # navigation should redraw as promptly as a pause does.
                self.shell_events += 1
                continue
            before_document = self.editor.document_revision
            try:
                self.editor.apply(event)
            except EditRejected as error:
                self.events_rejected += 1
                self.log({
                    "event": "live_event_rejected", "sequence": event.sequence,
                    "kind": event.kind, "value": event.value,
                    "reason": str(error),
                })
                if self.shell is None:
                    raise LiveSessionError("unexpected rejected edit: " + str(error))
                # Requirement 11, and a real improvement rather than a formality:
                # reaching the document bound used to end the session outright.
                # The refused edit changed nothing, so the document is intact --
                # it is shown on a recoverable screen and the writer goes back to
                # it. Fail closed, keep the work.
                self.shell.fault(str(error))
                continue
            self.events_processed += 1
            # Pacing needs to know the writer is still typing, so it can tell a
            # sustained burst from a pause it should catch up after. The same
            # fact is handed to the passive latency recorder, which additionally
            # wants to know whether this keystroke *ended* a pause.
            was_quiet = self.pacer.quiet(now)
            self.pacer.note_input(now)
            self.latency.note_input(now, quiet_before=was_quiet)
            if self.persistence is not None:
                # Autosave wants the same fact for the opposite reason: pacing
                # uses a pause to decide it may send sooner, persistence uses it
                # to decide it should write now, while the writer has stopped.
                self.persistence.note_input(now)
            self.log({
                "event": "live_event_processed", "sequence": event.sequence,
                "kind": event.kind, "value": event.value,
                "cursor_row": self.editor.row, "cursor_column": self.editor.column,
                "document_revision": self.editor.document_revision,
                "viewport_revision": self.editor.viewport_revision,
                "queue_depth": len(self.queue),
            })
            if self.editor.document_revision != before_document:
                self.log({
                    "event": "live_document_revision_changed",
                    "document_revision": self.editor.document_revision,
                    "lines": len(self.editor.lines),
                    "characters": self.editor.character_count(),
                })
        return applied

    # ----------------------------------------------------------- status stage

    def _drain_status(self, now):
        """Stage 4: bounded status parsing and acknowledgement updates."""
        for _ in range(STATUS_FRAME_BUDGET):
            frame = self.parser.pop()
            if frame is None:
                break
            fields = self.tracker.apply(frame, now)
            self.status_counts[frame.message_type] = (
                self.status_counts.get(frame.message_type, 0) + 1
            )
            self.latency.note_status(now, frame.message_type, frame.revision)
            self.log({
                "event": "live_status_received",
                "message_type": frame.message_type, "sequence": frame.sequence,
                "revision": frame.revision, "fields": fields,
            })
        if (
            self.parser.crc_failures
            or self.parser.version_failures
            or self.parser.type_failures
            or self.parser.oversized
            or self.parser.buffer_overflows
        ):
            raise LiveSessionError("fatal status parser integrity failure")

    # --------------------------------------------------------- viewport stage

    def _build_viewport(self):
        revision = self.editor.viewport_revision
        if revision == 0:
            return None
        if self.shell is not None:
            screen = shell_payload(self.shell, self.editor, self.save_indicator)
            if screen is not None:
                # A shell screen is a semantic viewport like any other: same
                # encoder, same bounds, same revision, same pacing. The editor
                # still owns the revision number, which is what stops two
                # different payloads from ever going out under one revision.
                return revision, screen
            return revision, self.viewport.payload(
                self.editor, LIVE_SCENARIO_ID, self.save_indicator,
                self.shell.panel_title(),
            )
        return revision, self.viewport.payload(
            self.editor, LIVE_SCENARIO_ID, self.save_indicator
        )

    def _maybe_send_viewport(self, now, force=False):
        """Stages 7 and 8: coalesce stale states, send at most one newest."""
        built = self._build_viewport()
        if built is None:
            return False
        revision, payload = built
        if payload == self.last_sent_payload:
            # The panel already shows this exact state; nothing is pending.
            self.built_revision = None
            self.pacer.clear_pending()
            return False
        self.pacer.note_pending(now)
        if self.built_revision is None:
            self.viewports_built += 1
        elif self.built_revision != revision:
            self.viewports_superseded_locally += 1
            self.viewports_built += 1
            self.log({
                "event": "live_viewport_superseded",
                "superseded_revision": self.built_revision,
                "newest_revision": revision,
            })
        self.built_revision = revision
        # The busy gate is absolute and applies to the forced final send too: a
        # refresh is never started while the MagTag is still working.
        busy = self._outstanding() >= self.send_window
        reason = self.pacer.decide(now, busy)
        if busy:
            return False
        if not force and reason not in SENDING_REASONS:
            return False
        if self.viewport_frames_sent >= self.max_viewport_frames:
            raise LiveSessionError("viewport frame limit exceeded")
        self._emit(VIEWPORT, revision, payload)
        digest = crc32(payload)
        self.tracker.sent(revision, self.frame_sequence, digest, now)
        self.viewport_frames_sent += 1
        self.last_sent_payload = payload
        self.last_sent_revision = revision
        self.last_sent_hash = digest
        self.last_send_at = now
        self.built_revision = None
        self.pacer.note_sent(now, None if force else reason)
        self.latency.note_sent(now, revision, None if force else reason)
        if reason == REASON_CAUGHT_UP and not force:
            self.latency.note_frame_after_pause()
        self.log({
            "event": "live_viewport_sent", "sequence": self.frame_sequence,
            "revision": revision,
            "document_revision": self.editor.document_revision,
            "text_hash": "%08X" % digest, "outstanding": self._outstanding(),
            "pacing_reason": "FORCED" if force else reason,
        })
        return True

    # ------------------------------------------------------ persistence stage

    def restore(self, snapshot, entry=None):
        """Load a recovered document into the authoritative editor.

        Called once, before the session starts, when the store returned a
        snapshot. The persistence controller then adopts the restored revision so
        the first thing a recovered session does is *not* to rewrite the state it
        was just recovered from.

        ``entry`` is the document's catalogue entry when there is a catalogue.
        It carries the identity, kind, and title back with the words, which is
        what makes a restored session restore its *mode* as well as its text --
        the gap V1.3 recorded and handed to this phase.
        """
        self.editor.load(
            snapshot.text, snapshot.row, snapshot.column, snapshot.revision
        )
        if self.persistence is not None:
            self.persistence.adopt(self.editor)
            self.save_indicator = self.persistence.indicator
        if self.shell is not None:
            # Requirement 10, and the whole of it: a recovered document means the
            # writer was writing, so the shell opens where their words are rather
            # than making them find their way back through a menu.
            self.shell.restore(
                True, snapshot.revision,
                None if entry is None else entry.document_id,
                None if entry is None else entry.kind,
                None if entry is None else entry.title,
            )
            self.shell_visible_revision = self.shell.visible_revision
            self.editor.note_visible_change()
        self.log({
            "event": "live_document_restored",
            "revision": snapshot.revision, "characters": len(snapshot.text),
            "lines": len(self.editor.lines), "cursor_row": self.editor.row,
            "cursor_column": self.editor.column,
            "document_id": None if entry is None else entry.document_id,
            "kind": None if entry is None else entry.kind,
            "title": None if entry is None else entry.title,
        })

    def _service_persistence(self, now):
        """Stage 5: autosave, checkpoint, and manual save work when due."""
        if self.persistence is None:
            return
        requests = getattr(self.adapter, "save_requests", 0)
        if requests > self.save_requests_serviced:
            # Collapsed rather than counted out one at a time: several Ctrl-S
            # presses in a row mean "save now", not "save four times", and one
            # checkpoint of the newest state satisfies all of them.
            self.save_requests_serviced = requests
            self.manual_saves += 1
            self.persistence.save_now(now, self.editor)
        else:
            self.persistence.service(now, self.editor)
        self._refresh_save_indicator()

    def _refresh_save_indicator(self):
        """Adopt the current save state as visible state."""
        if self.persistence is None:
            return
        if self.shell is not None:
            self.shell.note_save_state(self.persistence.state)
        indicator = self.persistence.indicator
        if indicator != self.save_indicator:
            self.save_indicator = indicator
            # The indicator is visible state, so the viewport revision has to
            # advance for it: without this the next payload would differ from the
            # last while carrying the same revision number, and the
            # acknowledgement tracker would be reconciling two different frames
            # against one revision.
            self.editor.note_visible_change()

    # ------------------------------------------------------------ shell stage

    def _service_shell(self, now):
        """Stage 6: the shell's own control gesture, and the redraw it implies.

        The finish gesture is the only control the shell takes from outside the
        normalized event stream, because it is the only one the keyboard layer
        reports as a control rather than an editor event.
        """
        if self.shell is None:
            return
        requests = getattr(self.adapter, "finish_requests", 0)
        if requests > self.finish_requests_serviced and not len(self.queue):
            # An empty queue is required for the same reason the pre-shell stop
            # required it: every keystroke pressed before the gesture is already
            # in the authoritative document, so leaving the editor can never
            # outrun the writing it is leaving.
            #
            # Collapsed rather than counted out, exactly as manual save is. A
            # burst of one gesture means one action, and on a panel that trails
            # by a second or more an accidental double press must not silently
            # skip a level.
            self.finish_requests_serviced = requests
            previous = self.shell.state
            self.shell.back()
            if previous == STATE_EDITOR and self.shell.state == STATE_SAVE_STATUS:
                # The point of the screen. Leaving the editor is the moment the
                # writer is most likely to walk away, so the document is made
                # durable on the way out rather than left to a threshold.
                if self.persistence is not None:
                    self.manual_saves += 1
                    self.persistence.save_now(now, self.editor)
                self.log({
                    "event": "shell_left_editor",
                    "document_id": self.shell.document_id,
                    "document_revision": self.editor.document_revision,
                    "characters": self.editor.character_count(),
                })
        # V1.4. Serviced here, in the same iteration the writer's keystroke was
        # routed and before any frame is built, so a mode never puts a stale
        # document on the panel for even one refresh.
        self._service_document_request(now)
        self._service_drafts_list()
        self._refresh_save_indicator()
        if self.shell.visible_revision != self.shell_visible_revision:
            self.shell_visible_revision = self.shell.visible_revision
            # The shell's screens are visible state the editor does not own, so
            # they advance the viewport revision through the same single door the
            # save indicator uses. The editor stays the only owner of both
            # revision numbers.
            self.editor.note_visible_change()

    # ---------------------------------------------------------- library stage

    def _service_document_request(self, now):
        """Perform the shell's pending open, if there is one. V1.4.

        The shell may not touch a card, so it asks; this is where the asking is
        answered. The order below is the safety argument and is not rearranged:

        1. **checkpoint the outgoing document first.** A switch is the only
           operation in the system that replaces the contents of the editor, so
           the words being replaced are made durable before anything is rebound.
           Nothing is closed -- there is still exactly one editor -- but something
           is handed over, and a handover with unsaved work in it is the failure
           the whole shell was built to make impossible;
        2. ask the library which document, and let it select it in the store;
        3. load it into the one editor, which validates it against the same
           bounds an interactive edit gets, because a card is not trusted input;
        4. only then tell the shell what it is now holding.

        Every failure between (2) and (4) becomes a recoverable error screen with
        the outgoing document already durable behind it.
        """
        if self.shell is None or self.library is None:
            return False
        taken = self.shell.take_request()
        if taken is None:
            return False
        request, argument = taken
        if self.persistence is not None and self.shell.document_id is not None:
            # Step 1. Unconditional: a threshold that has not been reached is not
            # a reason to hand a document over with work only in RAM.
            self.manual_saves += 1
            self.persistence.save_now(now, self.editor)
        if request == REQUEST_JOURNAL:
            opening = self.library.open_journal()
        elif request == REQUEST_QUICK_NOTE:
            opening = self.library.new_note()
        elif request == REQUEST_RECENT:
            opening = self.library.open_recent()
        elif request == REQUEST_OPEN:
            opening = self.library.open_document(argument)
        else:
            self.shell.fault("unknown document request: " + str(request))
            return False
        if opening is None:
            self.document_open_failures += 1
            self.shell.fault(
                self.library.last_error or "the document could not be opened"
            )
            return False
        return self._adopt_document(opening)

    def _adopt_document(self, opening):
        """Put an opened document into the one editor and tell the shell."""
        row, column = opening.cursor()
        try:
            self.editor.open_document(opening.text, row, column)
        except EditRejected as error:
            # The store is now pointed at a document the editor will not hold.
            # The words in RAM were checkpointed before any of this began, so the
            # writer loses nothing but the switch, and the error screen says why.
            self.document_open_failures += 1
            self.shell.fault(str(error))
            return False
        self.shell.opened(opening.document_id, opening.kind, opening.title)
        self.documents_opened += 1
        if not opening.created:
            self.document_switches += 1
        # The save state deliberately reads UNSAVED for the moment after a
        # switch, until the first autosave lands. What is on the card is durable,
        # but it is durable at the *stored* revision and this session's counter is
        # already past it. Erring toward "not yet saved" is the only direction
        # this indicator is ever allowed to be wrong in.
        self.log({
            "event": "live_document_opened",
            "document_id": opening.document_id, "kind": opening.kind,
            "title": opening.title, "created": opening.created,
            "characters": len(opening.text), "lines": len(self.editor.lines),
            "cursor_row": self.editor.row, "cursor_column": self.editor.column,
            "document_revision": self.editor.document_revision,
        })
        return True

    def _service_drafts_list(self):
        """Hand the shell the catalogue when it opens the Drafts list.

        On entry to the list only. The catalogue is re-read from RAM rather than
        from the card, and sorting it on every loop iteration would be work done
        thousands of times to answer a question asked once.
        """
        if self.shell is None or self.library is None:
            return False
        state = self.shell.state
        if state != STATE_DRAFTS or self.shell_state_seen == STATE_DRAFTS:
            self.shell_state_seen = state
            return False
        self.shell_state_seen = state
        return self.shell.set_documents(self.library.drafts())

    def _final_viewport_displayed(self):
        if self.last_sent_payload is None:
            return False
        built = self._build_viewport()
        if built is not None and built[1] != self.last_sent_payload:
            return False
        state = self.tracker.find(self.last_sent_revision)
        return state is not None and state.displayed

    # ------------------------------------------------------------- main cycle

    def service(self):
        """One cooperative iteration of the input-first live scheduler."""
        now = self.monotonic()
        if self.phase == PHASE_DONE:
            return

        # Stages 1 to 3: input is always polled, normalized, and routed before
        # any viewport work, so display timing can never reorder or drop an edit.
        if self.phase in (PHASE_HELLO, PHASE_LIVE):
            self._poll_keyboard(now)
        if self.phase == PHASE_LIVE:
            self._drain_input(now)

        # Stage 4.
        self._drain_status(now)

        # Stage 5, which runs *before* the viewport stages exactly as the
        # architecture's loop order specifies. Durability is never made to wait
        # on a display refresh, and the save indicator the viewport draws is
        # already current by the time the frame is built.
        if self.phase in (PHASE_LIVE, PHASE_DRAIN):
            self._service_persistence(now)

        # Stage 6 of the architecture's loop order: workflow state owned by the
        # Fruit Jam, applied after input and durability and before any frame is
        # built, so the screen that goes out is the one the writer just asked for.
        if self.phase == PHASE_LIVE:
            self._service_shell(now)

        # Stages 7 and 8.
        if self.phase == PHASE_HELLO:
            if self.frame_sequence == 0:
                self._emit(HELLO, 0, HELLO_PAYLOAD)
            elif self.tracker.hello:
                self.phase = PHASE_LIVE
                self.log({
                    "event": "live_typing_started",
                    "usb_ready": self.adapter.ready,
                })
        elif self.phase == PHASE_LIVE:
            self._maybe_send_viewport(now)
            # Without a shell the finish gesture ends the session, exactly as it
            # did for every run that produced the existing evidence. With one it
            # means *back*, and only the shell reaching its own terminal state
            # ends the session -- which is what makes the gesture safe to press
            # inside a document.
            stopping = (
                self.shell.exiting if self.shell is not None
                else self.adapter.finish_requested
            )
            if stopping and not len(self.queue):
                self.phase = PHASE_DRAIN
                # A deliberate stop is the one moment a checkpoint is
                # unambiguously worth its cost, so it does not wait for a
                # threshold. The queue is already empty, so this checkpoints the
                # complete final document rather than a state part-way through it.
                if self.persistence is not None:
                    self.persistence.save_now(now, self.editor)
                self.log({
                    "event": "live_typing_finished",
                    "events_processed": self.events_processed,
                    "text": self.editor.text,
                })
        elif self.phase == PHASE_DRAIN:
            if self.editor.viewport_revision == 0 and self.shell is None:
                # Escape was pressed without a single edit, so there is no final
                # viewport to reconcile. Stop explicitly rather than wait out the
                # session bound for a frame that can never be built.
                raise LiveSessionError("finished with an empty document")
            self._maybe_send_viewport(now, force=True)
            if self._final_viewport_displayed():
                self._emit(END_OF_TEST, self.last_sent_revision, (
                    "%d;%d;%08X" % (
                        self.last_sent_revision, self.viewport_frames_sent,
                        self.last_sent_hash,
                    )
                ).encode("ascii"))
                self.phase = PHASE_END
        elif self.phase == PHASE_END:
            if self.tracker.final_complete:
                self.phase = PHASE_DONE
                self.log({
                    "event": "live_test_complete",
                    "displayed_revision": self.tracker.final_displayed_revision,
                    "final_hash": "%08X" % self.tracker.final_hash,
                })

        # Stage 9.
        self.tracker.check_timeouts(now)
        if now - self.started_at > self.session_timeout_seconds:
            raise LiveSessionError("live session timeout")
        if (
            self.phase == PHASE_LIVE
            and now - self.last_activity_at > self.idle_timeout_seconds
        ):
            raise LiveSessionError("live session idle timeout")

    # ---------------------------------------------------------------- summary

    def summary(self, result):
        record = {
            "event": "usb_keyboard_test_summary",
            "result": result,
            "stop_reason": self.stop_reason,
            "events_generated": self.sequence_tracker.expected,
            "events_processed": self.events_processed,
            "events_rejected": self.events_rejected,
            "queue_overflows": self.queue_overflows + self.adapter.queue_overflows,
            "maximum_queue_depth": self.queue.maximum_depth,
            "queue_capacity": self.queue.capacity,
            "document_revision": self.editor.document_revision,
            "final_viewport_revision": self.editor.viewport_revision,
            "final_document_text": self.editor.text,
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
        record.update(self.pacer.summary())
        record.update(self.latency.summary())
        record.update(self.adapter.summary())
        if self.persistence is not None:
            record["manual_save_requests"] = self.save_requests_serviced
            record.update(self.persistence.summary())
        if self.shell is not None:
            record["shell_routed_events"] = self.shell_events
            record["finish_requests_serviced"] = self.finish_requests_serviced
            record.update(self.shell.summary())
        if self.library is not None:
            record["documents_opened"] = self.documents_opened
            record["document_switches"] = self.document_switches
            record["document_open_failures"] = self.document_open_failures
            record.update(self.library.summary())
        return record
