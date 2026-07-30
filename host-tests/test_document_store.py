"""Single-document storage and recovery, including forced power loss.

The V1.2 exit condition is that a writing session survives forced power loss with
the final acknowledged edit recovered. That is a claim about interruption, so the
tests here interrupt: :class:`FakeFileSystem` cuts power at a chosen byte offset
of a chosen write, the volume is then re-opened exactly as the board would
re-open it after reset, and the recovered document is compared against the last
state that was ever promised to be durable.

The checkpoint sequence has three windows a power loss can land in, and each one
gets its own test. None of them may lose the newest acknowledged snapshot.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from fake_filesystem import FakeFileSystem, PowerCut
from magwrite_transport import document_store
from magwrite_transport.document_store import (
    DocumentStore, SOURCE_CHECKPOINT, SOURCE_JOURNAL, SOURCE_NONE, StoreError,
)
from magwrite_transport.journal import Snapshot

ROOT_PATH = "/sd/magwrite"


def opened(filesystem=None, **kwargs):
    filesystem = filesystem or FakeFileSystem()
    store = DocumentStore(filesystem, root=ROOT_PATH, **kwargs)
    recovery = store.open()
    return store, filesystem, recovery


class LayoutTests(unittest.TestCase):
    def test_opening_a_blank_card_creates_the_layout_and_recovers_nothing(self):
        store, filesystem, recovery = opened()
        self.assertFalse(recovery.recovered)
        self.assertEqual(recovery.source, SOURCE_NONE)
        self.assertEqual(recovery.revision, 0)
        for path in (ROOT_PATH, ROOT_PATH + "/documents", ROOT_PATH + "/recovery"):
            self.assertTrue(filesystem.exists(path), path)

    def test_a_store_refuses_to_be_used_before_open(self):
        store = DocumentStore(FakeFileSystem(), root=ROOT_PATH)
        with self.assertRaises(StoreError):
            store.journal(Snapshot(1, 0, 0, "x"))
        with self.assertRaises(StoreError):
            store.checkpoint(Snapshot(1, 0, 0, "x"))

    def test_an_unusable_card_fails_open_explicitly(self):
        filesystem = FakeFileSystem()
        original = filesystem.makedirs

        def refuse(path):
            raise OSError("read-only filesystem")

        filesystem.makedirs = refuse
        with self.assertRaises(StoreError):
            DocumentStore(filesystem, root=ROOT_PATH).open()
        filesystem.makedirs = original


class JournalTests(unittest.TestCase):
    def test_an_acknowledged_snapshot_is_readable_immediately(self):
        store, _, _ = opened()
        self.assertTrue(store.journal(Snapshot(1, 0, 3, "abc")))
        self.assertEqual(store.read_latest(), Snapshot(1, 0, 3, "abc"))
        self.assertEqual(store.journaled_revision, 1)

    def test_successive_snapshots_append_rather_than_replace(self):
        store, filesystem, _ = opened()
        for revision in range(1, 6):
            store.journal(Snapshot(revision, 0, revision, "a" * revision))
        self.assertEqual(store.journal_records, 5)
        self.assertEqual(filesystem.read(store.journal_path).count(b"\n"), 5)
        self.assertEqual(store.read_latest().text, "aaaaa")

    def test_journal_sequence_numbers_stay_unique_across_a_reopen(self):
        store, filesystem, _ = opened()
        store.journal(Snapshot(1, 0, 0, "one"))
        store.journal(Snapshot(2, 0, 0, "two"))
        reopened = DocumentStore(filesystem, root=ROOT_PATH)
        reopened.open()
        self.assertEqual(reopened.journal_sequence, 2)
        reopened.journal(Snapshot(3, 0, 0, "three"))
        from magwrite_transport.journal import scan
        records, _, _ = scan(filesystem.read(reopened.journal_path))
        sequences = [sequence for sequence, _ in records]
        self.assertEqual(sequences, sorted(set(sequences)))

    def test_a_refused_write_is_reported_and_never_raises(self):
        store, filesystem, _ = opened()
        filesystem.refuse_writes_to(store.journal_path)
        self.assertFalse(store.journal(Snapshot(1, 0, 0, "lost")))
        self.assertIn("journal append failed", store.last_error)
        # The editor keeps its document either way; only durability was lost.
        self.assertEqual(store.journaled_revision, 0)

    def test_a_full_card_is_refused_before_it_is_exhausted(self):
        filesystem = FakeFileSystem(free=document_store.RESERVE_BYTES + 10)
        store, _, _ = opened(filesystem)
        self.assertFalse(store.journal(Snapshot(1, 0, 0, "too big for the reserve")))
        self.assertIn("insufficient free space", store.last_error)

    def test_unknown_free_space_does_not_disable_persistence(self):
        # Refusing every write on a platform that cannot report capacity is a
        # worse failure than discovering a full card.
        store, filesystem, _ = opened(FakeFileSystem(free=None))
        self.assertTrue(store.journal(Snapshot(1, 0, 0, "written")))


class CheckpointTests(unittest.TestCase):
    def test_a_checkpoint_discards_the_journal_and_keeps_the_document(self):
        store, filesystem, _ = opened()
        for revision in range(1, 4):
            store.journal(Snapshot(revision, 0, 0, "rev %d" % revision))
        self.assertTrue(store.checkpoint(Snapshot(4, 1, 2, "final\ntext")))
        self.assertEqual(store.journal_records, 0)
        self.assertEqual(filesystem.read(store.journal_path), b"")
        self.assertEqual(store.read_latest(), Snapshot(4, 1, 2, "final\ntext"))
        self.assertEqual(store.checkpoint_revision, 4)

    def test_the_mirror_is_a_plain_text_document_with_no_header(self):
        """It has to be readable on any computer the card is plugged into."""
        store, filesystem, _ = opened()
        store.checkpoint(Snapshot(2, 0, 0, "# Heading\n\nA paragraph."))
        self.assertEqual(
            filesystem.read(store.active_path), b"# Heading\n\nA paragraph."
        )

    def test_the_previous_mirror_is_preserved(self):
        store, filesystem, _ = opened()
        store.checkpoint(Snapshot(1, 0, 0, "first"))
        store.checkpoint(Snapshot(2, 0, 0, "second"))
        self.assertEqual(filesystem.read(store.active_path), b"second")
        self.assertEqual(
            filesystem.read(ROOT_PATH + "/documents/active.prev.md"), b"first"
        )

    def test_the_pending_mirror_never_survives_a_successful_checkpoint(self):
        store, filesystem, _ = opened()
        store.checkpoint(Snapshot(1, 0, 0, "text"))
        self.assertIsNone(filesystem.read(ROOT_PATH + "/documents/active.new.md"))

    def test_the_checkpoint_log_is_compacted_but_keeps_the_previous_one(self):
        store, filesystem, _ = opened()
        for revision in range(1, 12):
            store.checkpoint(Snapshot(revision, 0, 0, "rev %d" % revision))
        from magwrite_transport.journal import scan
        records, _, _ = scan(filesystem.read(store.checkpoint_path))
        self.assertLessEqual(len(records), document_store.MAX_CHECKPOINT_RECORDS)
        self.assertGreaterEqual(len(records), 2)
        self.assertEqual(records[-1][1].revision, 11)
        self.assertEqual(records[-2][1].revision, 10)
        self.assertGreater(store.compactions, 0)

    def test_a_failed_mirror_write_does_not_fail_the_checkpoint(self):
        # The mirror is a convenience; the recovery logs are the authority. Losing
        # the .md file must not make a durable snapshot look undurable.
        store, filesystem, _ = opened()
        filesystem.refuse_writes_to(ROOT_PATH + "/documents/active.new.md")
        self.assertTrue(store.checkpoint(Snapshot(3, 0, 0, "durable")))
        self.assertEqual(store.read_latest().revision, 3)
        self.assertIn("mirror write failed", store.last_error)


class PowerLossTests(unittest.TestCase):
    """Every interruption window, re-opened exactly as the board would."""

    def reopen(self, filesystem):
        store = DocumentStore(filesystem, root=ROOT_PATH)
        return store, store.open()

    def test_a_journal_append_cut_in_half_loses_only_that_append(self):
        store, filesystem, _ = opened()
        store.journal(Snapshot(1, 0, 4, "safe"))
        store.journal(Snapshot(2, 0, 9, "also safe"))
        filesystem.cut_power_during(store.journal_path, 12)
        with self.assertRaises(PowerCut):
            store.journal(Snapshot(3, 0, 4, "lost"))

        reopened, recovery = self.reopen(filesystem)
        self.assertTrue(recovery.truncated_tail)
        self.assertEqual(recovery.source, SOURCE_JOURNAL)
        self.assertEqual(recovery.snapshot, Snapshot(2, 0, 9, "also safe"))
        self.assertEqual(recovery.rejected_records, 0)

    def test_a_journal_append_lost_entirely_leaves_a_clean_journal(self):
        store, filesystem, _ = opened()
        store.journal(Snapshot(1, 0, 4, "safe"))
        filesystem.cut_power_during(store.journal_path, 0)
        with self.assertRaises(PowerCut):
            store.journal(Snapshot(2, 0, 0, "never landed"))
        _, recovery = self.reopen(filesystem)
        self.assertFalse(recovery.truncated_tail)
        self.assertEqual(recovery.snapshot, Snapshot(1, 0, 4, "safe"))

    def test_power_lost_while_the_checkpoint_record_is_written_keeps_the_journal(self):
        """Window one: the journal has not been discarded yet, so nothing is lost."""
        store, filesystem, _ = opened()
        store.journal(Snapshot(1, 0, 0, "one"))
        store.journal(Snapshot(2, 0, 3, "two"))
        filesystem.cut_power_during(store.checkpoint_path, 15)
        with self.assertRaises(PowerCut):
            store.checkpoint(Snapshot(2, 0, 3, "two"))

        _, recovery = self.reopen(filesystem)
        self.assertEqual(recovery.snapshot, Snapshot(2, 0, 3, "two"))
        self.assertEqual(recovery.source, SOURCE_JOURNAL)
        self.assertTrue(recovery.truncated_tail)

    def test_power_lost_between_the_checkpoint_and_the_journal_truncate(self):
        """Window two: the snapshot is in both logs, and revision resolves it.

        Power is cut immediately *after* the checkpoint record lands whole, which
        is the only moment at which the same acknowledged state exists in two
        places. Recovery has to be indifferent to which one it reads.
        """
        store, filesystem, _ = opened()
        newest = Snapshot(4, 1, 2, "the newest\nstate")
        store.journal(Snapshot(1, 0, 0, "one"))
        store.journal(newest)
        # A cut length beyond the record means it landed whole and power went
        # immediately afterwards, before the journal could be discarded.
        filesystem.cut_power_during(store.checkpoint_path, 10000)
        with self.assertRaises(PowerCut):
            store.checkpoint(newest)

        # Both logs hold it, which is exactly the state being tested.
        self.assertGreater(len(filesystem.read(store.checkpoint_path)), 0)
        self.assertGreater(len(filesystem.read(store.journal_path)), 0)

        reopened, recovery = self.reopen(filesystem)
        self.assertEqual(recovery.snapshot, newest)
        self.assertFalse(recovery.truncated_tail)
        self.assertEqual(recovery.journal_records, 2)
        self.assertEqual(recovery.checkpoint_records, 1)
        # And the resumed session must not re-use a sequence number either log
        # already holds, or the log becomes unreadable after the fact.
        self.assertGreater(reopened.journal_sequence, 2)

    def test_power_lost_when_the_journal_truncate_is_refused(self):
        """The same window, reached by a filesystem that refuses instead."""
        store, filesystem, _ = opened()
        newest = Snapshot(4, 0, 1, "newest")
        store.journal(newest)
        filesystem.refuse_writes_to(store.journal_path)
        self.assertTrue(store.checkpoint(newest))
        self.assertIn("journal truncate failed", store.last_error)
        _, recovery = self.reopen(filesystem)
        self.assertEqual(recovery.snapshot, newest)

    def test_power_lost_while_the_mirror_is_written_costs_nothing(self):
        """Window three: the mirror is not authoritative."""
        store, filesystem, _ = opened()
        filesystem.cut_power_during(ROOT_PATH + "/documents/active.new.md", 3)
        with self.assertRaises(PowerCut):
            store.checkpoint(Snapshot(7, 0, 5, "whole document"))

        _, recovery = self.reopen(filesystem)
        self.assertEqual(recovery.snapshot, Snapshot(7, 0, 5, "whole document"))
        self.assertEqual(recovery.source, SOURCE_CHECKPOINT)
        self.assertTrue(recovery.mirror_stale)

    def test_power_lost_during_compaction_leaves_the_checkpoint_log_intact(self):
        store, filesystem, _ = opened()
        for revision in range(1, 6):
            store.checkpoint(Snapshot(revision, 0, 0, "rev %d" % revision))
        filesystem.cut_power_during(
            ROOT_PATH + "/recovery/checkpoint.new.log", 10
        )
        try:
            store.checkpoint(Snapshot(6, 0, 0, "rev 6"))
        except PowerCut:
            pass
        _, recovery = self.reopen(filesystem)
        self.assertEqual(recovery.revision, 6)

    def test_the_newest_acknowledged_snapshot_survives_a_cut_at_every_offset(self):
        """The exit condition, swept rather than sampled.

        Power is cut at every byte offset of the append that carries revision
        three. Whatever lands, recovery must return either revision three or the
        last state that was durable before it -- and never a document that no
        acknowledged revision ever held.
        """
        outcomes = set()
        probe = DocumentStore(FakeFileSystem(), root=ROOT_PATH)
        probe.open()
        probe.journal(Snapshot(1, 0, 0, "one"))
        probe.journal(Snapshot(2, 0, 0, "two"))
        record_length = len(probe.backend.read(probe.journal_path))

        for offset in range(record_length + 4):
            store, filesystem, _ = opened()
            store.journal(Snapshot(1, 0, 3, "one"))
            store.journal(Snapshot(2, 0, 3, "two"))
            filesystem.cut_power_during(store.journal_path, offset)
            try:
                store.journal(Snapshot(3, 0, 5, "three"))
            except PowerCut:
                pass
            _, recovery = self.reopen(filesystem)
            self.assertIn(
                recovery.snapshot,
                (Snapshot(2, 0, 3, "two"), Snapshot(3, 0, 5, "three")),
                "offset %d recovered %r" % (offset, recovery.snapshot),
            )
            outcomes.add(recovery.revision)
        # Both outcomes must actually occur, or the sweep proved nothing.
        self.assertEqual(outcomes, {2, 3})


class NewDocumentTests(unittest.TestCase):
    def test_starting_a_new_document_clears_both_logs_and_the_mirror(self):
        store, filesystem, _ = opened()
        store.checkpoint(Snapshot(5, 0, 0, "old draft"))
        store.journal(Snapshot(6, 0, 0, "old draft plus"))
        store.start_new_document()
        self.assertEqual(store.checkpoint_revision, 0)
        self.assertEqual(store.journaled_revision, 0)
        self.assertIsNone(store.read_latest())
        self.assertEqual(filesystem.read(store.active_path), b"")

    def test_a_new_document_is_not_resurrected_by_a_reopen(self):
        store, filesystem, _ = opened()
        store.checkpoint(Snapshot(5, 0, 0, "old draft"))
        store.start_new_document()
        reopened = DocumentStore(filesystem, root=ROOT_PATH)
        recovery = reopened.open()
        self.assertFalse(recovery.recovered)

    def test_a_failure_to_clear_is_raised_rather_than_half_applied(self):
        store, filesystem, _ = opened()
        store.checkpoint(Snapshot(5, 0, 0, "old draft"))
        filesystem.refuse_writes_to(store.journal_path)
        with self.assertRaises(StoreError):
            store.start_new_document()


class SummaryTests(unittest.TestCase):
    def test_the_summary_reports_what_the_session_did(self):
        store, _, _ = opened()
        store.journal(Snapshot(1, 0, 0, "a"))
        store.checkpoint(Snapshot(2, 0, 0, "ab"))
        summary = store.summary()
        self.assertEqual(summary["journal_appends"], 1)
        self.assertEqual(summary["checkpoints_written"], 1)
        self.assertEqual(summary["checkpoint_revision"], 2)
        self.assertEqual(summary["root"], ROOT_PATH)
        self.assertIsNone(summary["last_storage_error"])

    def test_a_recovery_summary_names_the_source_and_the_truncation(self):
        store, filesystem, _ = opened()
        store.journal(Snapshot(3, 1, 2, "text"))
        filesystem.cut_power_during(store.journal_path, 5)
        with self.assertRaises(PowerCut):
            store.journal(Snapshot(4, 0, 0, "more"))
        reopened = DocumentStore(filesystem, root=ROOT_PATH)
        summary = reopened.open().summary()
        self.assertTrue(summary["recovered"])
        self.assertTrue(summary["truncated_final_record"])
        self.assertEqual(summary["source"], SOURCE_JOURNAL)
        self.assertEqual(summary["revision"], 3)
        self.assertEqual(summary["cursor_row"], 1)
        self.assertEqual(summary["cursor_column"], 2)


if __name__ == "__main__":
    unittest.main()
