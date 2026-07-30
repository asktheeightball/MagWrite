"""The four writing modes, as thin policy over one editor and one store.

Host-safe. This module is where V1.4's requirement that "each mode is a thin
policy over the one proven editor and storage layer" is actually cashed in, so it
is worth being explicit about how thin: **no mode here owns a document format, a
record format, a recovery rule, a renderer, or a transport.** Every one of them
resolves to the same two operations --

    index.record / index.touch      which document, and that it was opened now
    store.select(document_id)       point the proven store at it and recover it

-- and hands the resulting snapshot back for the session to load into the one
editor. A mode is a *choice of document*, and that is all a mode is.

The four
--------

**Journal** — append-oriented. Opens the newest journal entry with the cursor at
the end of the writer's last words, so sitting down and typing continues the
entry rather than starting a page. When that entry is close enough to the
document bound that there is no useful room left, the next numbered entry is
started instead, which is the one place a journal rolls over.

*Dating is deferred, and deliberately.* The prototype has no RTC and no network,
so the device cannot know today's date; the choice was between numbering entries
honestly and stamping them with a date derived from ``time.monotonic``, which
would be a fabricated date printed next to a writer's own words. Entries are
numbered. When a time source exists, ``_journal_title`` is the one function that
changes, and the rollover rule above becomes a date comparison.

**Quick Note** — always a new, empty document, opened immediately. It is the only
mode that never asks a question, because the entire value of it is the interval
between deciding to write something down and being able to.

**Drafts** — the working set. Not a mode a document can be *in*: it is a way of
reaching one, and a note reached through Drafts is still a note.

**Recent** — the document with the highest open ordinal in the catalogue, which
is the one that was open last. It survives forced power loss for the same reason
the document does: the ordinal is a record in an append-only log, written when
the document is opened rather than when it is closed, so there is no "on close"
step for a power cut to interrupt.

Failure is a returned value, never an exception
-----------------------------------------------

Every entry point returns an :class:`Opening` or ``None`` with ``last_error``
set. A mode that could raise would be a mode that can end a session holding an
unsaved document, and the shell above this is fail-closed precisely so that a
refusal becomes a screen the writer can dismiss. The full card, the full
catalogue, and the document too large to load all arrive the same way.
"""

from magwrite_transport.document_index import (
    KIND_DRAFT, KIND_JOURNAL, KIND_NOTE,
)
from magwrite_transport.document_store import ACTIVE_ID
from magwrite_transport.editor import MAX_DOCUMENT_CHARS

JOURNAL_PREFIX = "j"
NOTE_PREFIX = "n"

# A journal entry rolls over when fewer than this many characters remain. Sized
# to be a paragraph rather than a word: rolling over with forty characters left
# would hand the writer an entry they cannot finish a thought in.
JOURNAL_ROLLOVER_MARGIN = 512

# The title given to a document recovered from a pre-V1.4 card. It is called what
# it is -- an existing draft of unknown origin -- rather than being guessed at.
MIGRATED_TITLE = "DRAFT"


class Opening:
    """A document the session should now load into the one editor."""

    __slots__ = ("entry", "snapshot", "created", "recovery")

    def __init__(self, entry, snapshot=None, created=False, recovery=None):
        self.entry = entry
        self.snapshot = snapshot
        self.created = created
        self.recovery = recovery

    @property
    def document_id(self):
        return self.entry.document_id

    @property
    def kind(self):
        return self.entry.kind

    @property
    def title(self):
        return self.entry.title

    @property
    def text(self):
        return "" if self.snapshot is None else self.snapshot.text

    def cursor(self):
        """Where the cursor goes: the stored position, or nowhere for a new one."""
        if self.snapshot is None:
            return 0, 0
        return self.snapshot.row, self.snapshot.column

    def end_cursor(self):
        """The end of the document, for the append-oriented journal."""
        if self.snapshot is None:
            return 0, 0
        lines = self.snapshot.text.split("\n")
        return len(lines) - 1, len(lines[-1])

    def summary(self):
        record = dict(self.entry.summary())
        record["created"] = self.created
        record["characters"] = len(self.text)
        return record


class Library:
    """Which document each menu item opens. Owns no text and no durability."""

    def __init__(self, store, index, log=None, max_chars=MAX_DOCUMENT_CHARS,
                 rollover_margin=JOURNAL_ROLLOVER_MARGIN):
        self.store = store
        self.index = index
        self.log = log
        self.max_chars = max_chars
        self.rollover_margin = rollover_margin
        self.last_error = None
        self.opens = 0
        self.creations = 0
        self.refusals = 0

    # ---------------------------------------------------------------- opening

    def open_journal(self):
        """Continue the newest journal entry, or begin the next one."""
        newest = self.index.newest_of_kind(KIND_JOURNAL)
        if newest is not None:
            opening = self._open_existing(newest.document_id)
            if opening is None:
                return None
            if len(opening.text) + self.rollover_margin <= self.max_chars:
                row, column = opening.end_cursor()
                # Append-oriented: the cursor lands after the last words the
                # writer wrote, not at the top of them.
                if opening.snapshot is not None:
                    opening.snapshot.row = row
                    opening.snapshot.column = column
                return opening
            self._report("journal_rollover", document_id=newest.document_id,
                         characters=len(opening.text))
        return self._create(KIND_JOURNAL, JOURNAL_PREFIX, self._journal_title())

    def new_note(self):
        """Quick Note: a new empty document, opened immediately."""
        return self._create(KIND_NOTE, NOTE_PREFIX, self._note_title())

    def open_recent(self):
        """Return to whatever was open last."""
        entry = self.index.active()
        if entry is None:
            return self._refuse("nothing has been opened yet")
        return self._open_existing(entry.document_id)

    def open_document(self, document_id):
        """Open a specific document, which is how Drafts opens one."""
        if self.index.get(document_id) is None:
            return self._refuse("unknown document: " + str(document_id))
        return self._open_existing(document_id)

    def drafts(self):
        """The working set, most recently opened first."""
        return self.index.ordered()

    # -------------------------------------------------------------- migration

    def migrate(self, recovery):
        """Adopt a document that predates the catalogue. Returns the ``Entry``.

        The V1.2 and V1.3 files are already correct under the per-document
        naming, so this writes one catalogue record and moves, renames, and
        rewrites nothing. **The recovered document is preserved exactly**: it
        keeps its id, its journal, its checkpoints, and its mirror, and the only
        thing that changes about it is that the catalogue now knows it is there.

        Returns ``None`` when there is nothing to migrate, which is the ordinary
        case on a card this build wrote.
        """
        if self.index.get(ACTIVE_ID) is not None:
            return None
        if recovery is None or not recovery.recovered:
            return None
        entry = self.index.record(ACTIVE_ID, KIND_DRAFT, MIGRATED_TITLE)
        if entry is None:
            self.last_error = self.index.last_error
            self._report("document_migration_failed", detail=self.last_error)
            return None
        self._report(
            "document_migrated", document_id=ACTIVE_ID, kind=KIND_DRAFT,
            revision=recovery.revision,
            characters=0 if recovery.snapshot is None else len(recovery.snapshot.text),
        )
        return entry

    # ----------------------------------------------------------------- detail

    def _journal_title(self):
        """Numbered, not dated. See the module docstring."""
        return "JOURNAL %d" % (self._count_of_kind(KIND_JOURNAL) + 1)

    def _note_title(self):
        return "NOTE %d" % (self._count_of_kind(KIND_NOTE) + 1)

    def _count_of_kind(self, kind):
        return sum(1 for entry in self.index.entries.values() if entry.kind == kind)

    def _create(self, kind, prefix, title):
        document_id = self.index.next_id(prefix)
        if document_id is None:
            return self._refuse("no free document id remains on this card")
        # The catalogue record is written *before* the document exists, so the
        # only entry a power cut can lose is the entry for an empty document.
        entry = self.index.record(document_id, kind, title)
        if entry is None:
            return self._refuse(self.index.last_error or "catalogue refused a document")
        try:
            self.store.select(document_id)
        except Exception as error:  # noqa: BLE001 - reported, never raised onward
            return self._refuse("cannot open " + document_id + ": " + str(error))
        self.opens += 1
        self.creations += 1
        self.last_error = None
        opening = Opening(entry, None, created=True)
        self._report("document_opened", **opening.summary())
        return opening

    def _open_existing(self, document_id):
        entry = self.index.touch(document_id)
        if entry is None:
            return self._refuse(self.index.last_error or "catalogue refused an open")
        try:
            recovery = self.store.select(document_id)
        except Exception as error:  # noqa: BLE001 - reported, never raised onward
            return self._refuse("cannot open " + document_id + ": " + str(error))
        self.opens += 1
        self.last_error = None
        opening = Opening(entry, recovery.snapshot, recovery=recovery)
        self._report("document_opened", source=recovery.source,
                     **opening.summary())
        return opening

    def _refuse(self, reason):
        self.refusals += 1
        self.last_error = str(reason)
        self._report("document_open_refused", detail=self.last_error)
        return None

    def _report(self, event, **fields):
        if self.log is not None:
            fields["event"] = event
            self.log(fields)

    def summary(self):
        record = {
            "library_opens": self.opens,
            "library_creations": self.creations,
            "library_refusals": self.refusals,
            "library_last_error": self.last_error,
        }
        record.update(self.index.summary())
        return record
