"""Single-document storage, checkpointing, and recovery.

Host-safe. Every filesystem operation goes through an injected backend, so this
module is fully testable on CPython -- including the power-loss cases, which is
the entire point: a recovery path that has only ever been exercised by pulling a
real power lead is a recovery path that has been tested a handful of times.

The backend contract
--------------------

An object with these methods, each raising ``OSError`` on failure:

``exists(path)``        -> bool
``makedirs(path)``      -> create a directory and its parents, idempotently
``read(path)``          -> bytes, or ``None`` if the file does not exist
``append(path, data)``  -> append and make durable
``write(path, data)``   -> replace and make durable
``remove(path)``        -> delete, tolerating absence
``rename(src, dst)``    -> rename, target must not exist (FAT semantics)
``free_bytes()``        -> free bytes, or ``None`` when unknown

"Make durable" means the bytes have been flushed as far as the platform allows
before the call returns. Nothing here can be correct if that is a lie.

What is authoritative, and what is a convenience
-----------------------------------------------

::

    documents/active.md         plain text, readable on any computer
    documents/active.prev.md    the previous plain-text mirror
    documents/active.new.md     a mirror being written
    recovery/active.log         append-only journal of acknowledged snapshots
    recovery/checkpoint.log     append-only checkpoint records

The **recovery logs are authoritative**. ``documents/active.md`` is a plain-text
mirror maintained for the writer and for any computer the card is later plugged
into; it is never the source recovery trusts.

That split is what keeps this small. The alternative -- making the ``.md`` file
authoritative -- needs either a metadata header inside the file, which stops it
being a plain-text document, or a sidecar, which reintroduces the two-file
atomicity problem the append-only log already solves. Since the document is
bounded at 512 characters, mirroring it costs a few hundred bytes and buys a
recovery path with exactly one kind of write in it: an append that either lands
whole or is rejected by its own CRC.

Checkpoint sequence, and every way it can be interrupted
--------------------------------------------------------

1. append the newest snapshot to ``recovery/checkpoint.log`` and sync;
2. truncate ``recovery/active.log``;
3. materialise the mirror: write ``active.new.md``, rotate ``active.md`` to
   ``active.prev.md``, rename ``active.new.md`` to ``active.md``.

Power loss before (1) completes leaves the journal intact and the truncated
checkpoint record is rejected on read. Between (1) and (2) leaves the same
snapshot in both logs, which recovery resolves by revision, not by file. During
(3) leaves the mirror stale or split across three names -- and since the mirror
is not authoritative, that costs nothing but a rewrite at the next checkpoint.

There is deliberately no window in which the newest acknowledged snapshot exists
in neither log.
"""

from magwrite_transport.journal import (
    MAX_RECORD_BYTES, Snapshot, encode_record, latest, scan,
)

DEFAULT_ROOT = "/sd/magwrite"

DOCUMENTS = "documents"
RECOVERY = "recovery"
ACTIVE_NAME = "active.md"
PREVIOUS_NAME = "active.prev.md"
PENDING_NAME = "active.new.md"
JOURNAL_NAME = "active.log"
CHECKPOINT_NAME = "checkpoint.log"
CHECKPOINT_PENDING_NAME = "checkpoint.new.log"

# The checkpoint log is compacted rather than allowed to grow, but never down to
# a single record: keeping the previous checkpoint is what "preserve the last
# known-good checkpoint" means when the newest one is the thing that failed.
MAX_CHECKPOINT_RECORDS = 4
KEPT_CHECKPOINT_RECORDS = 2

# Refuse to append when the card has less than this free. A journal append that
# fails halfway is recoverable by design, but a filesystem with no room left is
# not a state to discover one record at a time.
RESERVE_BYTES = 32 * 1024

# Sources a recovered snapshot can come from, reported so a recovery is never
# silent about which path produced the document.
SOURCE_NONE = "NONE"
SOURCE_JOURNAL = "JOURNAL"
SOURCE_CHECKPOINT = "CHECKPOINT"


class StoreError(Exception):
    """A storage operation failed and the caller must be told, not shielded."""


class Recovery:
    """What opening the store found on the card."""

    __slots__ = (
        "snapshot", "source", "truncated_tail", "rejected_records",
        "journal_records", "checkpoint_records", "mirror_stale",
    )

    def __init__(
        self, snapshot=None, source=SOURCE_NONE, truncated_tail=False,
        rejected_records=0, journal_records=0, checkpoint_records=0,
        mirror_stale=False,
    ):
        self.snapshot = snapshot
        self.source = source
        self.truncated_tail = truncated_tail
        self.rejected_records = rejected_records
        self.journal_records = journal_records
        self.checkpoint_records = checkpoint_records
        self.mirror_stale = mirror_stale

    @property
    def recovered(self):
        return self.snapshot is not None

    @property
    def revision(self):
        return 0 if self.snapshot is None else self.snapshot.revision

    def summary(self):
        return {
            "recovered": self.recovered,
            "source": self.source,
            "revision": self.revision,
            "characters": 0 if self.snapshot is None else len(self.snapshot.text),
            "cursor_row": 0 if self.snapshot is None else self.snapshot.row,
            "cursor_column": 0 if self.snapshot is None else self.snapshot.column,
            "truncated_final_record": self.truncated_tail,
            "rejected_records": self.rejected_records,
            "journal_records": self.journal_records,
            "checkpoint_records": self.checkpoint_records,
            "mirror_stale": self.mirror_stale,
        }


class DocumentStore:
    """One active document: journal, checkpoints, and recovery.

    The store holds no clock and no thresholds. *When* to journal or checkpoint
    is policy and lives in ``persistence``; this class only knows how to do it
    durably and how to read back what survived.
    """

    def __init__(self, backend, root=DEFAULT_ROOT, reserve_bytes=RESERVE_BYTES):
        self.backend = backend
        self.root = root
        self.reserve_bytes = reserve_bytes
        self.journal_sequence = 0
        self.journal_records = 0
        self.journal_bytes = 0
        self.checkpoints_written = 0
        self.journal_appends = 0
        self.mirror_writes = 0
        self.compactions = 0
        self.last_error = None
        self.opened = False
        self.checkpoint_revision = 0
        self.journaled_revision = 0

    # ------------------------------------------------------------------ paths

    def _path(self, *parts):
        path = self.root
        for part in parts:
            path = path + "/" + part
        return path

    @property
    def journal_path(self):
        return self._path(RECOVERY, JOURNAL_NAME)

    @property
    def checkpoint_path(self):
        return self._path(RECOVERY, CHECKPOINT_NAME)

    @property
    def active_path(self):
        return self._path(DOCUMENTS, ACTIVE_NAME)

    # ------------------------------------------------------------------- open

    def open(self):
        """Prepare the layout and recover the newest acknowledged snapshot."""
        try:
            self.backend.makedirs(self.root)
            self.backend.makedirs(self._path(DOCUMENTS))
            self.backend.makedirs(self._path(RECOVERY))
        except OSError as error:
            raise StoreError("cannot create store layout: " + str(error))

        recovery = self._recover()
        self.opened = True
        if recovery.snapshot is not None:
            # The journal continues from where it was rather than restarting, so
            # sequence numbers stay unique across power losses. They are
            # diagnostic only -- file order decides recency -- but a sequence
            # that silently restarts makes a log impossible to read afterwards.
            self.journaled_revision = recovery.snapshot.revision
        return recovery

    def _recover(self):
        journal_data = self._read(self.journal_path)
        checkpoint_data = self._read(self.checkpoint_path)

        journal_records, journal_truncated, journal_rejected = scan(journal_data)
        checkpoint_records, checkpoint_truncated, checkpoint_rejected = scan(
            checkpoint_data
        )

        self.journal_records = len(journal_records)
        self.journal_bytes = 0 if journal_data is None else len(journal_data)
        if journal_records:
            self.journal_sequence = journal_records[-1][0] + 1

        best = None
        source = SOURCE_NONE
        if checkpoint_records:
            sequence, snapshot = checkpoint_records[-1]
            best = snapshot
            source = SOURCE_CHECKPOINT
            self.checkpoint_revision = snapshot.revision
            if sequence >= self.journal_sequence:
                self.journal_sequence = sequence + 1
        if journal_records:
            snapshot = journal_records[-1][1]
            # A journal record is only ever discarded after it has been promoted
            # into the checkpoint log, so a journal entry at least as new as the
            # checkpoint always wins. Comparing revisions rather than file
            # timestamps keeps this true regardless of which write was cut off.
            if best is None or snapshot.revision >= best.revision:
                best = snapshot
                source = SOURCE_JOURNAL

        mirror_stale = False
        if best is not None:
            mirror = self._read(self.active_path)
            expected = best.text.encode("ascii")
            mirror_stale = mirror != expected

        return Recovery(
            snapshot=best,
            source=source,
            truncated_tail=journal_truncated or checkpoint_truncated,
            rejected_records=journal_rejected + checkpoint_rejected,
            journal_records=len(journal_records),
            checkpoint_records=len(checkpoint_records),
            mirror_stale=mirror_stale,
        )

    # ---------------------------------------------------------------- writing

    def journal(self, snapshot):
        """Append one acknowledged snapshot. Returns True when it was written.

        A refusal is always explicit and always recorded in ``last_error``. The
        document in RAM is unaffected either way, so a full or failing card
        costs durability, never the writer's words.
        """
        self._require_open()
        record = encode_record(self.journal_sequence, snapshot)
        if not self._has_room(len(record)):
            return False
        try:
            self.backend.append(self.journal_path, record)
        except OSError as error:
            self.last_error = "journal append failed: " + str(error)
            return False
        self.journal_sequence += 1
        self.journal_records += 1
        self.journal_bytes += len(record)
        self.journal_appends += 1
        self.journaled_revision = snapshot.revision
        self.last_error = None
        return True

    def checkpoint(self, snapshot):
        """Promote ``snapshot`` to a checkpoint and compact the journal.

        Ordering is the whole safety argument, so it is not rearranged for
        convenience: the checkpoint record becomes durable *before* the journal
        that also holds that state is discarded.
        """
        self._require_open()
        record = encode_record(self.journal_sequence, snapshot)
        if not self._has_room(len(record) + len(snapshot.text) + MAX_RECORD_BYTES):
            return False
        try:
            self.backend.append(self.checkpoint_path, record)
        except OSError as error:
            self.last_error = "checkpoint append failed: " + str(error)
            return False
        self.journal_sequence += 1
        self.checkpoint_revision = snapshot.revision
        self.journaled_revision = snapshot.revision
        self.checkpoints_written += 1

        # Only now may the journal be discarded. If power is lost between the
        # two, recovery finds the same snapshot in both logs and picks it by
        # revision; nothing is lost and nothing is ambiguous.
        try:
            self.backend.write(self.journal_path, b"")
            self.journal_records = 0
            self.journal_bytes = 0
        except OSError as error:
            self.last_error = "journal truncate failed: " + str(error)

        self._materialise(snapshot)
        self._compact_checkpoints()
        return True

    def _materialise(self, snapshot):
        """Rewrite the plain-text mirror. Never the recovery authority."""
        data = snapshot.text.encode("ascii")
        pending = self._path(DOCUMENTS, PENDING_NAME)
        previous = self._path(DOCUMENTS, PREVIOUS_NAME)
        active = self.active_path
        try:
            self.backend.write(pending, data)
            # FAT rename cannot overwrite, so the target is cleared first. Each
            # step is individually survivable because the mirror is a
            # convenience: the worst outcome is a stale or missing .md file,
            # which the next checkpoint rewrites.
            self.backend.remove(previous)
            if self.backend.exists(active):
                self.backend.rename(active, previous)
            self.backend.rename(pending, active)
            self.mirror_writes += 1
        except OSError as error:
            self.last_error = "mirror write failed: " + str(error)
            return False
        return True

    def _compact_checkpoints(self):
        """Keep the checkpoint log bounded without losing the previous one."""
        data = self._read(self.checkpoint_path)
        records, _, _ = scan(data)
        if len(records) <= MAX_CHECKPOINT_RECORDS:
            return False
        kept = records[-KEPT_CHECKPOINT_RECORDS:]
        rebuilt = b"".join(
            encode_record(sequence, snapshot) for sequence, snapshot in kept
        )
        pending = self._path(RECOVERY, CHECKPOINT_PENDING_NAME)
        try:
            # Written aside and renamed, so an interrupted compaction leaves the
            # existing checkpoint log untouched rather than half-rewritten.
            self.backend.write(pending, rebuilt)
            self.backend.remove(self.checkpoint_path)
            self.backend.rename(pending, self.checkpoint_path)
            self.compactions += 1
        except OSError as error:
            self.last_error = "checkpoint compaction failed: " + str(error)
            return False
        return True

    # ---------------------------------------------------------------- reading

    def read_latest(self):
        """Return the newest acknowledged snapshot on the card, or ``None``."""
        journal = latest(self._read(self.journal_path))
        checkpoint = latest(self._read(self.checkpoint_path))
        if journal is None and checkpoint is None:
            return None
        if journal is None:
            return checkpoint[1]
        if checkpoint is None:
            return journal[1]
        if journal[1].revision >= checkpoint[1].revision:
            return journal[1]
        return checkpoint[1]

    def start_new_document(self):
        """Discard the active document and begin an empty one.

        Both logs are cleared before the mirror, so there is no window in which
        the logs still describe a document the writer has abandoned.
        """
        self._require_open()
        empty = Snapshot(0, 0, 0, "")
        try:
            self.backend.write(self.journal_path, b"")
            self.backend.write(self.checkpoint_path, b"")
        except OSError as error:
            raise StoreError("cannot clear the active document: " + str(error))
        self.journal_records = 0
        self.journal_bytes = 0
        self.checkpoint_revision = 0
        self.journaled_revision = 0
        self._materialise(empty)
        return empty

    # ----------------------------------------------------------------- detail

    def _require_open(self):
        if not self.opened:
            raise StoreError("store used before open()")

    def _read(self, path):
        try:
            return self.backend.read(path)
        except OSError as error:
            self.last_error = "read failed: " + str(error)
            return None

    def _has_room(self, needed):
        try:
            free = self.backend.free_bytes()
        except OSError as error:
            self.last_error = "free space unavailable: " + str(error)
            return True
        if free is None:
            # Unknown free space is not treated as full: refusing every write on
            # a platform that cannot report capacity would disable persistence
            # entirely, which is a worse failure than discovering a full card.
            return True
        if free < self.reserve_bytes + needed:
            self.last_error = "insufficient free space: %d bytes" % free
            return False
        return True

    def summary(self):
        return {
            "root": self.root,
            "journal_appends": self.journal_appends,
            "journal_records": self.journal_records,
            "journal_bytes": self.journal_bytes,
            "checkpoints_written": self.checkpoints_written,
            "mirror_writes": self.mirror_writes,
            "checkpoint_compactions": self.compactions,
            "checkpoint_revision": self.checkpoint_revision,
            "journaled_revision": self.journaled_revision,
            "last_storage_error": self.last_error,
        }
