"""Recovery journal records: round-trip, corruption, and truncation.

The record format carries one obligation above all others -- a record that was
cut short by power loss must never be mistaken for a complete one -- so these
tests attack it from both directions. They prove a well-formed record survives,
and they prove each of the three independent truncation and corruption defences
actually fires on its own.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from magwrite_transport import journal
from magwrite_transport.journal import (
    JournalRecordError, Snapshot, decode_record, encode_record, escape, latest,
    scan, unescape,
)
from magwrite_transport.protocol import crc32


class EscapingTests(unittest.TestCase):
    """A document must survive being flattened onto one line."""

    def test_a_single_line_is_unchanged(self):
        self.assertEqual(escape("hello world"), "hello world")

    def test_line_breaks_become_escapes(self):
        self.assertEqual(escape("a\nb\nc"), "a\\nb\\nc")

    def test_backslashes_are_doubled(self):
        self.assertEqual(escape("a\\b"), "a\\\\b")

    def test_round_trip_over_every_character_the_editor_admits(self):
        text = "".join(chr(code) for code in range(32, 127))
        document = text + "\n" + text + "\n"
        self.assertEqual(unescape(escape(document)), document)

    def test_a_literal_backslash_n_is_not_confused_with_a_line_break(self):
        # The naive inverse -- two ``replace`` calls -- fails exactly here, by
        # turning an escaped backslash followed by "n" into a real newline.
        original = "a\\nb"
        self.assertNotIn("\n", original)
        self.assertEqual(unescape(escape(original)), original)

    def test_a_trailing_lone_backslash_is_refused(self):
        with self.assertRaises(JournalRecordError):
            unescape("abc\\")

    def test_an_unknown_escape_is_refused(self):
        with self.assertRaises(JournalRecordError):
            unescape("a\\qb")


class RecordRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = Snapshot(17, 2, 5, "first line\nsecond line")

    def test_a_record_round_trips_completely(self):
        sequence, decoded = decode_record(encode_record(4, self.snapshot)[:-1])
        self.assertEqual(sequence, 4)
        self.assertEqual(decoded, self.snapshot)

    def test_a_record_is_one_newline_terminated_line(self):
        record = encode_record(0, self.snapshot)
        self.assertTrue(record.endswith(b"\n"))
        self.assertEqual(record.count(b"\n"), 1)

    def test_an_empty_document_round_trips(self):
        empty = Snapshot(0, 0, 0, "")
        _, decoded = decode_record(encode_record(0, empty)[:-1])
        self.assertEqual(decoded, empty)

    def test_the_largest_document_the_editor_allows_fits_a_bounded_record(self):
        from magwrite_transport.editor import MAX_DOCUMENT_CHARS
        # Worst case for the escaped form: every character a backslash.
        text = "\\" * MAX_DOCUMENT_CHARS
        record = encode_record(999999, Snapshot(999999, 0, 0, text))
        self.assertLessEqual(len(record), journal.MAX_RECORD_BYTES)

    def test_a_negative_sequence_or_revision_is_refused_at_encode(self):
        with self.assertRaises(JournalRecordError):
            encode_record(-1, self.snapshot)
        with self.assertRaises(JournalRecordError):
            Snapshot(-1, 0, 0, "")


class CorruptRecordTests(unittest.TestCase):
    """Every defence is proved to fire on its own."""

    def setUp(self):
        self.line = encode_record(3, Snapshot(9, 1, 2, "hello\nthere"))[:-1]
        self.assertIsNotNone(decode_record(self.line))

    def test_a_truncated_record_is_rejected(self):
        for cut in range(1, len(self.line)):
            self.assertIsNone(decode_record(self.line[:cut]), cut)

    def test_a_corrupted_payload_byte_is_rejected_by_the_crc(self):
        data = bytearray(self.line)
        data[-1] = data[-1] ^ 0xFF
        self.assertIsNone(decode_record(bytes(data)))

    def test_a_wrong_length_field_is_rejected_even_with_a_valid_crc(self):
        escaped = b"hello"
        line = ("MWJ1 1 1 0 0 99 %08X " % crc32(escaped)).encode("ascii") + escaped
        self.assertIsNone(decode_record(line))

    def test_a_wrong_magic_is_rejected(self):
        self.assertIsNone(decode_record(b"XXXX" + self.line[4:]))

    def test_a_non_numeric_header_field_is_rejected(self):
        escaped = b"hi"
        line = ("MWJ1 x 1 0 0 2 %08X " % crc32(escaped)).encode("ascii") + escaped
        self.assertIsNone(decode_record(line))

    def test_an_oversized_line_is_rejected_without_being_parsed(self):
        self.assertIsNone(decode_record(b"M" * (journal.MAX_RECORD_BYTES + 1)))

    def test_an_empty_line_is_rejected(self):
        self.assertIsNone(decode_record(b""))

    def test_non_ascii_bytes_are_rejected(self):
        self.assertIsNone(decode_record(b"MWJ1 1 1 0 0 1 00000000 \xff"))

    def test_decoding_never_raises_on_arbitrary_bytes(self):
        # Bad input is the *expected* case after a power loss, so the decoder has
        # to answer rather than throw.
        for candidate in (b"\x00", b"MWJ1", b"MWJ1 ", b"MWJ1 1 1 1 1 1 1 1 1",
                          b"MWJ1 1 1 0 0 4 zzzz abcd", b"\n", b" "):
            self.assertIsNone(decode_record(candidate), candidate)


class ScanTests(unittest.TestCase):
    def journal_bytes(self, count):
        return b"".join(
            encode_record(index, Snapshot(index + 1, 0, 0, "rev %d" % index))
            for index in range(count)
        )

    def test_an_empty_journal_yields_nothing(self):
        self.assertEqual(scan(b""), ([], False, 0))
        self.assertEqual(scan(None), ([], False, 0))
        self.assertIsNone(latest(b""))

    def test_every_complete_record_is_read_in_file_order(self):
        records, truncated, rejected = scan(self.journal_bytes(5))
        self.assertEqual([sequence for sequence, _ in records], [0, 1, 2, 3, 4])
        self.assertFalse(truncated)
        self.assertEqual(rejected, 0)

    def test_a_truncated_final_record_is_reported_and_dropped(self):
        """The V1.2 requirement, stated as directly as it can be."""
        data = self.journal_bytes(4)
        for lost in range(1, 20):
            records, truncated, rejected = scan(data[:-lost])
            self.assertTrue(truncated, lost)
            # The three intact records survive; the fourth does not.
            self.assertEqual(len(records), 3, lost)
            self.assertEqual(rejected, 0, lost)
            self.assertEqual(latest(data[:-lost])[1].revision, 3, lost)

    def test_a_journal_cut_at_exactly_a_record_boundary_is_not_truncated(self):
        data = self.journal_bytes(4)
        complete = data[: data.index(b"\n") + 1]
        records, truncated, rejected = scan(complete)
        self.assertFalse(truncated)
        self.assertEqual(len(records), 1)

    def test_a_corrupt_record_in_the_middle_is_counted_not_fatal(self):
        records = [
            encode_record(0, Snapshot(1, 0, 0, "one")),
            b"MWJ1 1 2 0 0 3 DEADBEEF two\n",
            encode_record(2, Snapshot(3, 0, 0, "three")),
        ]
        found, truncated, rejected = scan(b"".join(records))
        self.assertEqual(rejected, 1)
        self.assertFalse(truncated)
        self.assertEqual([sequence for sequence, _ in found], [0, 2])

    def test_latest_is_file_order_not_the_highest_sequence_field(self):
        """A corrupt header must not let a stale document outrank a newer one."""
        data = (
            encode_record(500, Snapshot(2, 0, 0, "stale but high sequence"))
            + encode_record(1, Snapshot(9, 0, 0, "newest"))
        )
        self.assertEqual(latest(data)[1].text, "newest")

    def test_a_journal_whose_only_record_is_truncated_recovers_nothing(self):
        data = encode_record(0, Snapshot(1, 0, 0, "only"))[:-3]
        records, truncated, _ = scan(data)
        self.assertTrue(truncated)
        self.assertEqual(records, [])
        self.assertIsNone(latest(data))


class SnapshotTests(unittest.TestCase):
    def test_equality_covers_every_field(self):
        base = Snapshot(1, 2, 3, "text")
        self.assertEqual(base, Snapshot(1, 2, 3, "text"))
        for other in (
            Snapshot(2, 2, 3, "text"), Snapshot(1, 9, 3, "text"),
            Snapshot(1, 2, 9, "text"), Snapshot(1, 2, 3, "other"),
        ):
            self.assertNotEqual(base, other)

    def test_a_snapshot_is_not_equal_to_an_unrelated_object(self):
        self.assertNotEqual(Snapshot(1, 0, 0, ""), "Snapshot")

    def test_the_repr_does_not_dump_the_document(self):
        # Diagnostics are bounded everywhere else in this codebase; a snapshot
        # repr that printed 512 characters into a log would not be.
        text = "secret " * 20
        self.assertNotIn("secret", repr(Snapshot(1, 0, 0, text)))


if __name__ == "__main__":
    unittest.main()
