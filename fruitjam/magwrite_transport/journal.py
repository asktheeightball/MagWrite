"""Append-only recovery journal records for one document.

Host-safe. This module knows how to turn an editor snapshot into one line of
bytes and back, and nothing else: no filesystem, no policy, no clock.

Why full snapshots rather than deltas
-------------------------------------

A delta journal would have to record editor *operations* and replay them, which
means a second implementation of what BACKSPACE, ENTER, and a refused edit mean.
Two models of editor semantics that must agree forever is the standard way a
recovery format ends up unable to reproduce the document it recorded.

The authoritative document is bounded at ``MAX_DOCUMENT_CHARS`` (512), so a full
snapshot costs at most a few hundred bytes. Recovery is then "keep the last
record that validates", which needs no replay engine and no agreement with the
editor beyond the text itself.

Record layout
-------------

One record is one line::

    MWJ1 <seq> <revision> <row> <column> <length> <crc8hex> <escaped-text>\\n

``length`` is the byte length of the escaped text and ``crc8hex`` is its CRC-32,
so a record that was cut short by power loss fails in three independent ways:

* the line has no terminating newline;
* the escaped text is shorter than ``length``;
* the CRC does not match.

Any one of those is enough to reject the record. The first is what a truncated
*final* record actually looks like on a FAT filesystem, and it is checked before
parsing so a half-written line is never even split into fields.

Escaping
--------

The editor admits printable ASCII 32..126 plus the line breaks it inserts
itself, so exactly two characters need escaping to keep a record on one line:
backslash and newline. That makes the transform total and reversible without
importing anything.
"""

from magwrite_transport.protocol import crc32

MAGIC = "MWJ1"
FIELDS = 8
# A record is at most the escaped worst case: every one of 512 characters a
# backslash, doubled, plus the header. The bound exists so a corrupt length
# field can never make the reader allocate or scan without limit.
MAX_RECORD_BYTES = 1200


class JournalRecordError(Exception):
    """A record could not be encoded; records are never written half-formed."""


class Snapshot:
    """One acknowledged editor state: text, cursor, and the revision it is."""

    __slots__ = ("revision", "row", "column", "text")

    def __init__(self, revision, row, column, text):
        if revision < 0 or row < 0 or column < 0:
            raise JournalRecordError("snapshot fields must be non-negative")
        self.revision = revision
        self.row = row
        self.column = column
        self.text = text

    def __eq__(self, other):
        if not isinstance(other, Snapshot):
            return NotImplemented
        return (
            self.revision == other.revision and self.row == other.row
            and self.column == other.column and self.text == other.text
        )

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return "Snapshot(revision=%d, row=%d, column=%d, chars=%d)" % (
            self.revision, self.row, self.column, len(self.text),
        )


def escape(text):
    """Collapse a multiline document onto one line, reversibly."""
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def unescape(text):
    """Invert :func:`escape`.

    Scanned left to right rather than by two ``replace`` calls, because the
    naive inverse turns the escaped form of a literal backslash-n into a real
    line break.
    """
    out = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= length:
            raise JournalRecordError("record ends inside an escape")
        following = text[index + 1]
        if following == "n":
            out.append("\n")
        elif following == "\\":
            out.append("\\")
        else:
            raise JournalRecordError("unknown escape: \\" + following)
        index += 2
    return "".join(out)


def encode_record(sequence, snapshot):
    """Return one complete, newline-terminated record for ``snapshot``."""
    if sequence < 0:
        raise JournalRecordError("record sequence must be non-negative")
    escaped = escape(snapshot.text).encode("ascii")
    line = "%s %d %d %d %d %d %08X " % (
        MAGIC, sequence, snapshot.revision, snapshot.row, snapshot.column,
        len(escaped), crc32(escaped),
    )
    record = line.encode("ascii") + escaped + b"\n"
    if len(record) > MAX_RECORD_BYTES:
        raise JournalRecordError("record exceeds the bounded record size")
    return record


def decode_record(line):
    """Return ``(sequence, Snapshot)`` for one complete record, or ``None``.

    ``None`` means the line is not a usable record: truncated, corrupt, or
    written by a format this build does not know. The caller decides what that
    means; this function never raises on bad input, because bad input is the
    expected case after a forced power loss.
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
        revision = int(parts[2])
        row = int(parts[3])
        column = int(parts[4])
        length = int(parts[5])
        expected_crc = int(parts[6], 16)
    except ValueError:
        return None
    escaped = parts[7]
    encoded = escaped.encode("ascii")
    # The length check is what catches a record whose tail was lost but whose
    # header survived; the CRC catches one whose bytes were corrupted in place.
    if len(encoded) != length or crc32(encoded) != expected_crc:
        return None
    try:
        body = unescape(escaped)
    except JournalRecordError:
        return None
    if sequence < 0 or revision < 0 or row < 0 or column < 0:
        return None
    return sequence, Snapshot(revision, row, column, body)


def scan(data):
    """Read every usable record from raw journal bytes.

    Returns ``(records, truncated_tail, rejected)`` where ``records`` is the list
    of ``(sequence, Snapshot)`` pairs in file order, ``truncated_tail`` is True
    when the file ended mid-record, and ``rejected`` counts complete lines that
    did not validate.

    A truncated tail is normal: it is what an interrupted append looks like, and
    it means the writer died before that state was durable. Dropping it is
    correct, not lossy -- the previous record is the last state that was ever
    promised to be recoverable.
    """
    records = []
    rejected = 0
    truncated_tail = False
    if not data:
        return records, truncated_tail, rejected
    lines = data.split(b"\n")
    # ``split`` leaves the text after the final newline as the last element. If
    # that is non-empty the file did not end on a record boundary.
    tail = lines.pop()
    if tail:
        truncated_tail = True
    for line in lines:
        if not line:
            continue
        decoded = decode_record(line)
        if decoded is None:
            rejected += 1
            continue
        records.append(decoded)
    return records, truncated_tail, rejected


def latest(data):
    """Return the newest usable ``(sequence, Snapshot)``, or ``None``.

    "Newest" is the last record in file order that validates, not the highest
    sequence number. The journal is append-only, so file order *is* time order,
    and trusting a sequence field over the file's own structure would let one
    corrupt header resurrect a stale document.
    """
    records, _, _ = scan(data)
    if not records:
        return None
    return records[-1]
