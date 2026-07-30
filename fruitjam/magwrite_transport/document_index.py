"""The document catalogue: identity, kind, title, and last-opened ordering.

Host-safe. V1.4 needs to answer four questions that a single-document store
cannot: which documents exist, what each one is called, what kind each one is,
and which was open last. This module answers exactly those and nothing else. It
does not know what a mode is, it does not decide which document to open, and it
never touches a document's text -- ``library`` owns policy and ``document_store``
owns durability.

Why an append-only log again, rather than a small file rewritten
---------------------------------------------------------------

Because the same argument that produced the recovery journal produces this. A
rewritten catalogue has a window in which it is neither the old contents nor the
new ones, and the thing it would be describing in that window is *where the
writer's documents are*. An append-only log of ``MWX1`` records has the same
three independent corruption defences the recovery journal has -- a missing
newline, a short body, a failed CRC -- and a truncated final record means exactly
one open was not recorded, which costs the ordering of one document and nothing
else.

The record::

    MWX1 <seq> <opened> <kind> <id> <length> <crc8hex> <escaped-title>\\n

``opened`` is a monotonic counter incremented every time a document is opened,
and it is the whole of "last-opened ordering" and "which document is active".
The highest ``opened`` in the catalogue *is* the active document, which is why
there is no second file holding a pointer and therefore no second file that can
disagree with this one after a power cut. That was the mistake worth not making
twice: an "active document" pointer stored separately from the catalogue is the
two-file atomicity problem in a new hat.

Later records win per id, so renaming a document, changing its kind, or opening
it again is one more append rather than an edit. The log is compacted when it
grows past its bound, keeping the newest record for each id, written aside and
renamed exactly as the checkpoint log is.

What a truncated tail costs
---------------------------

One append. A new document's catalogue entry is written *before* any of its text
is, so the record that can be lost to a power cut is always the record for an
empty document. Losing the entry for a document that has words in it is not a
state this ordering can reach.
"""

from magwrite_transport.document_store import valid_id
from magwrite_transport.journal import JournalRecordError, escape, unescape
from magwrite_transport.protocol import crc32

MAGIC = "MWX1"
FIELDS = 8

# Titles are drawn on a 48-column panel, in a list that also carries a selection
# marker, so there is no use for a longer one and every reason not to store one.
MAX_TITLE_CHARS = 24
MAX_KIND_CHARS = 12
# Generous against the fields above; a corrupt length field must never make the
# reader allocate or scan without limit.
MAX_RECORD_BYTES = 256

# A bounded catalogue, because an unbounded one on a microcontroller is a bug
# that takes a few months to appear. Sixty-four documents is far more than the
# minimum standalone workflow needs and small enough that the whole catalogue is
# a few kilobytes held in RAM.
MAX_DOCUMENTS = 64
# Compact once the log holds appreciably more records than it has documents.
MAX_INDEX_RECORDS = 4 * MAX_DOCUMENTS

# The kinds a document can be. These are properties of the *document*, not of the
# menu item it was reached through: Drafts and Recent are ways of navigating to a
# document, and a note opened through Drafts is still a note. That distinction is
# what lets a restored session restore its mode -- the mode comes back with the
# document, because it belongs to the document.
KIND_JOURNAL = "JOURNAL"
KIND_NOTE = "NOTE"
KIND_DRAFT = "DRAFT"
KINDS = (KIND_JOURNAL, KIND_NOTE, KIND_DRAFT)

# What the panel draws for each kind. Separate from the identifiers for the same
# reason the save-state labels are: an identifier is not promised to be
# renderable, and the 3x5 glyph table is the whole alphabet this device has.
KIND_LABELS = {
    KIND_JOURNAL: "JOURNAL",
    KIND_NOTE: "NOTE",
    KIND_DRAFT: "DRAFT",
}
UNKNOWN_KIND_LABEL = "DOCUMENT"

INDEX_NAME = "index.log"
INDEX_PENDING_NAME = "index.new.log"


class CatalogueError(Exception):
    """A catalogue operation failed and the caller must be told, not shielded."""


class Entry:
    """One document in the catalogue."""

    __slots__ = ("document_id", "kind", "title", "opened")

    def __init__(self, document_id, kind, title, opened):
        self.document_id = document_id
        self.kind = kind
        self.title = title
        self.opened = opened

    @property
    def label(self):
        """The panel-renderable name for this document's kind."""
        return KIND_LABELS.get(self.kind, UNKNOWN_KIND_LABEL)

    def __eq__(self, other):
        if not isinstance(other, Entry):
            return NotImplemented
        return (
            self.document_id == other.document_id and self.kind == other.kind
            and self.title == other.title and self.opened == other.opened
        )

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return "Entry(id=%s, kind=%s, opened=%d, title=%r)" % (
            self.document_id, self.kind, self.opened, self.title,
        )

    def summary(self):
        return {
            "document_id": self.document_id, "kind": self.kind,
            "title": self.title, "opened": self.opened,
        }


def _printable(text, limit):
    if len(text) > limit:
        return False
    for character in text:
        if not 32 <= ord(character) <= 126:
            return False
    return True


def encode_entry(sequence, entry):
    """Return one complete, newline-terminated catalogue record."""
    if sequence < 0 or entry.opened < 0:
        raise JournalRecordError("catalogue counters must be non-negative")
    if not valid_id(entry.document_id):
        raise JournalRecordError("unusable document id: " + str(entry.document_id))
    # The kind and the id are unescaped fields, so a space in either would move
    # every field after it. Refusing here is what keeps the parser's field count
    # a real check rather than a hopeful one.
    if not entry.kind or " " in entry.kind or not _printable(
        entry.kind, MAX_KIND_CHARS
    ):
        raise JournalRecordError("unusable document kind: " + str(entry.kind))
    if not _printable(entry.title, MAX_TITLE_CHARS):
        raise JournalRecordError("unusable document title")
    escaped = escape(entry.title).encode("ascii")
    line = "%s %d %d %s %s %d %08X " % (
        MAGIC, sequence, entry.opened, entry.kind, entry.document_id,
        len(escaped), crc32(escaped),
    )
    record = line.encode("ascii") + escaped + b"\n"
    if len(record) > MAX_RECORD_BYTES:
        raise JournalRecordError("catalogue record exceeds the bounded size")
    return record


def decode_entry(line):
    """Return ``(sequence, Entry)`` for one complete record, or ``None``.

    ``None`` means the line is not a usable record. As in the recovery journal
    this never raises on bad input, because bad input is the expected case after
    a forced power loss.
    """
    if not line or len(line) > MAX_RECORD_BYTES:
        return None
    try:
        text = line.decode("ascii")
    except (UnicodeError, ValueError):
        return None
    parts = text.split(" ", FIELDS - 1)
    if len(parts) != FIELDS or parts[0] != MAGIC:
        return None
    try:
        sequence = int(parts[1])
        opened = int(parts[2])
        length = int(parts[5])
        expected_crc = int(parts[6], 16)
    except ValueError:
        return None
    kind = parts[3]
    document_id = parts[4]
    escaped = parts[7]
    encoded = escaped.encode("ascii")
    if len(encoded) != length or crc32(encoded) != expected_crc:
        return None
    try:
        title = unescape(escaped)
    except JournalRecordError:
        return None
    if sequence < 0 or opened < 0 or not valid_id(document_id):
        return None
    if not kind or not _printable(kind, MAX_KIND_CHARS):
        return None
    # A kind this build does not recognise is kept rather than discarded, and
    # drawn as DOCUMENT. Dropping the record would make somebody's document
    # disappear from their own device because a later build named it something
    # new, which is a far worse failure than an unfamiliar word on the panel.
    if not _printable(title, MAX_TITLE_CHARS):
        return None
    return sequence, Entry(document_id, kind, title, opened)


def scan(data):
    """Read every usable record from raw catalogue bytes.

    Returns ``(records, truncated_tail, rejected)`` with the same meanings the
    recovery journal's scanner gives them.
    """
    records = []
    rejected = 0
    truncated_tail = False
    if not data:
        return records, truncated_tail, rejected
    lines = data.split(b"\n")
    tail = lines.pop()
    if tail:
        truncated_tail = True
    for line in lines:
        if not line:
            continue
        decoded = decode_entry(line)
        if decoded is None:
            rejected += 1
            continue
        records.append(decoded)
    return records, truncated_tail, rejected


class DocumentIndex:
    """The catalogue on the card: which documents exist and which was open last.

    Uses the same injected backend contract :class:`~document_store.DocumentStore`
    does, so every branch here -- including a truncated tail and a failed
    compaction -- is exercised on CPython against a filesystem that can lose power
    at a chosen byte.
    """

    def __init__(self, backend, root, max_documents=MAX_DOCUMENTS,
                 max_records=MAX_INDEX_RECORDS):
        self.backend = backend
        self.root = root
        self.max_documents = max_documents
        self.max_records = max_records
        self.entries = {}
        self.sequence = 0
        self.opened_counter = 0
        self.records = 0
        self.appends = 0
        self.compactions = 0
        self.rejected_records = 0
        self.truncated_tail = False
        self.last_error = None
        self.loaded = False

    @property
    def path(self):
        return self.root + "/" + INDEX_NAME

    # ------------------------------------------------------------------- read

    def load(self):
        """Read the catalogue. Returns the number of documents found."""
        data = self._read(self.path)
        records, truncated, rejected = scan(data)
        self.entries = {}
        self.sequence = 0
        self.opened_counter = 0
        for sequence, entry in records:
            # File order is time order, so a later record simply replaces an
            # earlier one for the same id. That is how a rename, a kind change,
            # and a re-open are all one append rather than three operations.
            self.entries[entry.document_id] = entry
            if sequence >= self.sequence:
                self.sequence = sequence + 1
            if entry.opened >= self.opened_counter:
                self.opened_counter = entry.opened + 1
        self.records = len(records)
        self.truncated_tail = truncated
        self.rejected_records = rejected
        self.loaded = True
        return len(self.entries)

    # ---------------------------------------------------------------- queries

    def __len__(self):
        return len(self.entries)

    @property
    def full(self):
        return len(self.entries) >= self.max_documents

    def get(self, document_id):
        return self.entries.get(document_id)

    def ordered(self):
        """Every document, most recently opened first."""
        items = list(self.entries.values())
        # Insertion sort: the catalogue is bounded at 64 and CircuitPython's
        # sort with a key function is not something to rely on for a list of
        # objects. Small, explicit, and total.
        for index in range(1, len(items)):
            current = items[index]
            position = index - 1
            while position >= 0 and items[position].opened < current.opened:
                items[position + 1] = items[position]
                position -= 1
            items[position + 1] = current
        return tuple(items)

    def active(self):
        """The document with the highest open ordinal, or ``None``."""
        best = None
        for entry in self.entries.values():
            if best is None or entry.opened > best.opened:
                best = entry
        return best

    def newest_of_kind(self, kind):
        """The most recently opened document of ``kind``, or ``None``."""
        best = None
        for entry in self.entries.values():
            if entry.kind != kind:
                continue
            if best is None or entry.opened > best.opened:
                best = entry
        return best

    def next_id(self, prefix):
        """Return an unused id beginning with ``prefix``.

        Bounded rather than clever: it counts up from one and stops at the
        catalogue bound, so it terminates whatever the card holds.
        """
        for number in range(1, self.max_documents * 2 + 2):
            candidate = "%s%04d" % (prefix, number)
            if candidate not in self.entries:
                return candidate
        return None

    # ----------------------------------------------------------------- writes

    def record(self, document_id, kind, title, opened=None):
        """Append one catalogue record and adopt it. Returns the ``Entry``.

        Refusals are explicit and returned as ``None`` with ``last_error`` set,
        never raised: a catalogue that cannot be written must cost the writer
        their ordering, never their session.
        """
        if not self.loaded:
            raise CatalogueError("catalogue used before load()")
        if document_id not in self.entries and self.full:
            self.last_error = (
                "the card already holds the maximum of %d documents"
                % self.max_documents
            )
            return None
        if opened is None:
            opened = self.opened_counter
        entry = Entry(document_id, kind, title, opened)
        try:
            record = encode_entry(self.sequence, entry)
        except JournalRecordError as error:
            self.last_error = "catalogue record refused: " + str(error)
            return None
        try:
            self.backend.append(self.path, record)
        except OSError as error:
            self.last_error = "catalogue append failed: " + str(error)
            return None
        self.sequence += 1
        if opened >= self.opened_counter:
            self.opened_counter = opened + 1
        self.entries[document_id] = entry
        self.records += 1
        self.appends += 1
        self.last_error = None
        self._compact()
        return entry

    def touch(self, document_id):
        """Record ``document_id`` as the one just opened. Returns the ``Entry``.

        This is what makes Recent work and what makes the active document
        survive a power cut: opening a document is an append, so the ordering on
        the card is updated before a single character is typed into it.
        """
        entry = self.entries.get(document_id)
        if entry is None:
            self.last_error = "unknown document: " + str(document_id)
            return None
        return self.record(document_id, entry.kind, entry.title)

    def _compact(self):
        """Keep the log bounded, keeping the newest record for each document."""
        if self.records <= self.max_records:
            return False
        kept = self.ordered()
        rebuilt = b""
        sequence = 0
        # Written oldest-first so that file order still means time order in the
        # rebuilt log, which is what the reader relies on.
        for entry in reversed(kept):
            try:
                rebuilt += encode_entry(sequence, entry)
            except JournalRecordError as error:
                self.last_error = "catalogue compaction refused: " + str(error)
                return False
            sequence += 1
        pending = self.root + "/" + INDEX_PENDING_NAME
        try:
            # Written aside and renamed, so an interrupted compaction leaves the
            # existing catalogue untouched rather than half-rewritten.
            self.backend.write(pending, rebuilt)
            self.backend.remove(self.path)
            self.backend.rename(pending, self.path)
        except OSError as error:
            self.last_error = "catalogue compaction failed: " + str(error)
            return False
        self.sequence = sequence
        self.records = len(kept)
        self.compactions += 1
        return True

    # ----------------------------------------------------------------- detail

    def _read(self, path):
        try:
            return self.backend.read(path)
        except OSError as error:
            self.last_error = "catalogue read failed: " + str(error)
            return None

    def summary(self):
        active = self.active()
        return {
            "documents": len(self.entries),
            "index_records": self.records,
            "index_appends": self.appends,
            "index_compactions": self.compactions,
            "index_rejected_records": self.rejected_records,
            "index_truncated_final_record": self.truncated_tail,
            "index_last_error": self.last_error,
            "active_document": None if active is None else active.document_id,
        }
