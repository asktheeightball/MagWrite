"""The MagWrite shell: the one owner of application state, above the editor.

Host-safe. This module holds no editor, no document, no store, no clock, and no
transport. It decides *where the writer is* and *where input goes*, and nothing
else. That separation is the whole point of the phase: the editor already owns
the document and both revisions, persistence already owns durability, and a
shell that reached into either would become a second author of state that has to
agree with the first forever.

What the shell owns
-------------------

* the current state, from a closed set;
* which menu item is selected, and which mode a document was entered through;
* the identity of the open document — its id, kind, and title — which it is
  *told*, and never reads from a card;
* which draft is selected in the Drafts list;
* at most one pending request for the session to perform;
* a monotonic ``visible_revision`` so the session knows the drawn state changed.

What the shell must never do
----------------------------

* construct, clear, reload, or truncate the editor;
* open, create, or select a document on the card;
* decide when a document is durable;
* raise.

Requests, added in V1.4
-----------------------

Three of the four menu items have to *open something*, and opening something is
filesystem work the shell is not allowed to do. So the shell does not do it: it
records a bounded request — at most one, replaced rather than queued — and the
session performs it in the same loop iteration, before any frame is built, and
reports back through :meth:`Shell.opened` or :meth:`Shell.fault`. The writer never
sees an intermediate screen, and the shell never grows a filesystem.

The request is deliberately *not* a precondition for the transition. Entering the
editor happens immediately, exactly as it did in V1.3, so a build with no card
and no library behaves precisely as the verified V1.3 build did rather than
stranding the writer at a menu whose items cannot be serviced.

The last one is requirement 11 and is enforced structurally rather than by
convention: every entry point below funnels through ``_transition``, and anything
it cannot make sense of becomes ``ERROR`` with a recorded reason. A shell that
can crash the loop is a shell that can lose the document sitting in RAM behind
it, which is the one outcome no menu is worth.

Why the document survives every transition
------------------------------------------

Because no transition touches it. There is exactly one ``MultilineEditor`` for
the life of the session, and the shell only changes what is drawn and where
input is routed. Leaving the editor cannot discard unsaved work for the same
reason closing a lid cannot: nothing was closed. Entering ``SAVE_STATUS``
additionally forces a checkpoint, so the writer who walks away has their words on
the card as well as in RAM.

The finish gesture
------------------

Escape, and Keyboard Application (``0x65``) for the 40% keyboards whose Escape
is only reachable through an Fn layer that drops the device off USB. It already
existed as the clean-stop control; under the shell it means **back** — leave the
current state toward its parent — and at the root that is still the stop. One
gesture, one meaning, no new keymap entry, and the physical evidence for it was
collected in V1.1.
"""

from magwrite_transport.document_index import (
    KIND_DRAFT, KIND_JOURNAL, KIND_NOTE,
)
from magwrite_transport.editor import DOWN, ENTER, UP

# ------------------------------------------------------------------- states

STATE_MAIN_MENU = "MAIN_MENU"
STATE_EDITOR = "EDITOR"
STATE_SAVE_STATUS = "SAVE_STATUS"
STATE_ERROR = "ERROR"
# The Drafts list. The one menu item that shows the writer a choice rather than
# opening something, because it is the only one whose answer the device cannot
# know: Journal continues the newest entry, Quick Note is always new, and Recent
# is by definition the last one.
STATE_DRAFTS = "DRAFTS"
# Not a screen. It is the terminal state the session reads to begin its ordinary
# drain-and-stop, kept in the same closed set so "where is the writer" always has
# exactly one answer.
STATE_EXIT = "EXIT"

STATES = (
    STATE_MAIN_MENU, STATE_EDITOR, STATE_SAVE_STATUS, STATE_DRAFTS,
    STATE_ERROR, STATE_EXIT,
)

# -------------------------------------------------------------------- modes

MODE_JOURNAL = "JOURNAL"
MODE_QUICK_NOTE = "QUICK_NOTE"
MODE_DRAFTS = "DRAFTS"
MODE_RECENT = "RECENT"

# ``(mode, label)``. The label is what the panel draws, so it is written in
# characters the proven 3x5 glyph table actually has -- which is why the mode
# identifier and its label are separate strings rather than one with an
# underscore in it. A host test asserts every label is renderable.
MENU_ITEMS = (
    (MODE_JOURNAL, "JOURNAL"),
    (MODE_QUICK_NOTE, "QUICK NOTE"),
    (MODE_DRAFTS, "DRAFTS"),
    (MODE_RECENT, "RECENT"),
)

# The menu item a *document* belongs to, by its kind.
#
# This is the answer to the question V1.3 handed forward: a restored session did
# not restore its mode, because the mode was derived from the menu rather than
# from the document. It is now a property of the document, which is where it
# belongs -- a note is a note however it was reached, and a document recovered
# from the card brings its own kind back with it. ``DRAFTS`` is the menu item for
# a plain draft because that is the item a writer would reach it through, not
# because "draft" is a way of writing.
MODE_FOR_KIND = {
    KIND_JOURNAL: MODE_JOURNAL,
    KIND_NOTE: MODE_QUICK_NOTE,
    KIND_DRAFT: MODE_DRAFTS,
}

# --------------------------------------------------------------- routing

ROUTE_EDITOR = "EDITOR"
ROUTE_CONSUMED = "CONSUMED"

# ------------------------------------------------------------------ requests

# What the shell asks the session to do on its behalf. At most one is pending at
# a time and a new one replaces an unserviced one, because these are the writer's
# most recent intention and a queue of stale intentions is not a feature.
REQUEST_JOURNAL = "OPEN_JOURNAL"
REQUEST_QUICK_NOTE = "NEW_QUICK_NOTE"
REQUEST_RECENT = "OPEN_RECENT"
REQUEST_OPEN = "OPEN_DOCUMENT"
REQUESTS = (REQUEST_JOURNAL, REQUEST_QUICK_NOTE, REQUEST_RECENT, REQUEST_OPEN)

# What each menu item asks for. ``DRAFTS`` is absent deliberately: it opens a
# list, which is a screen the shell owns outright and needs nothing from the card
# it has not already been given.
REQUEST_FOR_MODE = {
    MODE_JOURNAL: REQUEST_JOURNAL,
    MODE_QUICK_NOTE: REQUEST_QUICK_NOTE,
    MODE_RECENT: REQUEST_RECENT,
}

# The Drafts list is drawn on a five-row panel, one row per document, and the
# selection scrolls through a longer catalogue rather than the panel growing.
DRAFT_ROWS = 5


class Shell:
    """Bounded, fail-closed application state above the authoritative editor."""

    def __init__(self, items=MENU_ITEMS, log=None, state=STATE_MAIN_MENU):
        if not items:
            raise ValueError("the main menu needs at least one item")
        if state not in STATES:
            raise ValueError("unknown initial shell state: " + str(state))
        self.items = tuple(items)
        self.log = log
        self.state = state
        self.selection = 0
        self.mode = None
        self.error_reason = None
        # Starts at 1, not 0. The first thing the shell does is put a screen on
        # the panel, and the session's send path treats revision 0 as "nothing
        # has ever been visible" and declines to build a frame for it.
        self.visible_revision = 1
        self.entries = 0
        self.backs = 0
        self.faults = 0
        self.ignored_events = 0
        self.save_state = None
        # V1.4. The identity of the document the editor currently holds, as the
        # session most recently reported it. The shell is *told* this; it never
        # reads a card and never decides which document is open.
        self.document_id = None
        self.document_kind = None
        self.document_title = None
        self.documents = ()
        self.draft_selection = 0
        self.draft_top = 0
        self.pending_request = None
        self.pending_argument = None
        self.requests_made = 0
        self.documents_opened = 0

    # ------------------------------------------------------------- queries

    @property
    def editor_active(self):
        """True when normalized input belongs to the authoritative editor."""
        return self.state == STATE_EDITOR

    @property
    def exiting(self):
        return self.state == STATE_EXIT

    @property
    def selected_mode(self):
        return self.items[self.selection][0]

    @property
    def selected_label(self):
        return self.items[self.selection][1]

    def mode_label(self):
        """The label for the mode a document was entered through."""
        for mode, label in self.items:
            if mode == self.mode:
                return label
        return None

    def panel_title(self):
        """What the editor's title field names: the document, else the mode.

        The document's own title is preferred because it is the thing the writer
        chose to open and the only string that distinguishes one journal entry
        from the next. The mode label is the fallback for a build with no
        catalogue, which is exactly the V1.3 behaviour those runs measured.
        """
        return self.document_title or self.mode_label()

    @property
    def draft_count(self):
        return len(self.documents)

    def selected_document(self):
        """The Drafts entry under the cursor, or ``None`` on an empty list."""
        if not self.documents or not 0 <= self.draft_selection < len(self.documents):
            return None
        return self.documents[self.draft_selection]

    def visible_drafts(self):
        """The window of the catalogue the panel can show, and its offset."""
        return self.documents[self.draft_top : self.draft_top + DRAFT_ROWS]

    def take_request(self):
        """Return and clear the pending request, or ``None``.

        Taken rather than read, so a request is serviced exactly once. Leaving it
        in place would re-open a document on every loop iteration, which on a
        create-always mode like Quick Note would fill the card with empty notes.
        """
        request = self.pending_request
        if request is None:
            return None
        argument = self.pending_argument
        self.pending_request = None
        self.pending_argument = None
        return request, argument

    def _request(self, request, argument=None):
        if request not in REQUESTS:
            return self._fault("unknown request: " + str(request))
        self.pending_request = request
        self.pending_argument = argument
        self.requests_made += 1
        self._log({"event": "shell_request", "request": request,
                   "argument": argument, "mode": self.mode})
        return request

    # ---------------------------------------------------------- transitions

    def _note_visible_change(self):
        self.visible_revision += 1
        return self.visible_revision

    def _transition(self, state, reason=None):
        """The single door every state change goes through.

        An unknown target is not a crash and not a silent no-op: it is the fault
        path, because a shell that cannot name where it is has already lost the
        property that makes it safe to leave a document behind.
        """
        if state not in STATES:
            return self._fault("invalid transition target: " + str(state))
        if state == self.state:
            return self.state
        previous = self.state
        self.state = state
        if state != STATE_ERROR:
            self.error_reason = None
        self._note_visible_change()
        self._log({
            "event": "shell_transition", "from": previous, "to": state,
            "mode": self.mode, "reason": reason,
            "visible_revision": self.visible_revision,
        })
        return self.state

    def _fault(self, reason):
        """Fail closed into a recoverable screen. The document is untouched."""
        self.faults += 1
        self.error_reason = str(reason)
        if self.state != STATE_ERROR:
            previous = self.state
            self.state = STATE_ERROR
            self._note_visible_change()
            self._log({
                "event": "shell_fault", "from": previous, "reason": self.error_reason,
                "visible_revision": self.visible_revision,
            })
        else:
            # Already faulted. Record the newer reason and redraw, so a second
            # failure is visible rather than hidden behind the first.
            self._note_visible_change()
            self._log({"event": "shell_fault_repeated",
                       "reason": self.error_reason})
        return self.state

    def fault(self, reason):
        """Report a failure from outside the shell -- a rejected edit, say."""
        return self._fault(reason)

    # -------------------------------------------------------------- signals

    def enter(self):
        """Open the selected menu item.

        Drafts shows a list; the other three enter the editor and ask the session
        to put the right document in it. The transition is not made to wait on
        that request -- see the module docstring -- so a build with no catalogue
        behaves exactly as the verified V1.3 build did.
        """
        if self.state != STATE_MAIN_MENU:
            return self._fault("enter is only defined in the main menu")
        self.mode = self.selected_mode
        self.entries += 1
        self._log({"event": "shell_mode_entered", "mode": self.mode,
                   "label": self.selected_label, "entries": self.entries})
        if self.mode == MODE_DRAFTS:
            self.draft_selection = 0
            self.draft_top = 0
            return self._transition(STATE_DRAFTS, "browsing drafts")
        request = REQUEST_FOR_MODE.get(self.mode)
        if request is not None:
            self._request(request)
        return self._transition(STATE_EDITOR, "menu selection")

    def open_selected_draft(self):
        """Ask the session to open the draft under the cursor."""
        if self.state != STATE_DRAFTS:
            return self._fault("opening a draft is only defined in the list")
        entry = self.selected_document()
        if entry is None:
            # An empty list is not a fault. There is simply nothing to open, and
            # a writer pressing Enter at "NO DRAFTS" has made no mistake.
            self.ignored_events += 1
            return self.state
        self.mode = MODE_FOR_KIND.get(entry.kind, MODE_DRAFTS)
        self._request(REQUEST_OPEN, entry.document_id)
        return self._transition(STATE_EDITOR, "draft selection")

    def back(self):
        """The finish gesture: leave the current state toward its parent."""
        self.backs += 1
        state = self.state
        if state == STATE_EDITOR:
            # Not a discard and not a close. The editor keeps the document and
            # the cursor exactly as they are; the session checkpoints on the way
            # through so the words are durable as well as present.
            return self._transition(STATE_SAVE_STATUS, "left the editor")
        if state == STATE_SAVE_STATUS:
            return self._transition(STATE_EDITOR, "resumed writing")
        if state == STATE_DRAFTS:
            return self._transition(STATE_MAIN_MENU, "left the drafts list")
        if state == STATE_ERROR:
            return self._transition(STATE_MAIN_MENU, "dismissed the error")
        if state == STATE_MAIN_MENU:
            # The root. Back from here is the clean stop the runtime already had.
            return self._transition(STATE_EXIT, "stopped from the main menu")
        if state == STATE_EXIT:
            return self.state
        return self._fault("back is undefined in state " + str(state))

    # ------------------------------------------------------------- documents

    def set_documents(self, entries):
        """Adopt the catalogue the session read. Returns True if it changed.

        The shell is handed the list rather than fetching it, which is the whole
        of why it still owns no storage. It bounds and clamps what it is given
        and nothing more.
        """
        entries = tuple(entries)
        if entries == self.documents:
            return False
        self.documents = entries
        if self.draft_selection >= len(entries):
            self.draft_selection = max(0, len(entries) - 1)
        self._clamp_draft_window()
        if self.state == STATE_DRAFTS:
            self._note_visible_change()
        return True

    def opened(self, document_id, kind=None, title=None):
        """Adopt the identity of the document the session just opened.

        Called after the open succeeded, so the shell's idea of what is in the
        editor is never ahead of what is actually in it. The mode follows the
        document's kind, which is what makes a mode survive a restart.
        """
        self.document_id = document_id
        self.document_kind = kind
        self.document_title = title
        self.documents_opened += 1
        if kind is not None:
            mode = MODE_FOR_KIND.get(kind)
            if mode is not None:
                self.mode = mode
        self._note_visible_change()
        self._log({"event": "shell_document_opened", "document_id": document_id,
                   "kind": kind, "title": title, "mode": self.mode,
                   "state": self.state})
        return self.document_id

    def note_save_state(self, state):
        """Adopt the save state the persistence layer computed.

        Stored rather than derived, and never recomputed here: there is exactly
        one function in the codebase that decides what is durable, and this is
        not it. The value is drawn on the save screen and nowhere else.
        """
        if state == self.save_state:
            return False
        self.save_state = state
        if self.state == STATE_SAVE_STATUS:
            # Only a change to a screen currently on the panel is a redraw.
            self._note_visible_change()
            return True
        return False

    # --------------------------------------------------------------- input

    def route(self, event):
        """Return where one normalized input event belongs.

        ``ROUTE_EDITOR`` means the session applies it to the authoritative
        editor. ``ROUTE_CONSUMED`` means the shell handled it, or deliberately
        ignored it -- an ignored key is counted, never silently dropped.
        """
        state = self.state
        if state == STATE_EDITOR:
            return ROUTE_EDITOR
        if state == STATE_MAIN_MENU:
            self._menu_key(event)
            return ROUTE_CONSUMED
        if state == STATE_DRAFTS:
            self._draft_key(event)
            return ROUTE_CONSUMED
        if state in (STATE_SAVE_STATUS, STATE_ERROR):
            if event.kind == ENTER:
                self._transition(STATE_MAIN_MENU, "confirmed")
            else:
                self.ignored_events += 1
            return ROUTE_CONSUMED
        if state == STATE_EXIT:
            self.ignored_events += 1
            return ROUTE_CONSUMED
        self._fault("input is undefined in state " + str(state))
        return ROUTE_CONSUMED

    def _menu_key(self, event):
        kind = event.kind
        if kind == UP:
            self._move(-1)
        elif kind == DOWN:
            self._move(1)
        elif kind == ENTER:
            self.enter()
        else:
            # Typing at the menu does not fall through into the document. A
            # keystroke that means nothing here means nothing, and the writer
            # finding stray characters in their draft is exactly the loss of
            # trust this phase exists to avoid.
            self.ignored_events += 1

    def _move(self, delta):
        """Clamped, not wrapped: the ends of a four-item list stay the ends."""
        target = self.selection + delta
        if target < 0 or target >= len(self.items):
            return False
        self.selection = target
        self._note_visible_change()
        self._log({"event": "shell_selection_moved", "selection": self.selection,
                   "label": self.selected_label})
        return True

    def _draft_key(self, event):
        kind = event.kind
        if kind == UP:
            self._move_draft(-1)
        elif kind == DOWN:
            self._move_draft(1)
        elif kind == ENTER:
            self.open_selected_draft()
        else:
            # Same rule as the menu: a keystroke aimed at a list means nothing
            # and must never fall through into whatever document the editor is
            # still holding behind this screen.
            self.ignored_events += 1

    def _move_draft(self, delta):
        """Clamped, and the window follows the selection rather than the reverse."""
        target = self.draft_selection + delta
        if target < 0 or target >= len(self.documents):
            return False
        self.draft_selection = target
        self._clamp_draft_window()
        self._note_visible_change()
        entry = self.selected_document()
        self._log({
            "event": "shell_draft_selected", "selection": self.draft_selection,
            "document_id": None if entry is None else entry.document_id,
            "title": None if entry is None else entry.title,
        })
        return True

    def _clamp_draft_window(self):
        """Keep the selection inside the visible rows. A pure clamp, no history."""
        if self.draft_selection < self.draft_top:
            self.draft_top = self.draft_selection
        elif self.draft_selection >= self.draft_top + DRAFT_ROWS:
            self.draft_top = self.draft_selection - DRAFT_ROWS + 1
        if self.draft_top < 0:
            self.draft_top = 0

    # ------------------------------------------------------------- recovery

    def restore(self, recovered, revision=0, document_id=None, kind=None,
                title=None):
        """Choose the opening state from what the card gave back.

        The *state* is still derived rather than stored, deliberately: persisting
        it would mean a second file that has to stay in step with the journal
        through a power cut, which is the two-file atomicity problem the storage
        design already refused once. A recovered document means the writer was
        writing, so the shell opens where the words are; an empty card means they
        were not, so it opens at the menu.

        The **mode** is a different matter, and this is where V1.3's one
        acknowledged gap closes. It used to be taken from whatever the menu
        happened to be pointing at, so a session that ended in a note reopened
        claiming to be a journal. It now arrives with the document, because the
        kind is a property of the document and is recorded in the catalogue
        alongside it. Nothing new is persisted to achieve that -- the catalogue
        already had to exist for Drafts and Recent.
        """
        if recovered and revision > 0:
            if document_id is not None:
                self.opened(document_id, kind, title)
            if self.mode is None:
                # No catalogue, so no kind came back. Fall back to the menu's own
                # selection, which is exactly the V1.3 behaviour.
                self.mode = self.selected_mode
            self._sync_selection()
            self._transition(STATE_EDITOR, "recovered document")
        else:
            self._transition(STATE_MAIN_MENU, "no recovered document")
        self._log({"event": "shell_restored", "state": self.state,
                   "recovered": bool(recovered), "revision": revision,
                   "mode": self.mode, "document_id": self.document_id,
                   "title": self.document_title})
        return self.state

    def _sync_selection(self):
        """Point the menu cursor at the mode the open document belongs to.

        So that backing out to the menu lands on the item the writer was just in
        rather than on whatever was highlighted before the restart.
        """
        for index, item in enumerate(self.items):
            if item[0] == self.mode:
                self.selection = index
                return True
        return False

    # -------------------------------------------------------------- reporting

    def _log(self, record):
        if self.log is not None:
            self.log(record)

    def summary(self):
        return {
            "shell_state": self.state,
            "shell_mode": self.mode,
            "shell_selection": self.selection,
            "shell_entries": self.entries,
            "shell_backs": self.backs,
            "shell_faults": self.faults,
            "shell_ignored_events": self.ignored_events,
            "shell_error_reason": self.error_reason,
            "shell_visible_revision": self.visible_revision,
            "shell_document_id": self.document_id,
            "shell_document_kind": self.document_kind,
            "shell_document_title": self.document_title,
            "shell_requests": self.requests_made,
            "shell_documents_opened": self.documents_opened,
            "shell_drafts_listed": len(self.documents),
        }
