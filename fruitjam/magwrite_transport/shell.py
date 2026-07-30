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
* a monotonic ``visible_revision`` so the session knows the drawn state changed.

What the shell must never do
----------------------------

* construct, clear, reload, or truncate the editor;
* decide when a document is durable;
* raise.

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

from magwrite_transport.editor import DOWN, ENTER, UP

# ------------------------------------------------------------------- states

STATE_MAIN_MENU = "MAIN_MENU"
STATE_EDITOR = "EDITOR"
STATE_SAVE_STATUS = "SAVE_STATUS"
STATE_ERROR = "ERROR"
# Not a screen. It is the terminal state the session reads to begin its ordinary
# drain-and-stop, kept in the same closed set so "where is the writer" always has
# exactly one answer.
STATE_EXIT = "EXIT"

STATES = (
    STATE_MAIN_MENU, STATE_EDITOR, STATE_SAVE_STATUS, STATE_ERROR, STATE_EXIT,
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
#
# For this phase all four route into the same single document, exactly as the
# scope allows. The mode is carried anyway, because it is the seam V1.4 attaches
# its per-mode policy to, and because a menu that gives no sign of which item was
# chosen is a menu that is lying about having four items.
MENU_ITEMS = (
    (MODE_JOURNAL, "JOURNAL"),
    (MODE_QUICK_NOTE, "QUICK NOTE"),
    (MODE_DRAFTS, "DRAFTS"),
    (MODE_RECENT, "RECENT"),
)

# --------------------------------------------------------------- routing

ROUTE_EDITOR = "EDITOR"
ROUTE_CONSUMED = "CONSUMED"


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
        """Open the selected menu item. The one document is never replaced."""
        if self.state != STATE_MAIN_MENU:
            return self._fault("enter is only defined in the main menu")
        self.mode = self.selected_mode
        self.entries += 1
        self._log({"event": "shell_mode_entered", "mode": self.mode,
                   "label": self.selected_label, "entries": self.entries})
        return self._transition(STATE_EDITOR, "menu selection")

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
        if state == STATE_ERROR:
            return self._transition(STATE_MAIN_MENU, "dismissed the error")
        if state == STATE_MAIN_MENU:
            # The root. Back from here is the clean stop the runtime already had.
            return self._transition(STATE_EXIT, "stopped from the main menu")
        if state == STATE_EXIT:
            return self.state
        return self._fault("back is undefined in state " + str(state))

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

    # ------------------------------------------------------------- recovery

    def restore(self, recovered, revision=0):
        """Choose the opening state from what the card gave back.

        Derived rather than stored, deliberately. Persisting the shell state
        would mean a second file that has to stay in step with the journal
        through a power cut, which is the two-file atomicity problem the storage
        design already refused once. There is nothing to keep in step here: a
        recovered document means the writer was writing, so the shell opens where
        the words are, and an empty card means they were not, so it opens at the
        menu.
        """
        if recovered and revision > 0:
            self.mode = self.selected_mode
            self._transition(STATE_EDITOR, "recovered document")
        else:
            self._transition(STATE_MAIN_MENU, "no recovered document")
        self._log({"event": "shell_restored", "state": self.state,
                   "recovered": bool(recovered), "revision": revision,
                   "mode": self.mode})
        return self.state

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
        }
