"""Journal, Quick Note, Drafts, and Recent: the catalogue and the four modes.

Four layers, because four different things can break.

* the ``MWX1`` record, on its own, against every corruption a power cut produces
  -- the same three independent defences the recovery journal has, because it is
  deliberately the same discipline;
* :class:`DocumentIndex`, driven directly: ordering, the active document,
  compaction, and what a truncated tail actually costs;
* :class:`Library`, which is where a *mode* means something, driven against a
  real store on a filesystem that can lose power at a chosen byte;
* the whole thing through the real session, editor, shell, renderer, and
  transport, including a restart that has to bring back the document **and the
  mode it belongs to** -- the gap V1.3 recorded and handed to this phase.

The migration case is asserted first-class rather than as an afterthought,
because it is the one that operates on a document a writer already has: a card
written by V1.2 or V1.3 must come back with its words, its cursor, its revision,
and its journal, and this build must not move, rename, or rewrite any of them.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from fake_filesystem import FakeFileSystem, PowerCut
from keyboard_simulator import KeyboardLink, finish, press_kind, type_characters
from magwrite.test_pattern import GLYPHS
from magwrite.viewport_message import ViewportMessage
from magwrite.viewport_renderer import render_viewport
from magwrite_transport import shell_viewport
from magwrite_transport.document_index import (
    DocumentIndex, Entry, KIND_DRAFT, KIND_JOURNAL, KIND_NOTE, KINDS,
    MAX_TITLE_CHARS, UNKNOWN_KIND_LABEL, decode_entry, encode_entry, scan,
)
from magwrite_transport.document_store import (
    ACTIVE_ID, DocumentStore, LEGACY_CHECKPOINT_NAME, valid_id,
)
from magwrite_transport.editor import (
    CHAR, ENTER, InputEvent, MAX_DOCUMENT_CHARS, MultilineEditor,
)
from magwrite_transport.journal import JournalRecordError, Snapshot
from magwrite_transport.library import Library, MIGRATED_TITLE
from magwrite_transport.persistence import PersistenceController
from magwrite_transport.live_session import LIVE_SCENARIO_ID
from magwrite_transport.protocol import MAX_PAYLOAD_SIZE
from magwrite_transport.shell import (
    MODE_DRAFTS, MODE_JOURNAL, MODE_QUICK_NOTE, REQUEST_OPEN, STATE_DRAFTS,
    STATE_EDITOR, STATE_MAIN_MENU, Shell,
)

ROOT_PATH = "/sd/magwrite"


def build(filesystem=None, root=ROOT_PATH):
    """A store, a catalogue, and a library over one filesystem."""
    filesystem = filesystem if filesystem is not None else FakeFileSystem()
    store = DocumentStore(filesystem, root=root)
    store.open()
    index = DocumentIndex(filesystem, root)
    index.load()
    return filesystem, store, index, Library(store, index)


def write(store, text, revision=1, row=0, column=0):
    store.checkpoint(Snapshot(revision, row, column, text))


# --------------------------------------------------------------- the record


class RecordTests(unittest.TestCase):
    def entry(self, **overrides):
        fields = {"document_id": "n0001", "kind": KIND_NOTE,
                  "title": "NOTE 1", "opened": 3}
        fields.update(overrides)
        return Entry(**fields)

    def test_a_record_round_trips(self):
        record = encode_entry(5, self.entry())
        sequence, decoded = decode_entry(record[:-1])
        self.assertEqual(sequence, 5)
        self.assertEqual(decoded, self.entry())

    def test_a_record_is_one_newline_terminated_line(self):
        record = encode_entry(0, self.entry())
        self.assertTrue(record.endswith(b"\n"))
        self.assertEqual(record.count(b"\n"), 1)

    def test_a_truncated_record_is_rejected(self):
        record = encode_entry(0, self.entry(title="a longer title"))
        self.assertIsNone(decode_entry(record[:-6]))

    def test_a_corrupted_body_fails_the_crc(self):
        record = encode_entry(0, self.entry(title="ABCDEFGH"))
        broken = bytearray(record[:-1])
        broken[-1] = broken[-1] ^ 0x20
        self.assertIsNone(decode_entry(bytes(broken)))

    def test_a_wrong_magic_is_not_a_record(self):
        record = encode_entry(0, self.entry())
        self.assertIsNone(decode_entry(b"MWJ1" + record[4:-1]))

    def test_a_title_with_a_line_break_is_refused_rather_than_folded(self):
        # A record is one line and a title is one line. Refusing at the boundary
        # is what keeps the parser's field count a real check rather than
        # something the encoder quietly works around.
        with self.assertRaises(JournalRecordError):
            encode_entry(0, self.entry(title="two\nlines"))

    def test_a_title_with_a_backslash_survives_escaping(self):
        record = encode_entry(0, self.entry(title="back\\slash"))
        self.assertEqual(decode_entry(record[:-1])[1].title, "back\\slash")

    def test_an_unusable_id_is_refused_at_encode(self):
        for bad in ("", "Upper", "has space", "dots.", "x" * 40):
            self.assertFalse(valid_id(bad), bad)
            with self.assertRaises(JournalRecordError):
                encode_entry(0, self.entry(document_id=bad))

    def test_a_kind_with_a_space_is_refused_because_it_would_move_the_fields(self):
        with self.assertRaises(JournalRecordError):
            encode_entry(0, self.entry(kind="QUICK NOTE"))

    def test_an_oversized_title_is_refused_rather_than_truncated(self):
        with self.assertRaises(JournalRecordError):
            encode_entry(0, self.entry(title="t" * (MAX_TITLE_CHARS + 1)))

    def test_an_unrecognised_kind_is_kept_and_drawn_as_a_document(self):
        # A later build naming something new must not make a writer's document
        # disappear from their own device.
        record = encode_entry(0, self.entry(kind="LETTER"))
        decoded = decode_entry(record[:-1])[1]
        self.assertEqual(decoded.kind, "LETTER")
        self.assertEqual(decoded.label, UNKNOWN_KIND_LABEL)

    def test_every_known_kind_has_a_renderable_label(self):
        for kind in KINDS:
            for character in Entry("a", kind, "", 0).label:
                self.assertIn(character, GLYPHS)

    def test_scanning_reports_a_truncated_tail_without_losing_the_rest(self):
        data = encode_entry(0, self.entry()) + encode_entry(
            1, self.entry(document_id="n0002")
        )
        records, truncated, rejected = scan(data[:-4])
        self.assertEqual(len(records), 1)
        self.assertTrue(truncated)
        self.assertEqual(rejected, 0)


# ------------------------------------------------------------- the catalogue


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.filesystem = FakeFileSystem()
        self.index = DocumentIndex(self.filesystem, ROOT_PATH)
        self.filesystem.makedirs(ROOT_PATH)
        self.index.load()

    def test_an_empty_card_has_no_documents_and_no_active_one(self):
        self.assertEqual(len(self.index), 0)
        self.assertIsNone(self.index.active())

    def test_a_recorded_document_is_found_again_after_a_reload(self):
        self.index.record("n0001", KIND_NOTE, "NOTE 1")
        reopened = DocumentIndex(self.filesystem, ROOT_PATH)
        reopened.load()
        self.assertEqual(reopened.get("n0001").title, "NOTE 1")

    def test_the_active_document_is_the_one_opened_last(self):
        self.index.record("n0001", KIND_NOTE, "NOTE 1")
        self.index.record("j0001", KIND_JOURNAL, "JOURNAL 1")
        self.assertEqual(self.index.active().document_id, "j0001")
        self.index.touch("n0001")
        self.assertEqual(self.index.active().document_id, "n0001")

    def test_ordering_is_most_recently_opened_first(self):
        for number in range(1, 5):
            self.index.record("n%04d" % number, KIND_NOTE, "NOTE %d" % number)
        self.index.touch("n0002")
        order = [entry.document_id for entry in self.index.ordered()]
        self.assertEqual(order, ["n0002", "n0004", "n0003", "n0001"])

    def test_a_later_record_replaces_an_earlier_one_for_the_same_document(self):
        self.index.record("n0001", KIND_NOTE, "FIRST NAME")
        self.index.record("n0001", KIND_NOTE, "SECOND NAME")
        self.assertEqual(len(self.index), 1)
        self.assertEqual(self.index.get("n0001").title, "SECOND NAME")

    def test_the_newest_of_a_kind_is_found_across_kinds(self):
        self.index.record("j0001", KIND_JOURNAL, "JOURNAL 1")
        self.index.record("n0001", KIND_NOTE, "NOTE 1")
        self.index.record("j0002", KIND_JOURNAL, "JOURNAL 2")
        self.assertEqual(
            self.index.newest_of_kind(KIND_JOURNAL).document_id, "j0002"
        )
        self.assertEqual(self.index.newest_of_kind(KIND_NOTE).document_id, "n0001")
        self.assertIsNone(self.index.newest_of_kind(KIND_DRAFT))

    def test_next_id_skips_the_ids_already_taken(self):
        self.index.record("n0001", KIND_NOTE, "NOTE 1")
        self.index.record("n0002", KIND_NOTE, "NOTE 2")
        self.assertEqual(self.index.next_id("n"), "n0003")

    def test_the_catalogue_is_bounded_and_refuses_cleanly_when_full(self):
        index = DocumentIndex(self.filesystem, ROOT_PATH, max_documents=3)
        index.load()
        for number in range(1, 4):
            self.assertIsNotNone(
                index.record("n%04d" % number, KIND_NOTE, "NOTE %d" % number)
            )
        self.assertTrue(index.full)
        self.assertIsNone(index.record("n0004", KIND_NOTE, "NOTE 4"))
        self.assertIn("maximum", index.last_error)
        # A full catalogue must not stop an existing document being re-opened.
        self.assertIsNotNone(index.touch("n0001"))

    def test_the_log_is_compacted_without_losing_a_document(self):
        index = DocumentIndex(self.filesystem, ROOT_PATH, max_records=6)
        index.load()
        for number in range(1, 4):
            index.record("n%04d" % number, KIND_NOTE, "NOTE %d" % number)
        for _ in range(4):
            index.touch("n0001")
        self.assertGreater(index.compactions, 0)
        reopened = DocumentIndex(self.filesystem, ROOT_PATH)
        reopened.load()
        self.assertEqual(len(reopened), 3)
        self.assertEqual(reopened.active().document_id, "n0001")

    def test_compaction_preserves_the_ordering_it_rewrote(self):
        index = DocumentIndex(self.filesystem, ROOT_PATH, max_records=5)
        index.load()
        for number in range(1, 4):
            index.record("n%04d" % number, KIND_NOTE, "NOTE %d" % number)
        index.touch("n0002")
        index.touch("n0003")
        before = [entry.document_id for entry in index.ordered()]
        reopened = DocumentIndex(self.filesystem, ROOT_PATH)
        reopened.load()
        self.assertEqual([entry.document_id for entry in reopened.ordered()], before)

    def test_a_truncated_final_append_costs_one_open_and_nothing_else(self):
        self.index.record("n0001", KIND_NOTE, "NOTE 1")
        self.index.record("n0002", KIND_NOTE, "NOTE 2")
        raw = self.filesystem.read(self.index.path)
        self.filesystem.files[self.index.path] = raw[:-3]
        reopened = DocumentIndex(self.filesystem, ROOT_PATH)
        reopened.load()
        self.assertTrue(reopened.truncated_tail)
        self.assertEqual(len(reopened), 1)
        self.assertEqual(reopened.active().document_id, "n0001")

    def test_a_failed_append_is_reported_rather_than_raised(self):
        self.filesystem.refuse_writes_to(self.index.path)
        self.assertIsNone(self.index.record("n0001", KIND_NOTE, "NOTE 1"))
        self.assertIn("append failed", self.index.last_error)

    def test_a_power_cut_mid_append_leaves_the_earlier_records_readable(self):
        self.index.record("n0001", KIND_NOTE, "NOTE 1")
        self.filesystem.cut_power_during(self.index.path, 10)
        with self.assertRaises(PowerCut):
            self.index.record("n0002", KIND_NOTE, "NOTE 2")
        reopened = DocumentIndex(self.filesystem, ROOT_PATH)
        reopened.load()
        self.assertEqual(len(reopened), 1)
        self.assertEqual(reopened.get("n0001").title, "NOTE 1")


# ----------------------------------------------------------------- the modes


class JournalModeTests(unittest.TestCase):
    def setUp(self):
        self.filesystem, self.store, self.index, self.library = build()

    def test_the_first_journal_open_creates_a_numbered_entry(self):
        opening = self.library.open_journal()
        self.assertTrue(opening.created)
        self.assertEqual(opening.kind, KIND_JOURNAL)
        self.assertEqual(opening.title, "JOURNAL 1")
        self.assertEqual(opening.text, "")

    def test_the_second_journal_open_continues_the_same_entry(self):
        first = self.library.open_journal()
        write(self.store, "yesterday I wrote this", revision=4)
        second = self.library.open_journal()
        self.assertFalse(second.created)
        self.assertEqual(second.document_id, first.document_id)
        self.assertEqual(second.text, "yesterday I wrote this")

    def test_continuing_a_journal_puts_the_cursor_after_the_last_words(self):
        # "Append-oriented" is the whole of the mode: sitting down and typing
        # must continue the entry rather than insert at the top of it.
        self.library.open_journal()
        write(self.store, "line one\nline two", revision=4)
        opening = self.library.open_journal()
        self.assertEqual(opening.cursor(), (1, len("line two")))

    def test_a_journal_entry_rolls_over_when_there_is_no_room_left(self):
        first = self.library.open_journal()
        write(self.store, "x" * (MAX_DOCUMENT_CHARS - 8), revision=9)
        second = self.library.open_journal()
        self.assertTrue(second.created)
        self.assertNotEqual(second.document_id, first.document_id)
        self.assertEqual(second.title, "JOURNAL 2")
        self.assertEqual(second.text, "")

    def test_a_rolled_over_journal_leaves_the_previous_entry_intact(self):
        first = self.library.open_journal()
        text = "x" * (MAX_DOCUMENT_CHARS - 8)
        write(self.store, text, revision=9)
        self.library.open_journal()
        self.store.select(first.document_id)
        self.assertEqual(self.store.read_latest().text, text)


class QuickNoteTests(unittest.TestCase):
    def setUp(self):
        self.filesystem, self.store, self.index, self.library = build()

    def test_a_quick_note_is_always_new_and_always_empty(self):
        first = self.library.new_note()
        write(self.store, "captured", revision=3)
        second = self.library.new_note()
        self.assertNotEqual(second.document_id, first.document_id)
        self.assertTrue(second.created)
        self.assertEqual(second.text, "")

    def test_a_quick_note_never_disturbs_the_note_before_it(self):
        first = self.library.new_note()
        write(self.store, "captured", revision=3)
        self.library.new_note()
        self.store.select(first.document_id)
        self.assertEqual(self.store.read_latest().text, "captured")

    def test_notes_are_numbered_in_order(self):
        titles = [self.library.new_note().title for _ in range(3)]
        self.assertEqual(titles, ["NOTE 1", "NOTE 2", "NOTE 3"])


class RecentTests(unittest.TestCase):
    def setUp(self):
        self.filesystem, self.store, self.index, self.library = build()

    def test_recent_refuses_cleanly_when_nothing_has_been_opened(self):
        self.assertIsNone(self.library.open_recent())
        self.assertIn("nothing", self.library.last_error)

    def test_recent_returns_to_the_document_that_was_open_last(self):
        self.library.open_journal()
        note = self.library.new_note()
        write(self.store, "note text", revision=3)
        opening = self.library.open_recent()
        self.assertEqual(opening.document_id, note.document_id)
        self.assertEqual(opening.text, "note text")

    def test_recent_survives_a_restart(self):
        self.library.open_journal()
        note = self.library.new_note()
        write(self.store, "note text", revision=3)
        _, _, index, library = build(self.filesystem)
        self.assertEqual(index.active().document_id, note.document_id)
        self.assertEqual(library.open_recent().text, "note text")

    def test_recent_survives_a_power_cut_because_opening_is_what_records_it(self):
        # There is no "on close" step for a power cut to interrupt: the ordinal
        # is appended when the document is opened, before a character is typed.
        self.library.open_journal()
        note = self.library.new_note()
        self.filesystem.cut_power_during(self.store.journal_path, 5)
        with self.assertRaises(PowerCut):
            self.store.journal(Snapshot(2, 0, 0, "half a thought"))
        _, _, index, _ = build(self.filesystem)
        self.assertEqual(index.active().document_id, note.document_id)


class DraftsTests(unittest.TestCase):
    def setUp(self):
        self.filesystem, self.store, self.index, self.library = build()

    def test_drafts_lists_everything_most_recently_opened_first(self):
        self.library.open_journal()
        self.library.new_note()
        self.library.new_note()
        titles = [entry.title for entry in self.library.drafts()]
        self.assertEqual(titles, ["NOTE 2", "NOTE 1", "JOURNAL 1"])

    def test_opening_a_draft_by_id_returns_its_text(self):
        journal = self.library.open_journal()
        write(self.store, "journal text", revision=4)
        self.library.new_note()
        opening = self.library.open_document(journal.document_id)
        self.assertEqual(opening.text, "journal text")
        self.assertEqual(opening.kind, KIND_JOURNAL)

    def test_a_document_keeps_its_kind_however_it_is_reached(self):
        # Drafts is a way of reaching a document, not a way of writing one.
        note = self.library.new_note()
        self.library.open_journal()
        self.assertEqual(
            self.library.open_document(note.document_id).kind, KIND_NOTE
        )

    def test_an_unknown_document_is_refused_cleanly(self):
        self.assertIsNone(self.library.open_document("nope"))
        self.assertIn("unknown", self.library.last_error)


# ------------------------------------------------------------------ migration


class MigrationTests(unittest.TestCase):
    """A card written by V1.2 or V1.3, opened by V1.4."""

    def legacy_card(self, text="a draft from before", revision=41):
        """Write the exact file layout the pre-V1.4 builds produced."""
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        store.open()
        store.checkpoint(Snapshot(revision, 0, len(text), text))
        # Move the checkpoint log back to its pre-V1.4 name, which is the one
        # difference between what an older build wrote and what this one does.
        checkpoints = filesystem.read(store.checkpoint_path)
        del filesystem.files[store.checkpoint_path]
        filesystem.files[ROOT_PATH + "/recovery/" + LEGACY_CHECKPOINT_NAME] = (
            checkpoints
        )
        return filesystem

    def test_a_legacy_checkpoint_log_is_read_at_its_old_name(self):
        filesystem = self.legacy_card()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        recovery = store.open()
        self.assertTrue(recovery.recovered)
        self.assertEqual(recovery.snapshot.text, "a draft from before")
        self.assertEqual(recovery.snapshot.revision, 41)

    def test_migration_records_the_existing_document_and_moves_nothing(self):
        filesystem = self.legacy_card()
        before = dict(filesystem.files)
        store = DocumentStore(filesystem, root=ROOT_PATH)
        recovery = store.open()
        index = DocumentIndex(filesystem, ROOT_PATH)
        index.load()
        entry = Library(store, index).migrate(recovery)
        self.assertEqual(entry.document_id, ACTIVE_ID)
        self.assertEqual(entry.kind, KIND_DRAFT)
        self.assertEqual(entry.title, MIGRATED_TITLE)
        # The only new file is the catalogue. Nothing the writer owns was
        # renamed, rewritten, or removed.
        for path, data in before.items():
            self.assertEqual(filesystem.files.get(path), data, path)
        self.assertEqual(
            set(filesystem.files) - set(before), {ROOT_PATH + "/index.log"}
        )

    def test_the_migrated_document_is_the_one_that_opens(self):
        filesystem = self.legacy_card()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        recovery = store.open()
        index = DocumentIndex(filesystem, ROOT_PATH)
        index.load()
        Library(store, index).migrate(recovery)
        self.assertEqual(index.active().document_id, ACTIVE_ID)

    def test_the_migrated_document_still_recovers_after_a_restart(self):
        filesystem = self.legacy_card()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        index = DocumentIndex(filesystem, ROOT_PATH)
        index.load()
        Library(store, index).migrate(store.open())
        _, store2, index2, library2 = build(filesystem)
        opening = library2.open_recent()
        self.assertEqual(opening.document_id, ACTIVE_ID)
        self.assertEqual(opening.text, "a draft from before")

    def test_the_first_new_checkpoint_supersedes_the_legacy_log(self):
        filesystem = self.legacy_card()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        store.open()
        store.checkpoint(Snapshot(50, 0, 3, "new"))
        self.assertIn(store.checkpoint_path, filesystem.files)
        reopened = DocumentStore(filesystem, root=ROOT_PATH)
        self.assertEqual(reopened.open().snapshot.text, "new")
        # And the old file is left exactly where it was, untouched.
        self.assertIn(
            ROOT_PATH + "/recovery/" + LEGACY_CHECKPOINT_NAME, filesystem.files
        )

    def test_migration_is_performed_once_and_is_then_a_no_op(self):
        filesystem = self.legacy_card()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        recovery = store.open()
        index = DocumentIndex(filesystem, ROOT_PATH)
        index.load()
        library = Library(store, index)
        self.assertIsNotNone(library.migrate(recovery))
        self.assertIsNone(library.migrate(recovery))
        self.assertEqual(len(index), 1)

    def test_an_empty_card_has_nothing_to_migrate(self):
        _, store, index, library = build()
        self.assertIsNone(library.migrate(store.open()))
        self.assertEqual(len(index), 0)


# --------------------------------------------------------------- persistence


class RestoredMetadataTests(unittest.TestCase):
    """Everything V1.4 has to persist, asserted across a simulated restart."""

    def setUp(self):
        self.filesystem, self.store, self.index, self.library = build()
        self.library.open_journal()
        write(self.store, "journal words", revision=6)
        note = self.library.new_note()
        write(self.store, "note words", revision=9)
        self.note_id = note.document_id

    def reopen(self):
        return build(self.filesystem)

    def test_document_identity_is_restored(self):
        _, _, index, _ = self.reopen()
        self.assertIn(self.note_id, index.entries)

    def test_the_mode_is_restored_with_the_document(self):
        _, _, index, _ = self.reopen()
        self.assertEqual(index.get(self.note_id).kind, KIND_NOTE)

    def test_the_title_is_restored(self):
        _, _, index, _ = self.reopen()
        self.assertEqual(index.get(self.note_id).title, "NOTE 1")

    def test_last_opened_ordering_is_restored(self):
        _, _, index, _ = self.reopen()
        self.assertEqual(
            [entry.title for entry in index.ordered()], ["NOTE 1", "JOURNAL 1"]
        )

    def test_the_active_document_is_restored(self):
        _, _, index, _ = self.reopen()
        self.assertEqual(index.active().document_id, self.note_id)

    def test_the_text_of_every_document_is_restored(self):
        _, store, index, _ = self.reopen()
        found = {}
        for entry in index.ordered():
            store.select(entry.document_id)
            found[entry.title] = store.read_latest().text
        self.assertEqual(
            found, {"JOURNAL 1": "journal words", "NOTE 1": "note words"}
        )

    def test_two_documents_do_not_share_a_journal(self):
        # The property the per-document naming exists to provide. If they shared
        # one, the newest snapshot of either would recover as both.
        _, store, index, _ = self.reopen()
        paths = set()
        for entry in index.ordered():
            store.select(entry.document_id)
            paths.add(store.journal_path)
            paths.add(store.checkpoint_path)
            paths.add(store.active_path)
        self.assertEqual(len(paths), 6)


# ---------------------------------------------------------------- the shell


class ShellDraftsScreenTests(unittest.TestCase):
    def setUp(self):
        self.shell = Shell()
        self.entries = tuple(
            Entry("n%04d" % n, KIND_NOTE, "NOTE %d" % n, 10 - n)
            for n in range(1, 9)
        )

    def enter_drafts(self):
        self.shell.selection = 2
        self.shell.enter()
        self.shell.set_documents(self.entries)

    def test_drafts_opens_a_list_rather_than_the_editor(self):
        self.enter_drafts()
        self.assertEqual(self.shell.state, STATE_DRAFTS)
        self.assertEqual(self.shell.draft_count, 8)

    def test_the_selection_moves_and_clamps(self):
        self.enter_drafts()
        for _ in range(20):
            self.shell.route(InputEvent(0, "s", "DOWN"))
        self.assertEqual(self.shell.draft_selection, 7)
        for _ in range(20):
            self.shell.route(InputEvent(0, "s", "UP"))
        self.assertEqual(self.shell.draft_selection, 0)

    def test_the_window_follows_the_selection(self):
        self.enter_drafts()
        for _ in range(7):
            self.shell.route(InputEvent(0, "s", "DOWN"))
        visible = self.shell.visible_drafts()
        self.assertEqual(len(visible), 5)
        self.assertIs(visible[-1], self.entries[7])

    def test_opening_a_draft_asks_the_session_and_adopts_its_mode(self):
        self.enter_drafts()
        self.shell.route(InputEvent(0, "s", "DOWN"))
        self.shell.route(InputEvent(0, "s", "ENTER"))
        self.assertEqual(self.shell.state, STATE_EDITOR)
        self.assertEqual(self.shell.take_request(), (REQUEST_OPEN, "n0002"))
        self.assertEqual(self.shell.mode, MODE_QUICK_NOTE)

    def test_typing_at_the_list_never_reaches_a_document(self):
        self.enter_drafts()
        before = self.shell.ignored_events
        for character in "hello":
            self.shell.route(InputEvent(0, "s", CHAR, character))
        self.assertEqual(self.shell.ignored_events, before + 5)
        self.assertEqual(self.shell.state, STATE_DRAFTS)

    def test_enter_on_an_empty_list_is_not_a_fault(self):
        self.shell.selection = 2
        self.shell.enter()
        self.shell.route(InputEvent(0, "s", "ENTER"))
        self.assertEqual(self.shell.state, STATE_DRAFTS)
        self.assertEqual(self.shell.faults, 0)

    def test_back_from_the_list_returns_to_the_menu(self):
        self.enter_drafts()
        self.shell.back()
        self.assertEqual(self.shell.state, STATE_MAIN_MENU)

    def test_the_list_screen_renders_on_the_real_panel(self):
        self.enter_drafts()
        payload = shell_viewport.drafts_payload(self.shell, "s")
        self.assertLessEqual(len(payload), MAX_PAYLOAD_SIZE)
        message = ViewportMessage.decode(1, payload)
        self.assertEqual(len(message.lines), 5)
        self.assertTrue(message.lines[0].startswith("> "))
        render_viewport(message)

    def test_an_empty_list_says_so_and_still_renders(self):
        self.shell.selection = 2
        self.shell.enter()
        payload = shell_viewport.drafts_payload(self.shell)
        message = ViewportMessage.decode(1, payload)
        self.assertIn(shell_viewport.NO_DRAFTS, message.lines)
        render_viewport(message)

    def test_the_restored_mode_comes_from_the_document(self):
        # V1.3 reported JOURNAL after a session that ended in a note, because
        # the mode was taken from the menu. It now arrives with the document.
        shell = Shell()
        shell.restore(True, 12, "n0001", KIND_NOTE, "NOTE 1")
        self.assertEqual(shell.state, STATE_EDITOR)
        self.assertEqual(shell.mode, MODE_QUICK_NOTE)
        self.assertEqual(shell.document_title, "NOTE 1")
        self.assertEqual(shell.selected_mode, MODE_QUICK_NOTE)

    def test_a_restore_without_a_catalogue_behaves_exactly_as_v13_did(self):
        shell = Shell()
        shell.restore(True, 12)
        self.assertEqual(shell.state, STATE_EDITOR)
        self.assertEqual(shell.mode, MODE_JOURNAL)


# ------------------------------------------------------------- whole session


def session_link(filesystem=None, reports=(), render=render_viewport):
    """A full session with a shell, persistence, and a catalogue."""
    filesystem, store, index, library = build(filesystem)
    shell = Shell()
    # One log for the whole stack, so the ordering of a checkpoint against a
    # document switch is observable in a single stream rather than inferred.
    records = []
    library.log = records.append
    link = KeyboardLink(
        reports=reports, shell=shell, log=records.append, render=render,
        persistence=PersistenceController(store, 0.0, records.append),
        library=library, typing_interval_seconds=0.05,
    )
    link.records = records
    link.store = store
    link.index = index
    link.library = library
    link.shell = shell
    link.filesystem = filesystem
    return link


class TwoModeSessionTests(unittest.TestCase):
    """The V1.4 exit criterion: capture in two modes through the real code."""

    @classmethod
    def setUpClass(cls):
        reports = press_kind("ENTER")               # JOURNAL -> editor
        reports += type_characters("journal entry")
        reports += finish()                        # -> menu, checkpointed
        reports += press_kind("DOWN")              # QUICK NOTE
        reports += press_kind("ENTER")             # -> editor, a new note
        reports += type_characters("a quick note")
        reports += finish()                        # -> menu, checkpointed
        reports += finish()                        # stop
        cls.rendered = []

        def recording_render(viewport):
            cls.rendered.append(viewport)
            return render_viewport(viewport)

        cls.link = session_link(
            reports=reports, render=recording_render
        ).run()
        cls.summary = cls.link.session.summary("COMPLETE")

    def test_the_session_completed_through_the_shell(self):
        self.assertTrue(self.link.session.complete)
        self.assertEqual(self.summary["shell_state"], "EXIT")

    def test_two_documents_were_created(self):
        self.assertEqual(self.summary["documents"], 2)
        self.assertEqual(self.summary["library_creations"], 2)

    def test_each_mode_wrote_into_its_own_document(self):
        found = {}
        for entry in self.link.index.ordered():
            self.link.store.select(entry.document_id)
            found[entry.title] = self.link.store.read_latest().text
        self.assertEqual(
            found, {"JOURNAL 1": "journal entry", "NOTE 1": "a quick note"}
        )

    def test_the_journal_was_checkpointed_before_the_note_replaced_it(self):
        # The safety argument for a document switch: the outgoing words are
        # durable before anything is rebound.
        opened = [
            record for record in self.link.records
            if record.get("event") == "live_document_opened"
        ]
        checkpoints = [
            record for record in self.link.records
            if record.get("event") == "document_checkpointed"
        ]
        self.assertEqual(len(opened), 2)
        self.assertGreaterEqual(len(checkpoints), 2)
        first_note_open = self.link.records.index(opened[1])
        earlier = [
            record for record in self.link.records[:first_note_open]
            if record.get("event") == "document_checkpointed"
        ]
        self.assertTrue(earlier)
        self.assertEqual(earlier[-1]["characters"], len("journal entry"))

    def test_the_panel_named_each_document_rather_than_only_its_mode(self):
        # Asserted against what the real renderer actually drew. Two journal
        # entries look identical if the panel only ever says JOURNAL, so the
        # document's own title is what the title field carries.
        titles = set(
            view.title.split(" L")[0] for view in self.rendered
            if view.scenario_id == LIVE_SCENARIO_ID
        )
        self.assertEqual(titles, {"JOURNAL 1", "NOTE 1"})

    def test_the_final_mode_is_the_one_the_writer_last_chose(self):
        self.assertEqual(self.summary["shell_document_title"], "NOTE 1")
        self.assertEqual(self.summary["shell_document_kind"], KIND_NOTE)

    def test_nothing_was_rejected_and_the_shell_never_faulted(self):
        self.assertEqual(self.summary["events_rejected"], 0)
        self.assertEqual(self.summary["shell_faults"], 0)
        self.assertEqual(self.summary["document_open_failures"], 0)

    def test_the_pacing_and_acknowledgement_paths_were_the_proven_ones(self):
        self.assertEqual(self.summary["status_sequence_gaps"], 0)
        self.assertEqual(self.summary["crc_failures"], 0)
        self.assertTrue(self.summary["test_complete"])


class RecoveredModeSessionTests(unittest.TestCase):
    """A restart brings back the document *and* the mode it belongs to."""

    def test_a_restarted_session_reopens_the_note_as_a_note(self):
        reports = press_kind("DOWN") + press_kind("ENTER")
        reports += type_characters("unfinished")
        reports += finish() + finish()
        first = session_link(reports=reports).run()
        note_id = first.shell.document_id

        # Restart: a fresh store, catalogue, editor, shell, and session over the
        # same card, exactly as the board does after a reset.
        filesystem, store, index, library = build(first.filesystem)
        entry = index.active()
        recovery = store.select(entry.document_id)
        shell = Shell()
        link = KeyboardLink(
            reports=finish(), shell=shell,
            persistence=PersistenceController(store, 0.0), library=library,
        )
        link.session.restore(recovery.snapshot, entry)

        self.assertEqual(entry.document_id, note_id)
        self.assertEqual(shell.state, STATE_EDITOR)
        self.assertEqual(shell.mode, MODE_QUICK_NOTE)
        self.assertEqual(shell.document_title, "NOTE 1")
        self.assertEqual(link.session.editor.text, "unfinished")

    def test_a_forced_power_loss_recovers_the_words_and_the_mode(self):
        reports = press_kind("ENTER") + type_characters("half a sentence")
        link = session_link(reports=reports)
        # No clean stop: the run is abandoned mid-session, which is what a
        # cable pull looks like to the card.
        for _ in range(4000):
            if not link.backend.reports and link.session.persistence.journals:
                break
            link.step()
        filesystem, store, index, library = build(link.filesystem)
        entry = index.active()
        recovery = store.select(entry.document_id)
        self.assertTrue(recovery.recovered)
        self.assertEqual(entry.kind, KIND_JOURNAL)
        self.assertEqual(entry.title, "JOURNAL 1")
        self.assertTrue(recovery.snapshot.text)
        self.assertTrue("half a sentence".startswith(recovery.snapshot.text))


class NoCatalogueTests(unittest.TestCase):
    """Without a library the shell behaves exactly as the verified V1.3 build."""

    def test_the_four_items_all_route_into_the_one_document(self):
        shell = Shell()
        link = KeyboardLink(
            reports=press_kind("ENTER") + type_characters("one document")
            + finish() + finish(),
            shell=shell, typing_interval_seconds=0.05,
        ).run()
        self.assertIsNone(link.session.library)
        self.assertEqual(link.session.editor.text, "one document")
        self.assertIsNone(shell.document_id)
        self.assertNotIn("documents_opened", link.session.summary("COMPLETE"))


class ConfigAgreementTests(unittest.TestCase):
    """``config`` may mirror a bound. It may never be a second definition of one."""

    def config_values(self):
        import ast

        values = {}
        with open(os.path.join(ROOT, "fruitjam", "config.py"),
                  encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if "=" not in line or line.startswith(("#", " ")):
                    continue
                name, _, raw = line.partition("=")
                try:
                    values[name.strip()] = ast.literal_eval(raw.strip())
                except (SyntaxError, ValueError):
                    pass
        return values

    def test_the_config_matches_the_editor_document_bounds(self):
        from magwrite_transport import editor as editor_module

        values = self.config_values()
        for name in ("MAX_DOCUMENT_CHARS", "MAX_DOCUMENT_LINES",
                     "MAX_LINE_CHARS"):
            self.assertEqual(values[name], getattr(editor_module, name), name)

    def test_the_config_matches_the_catalogue_bound(self):
        from magwrite_transport import document_index

        self.assertEqual(
            self.config_values()["MAX_DOCUMENTS"], document_index.MAX_DOCUMENTS
        )

    def test_the_config_matches_the_store_reserve(self):
        from magwrite_transport import document_store

        self.assertEqual(
            self.config_values()["DOCUMENT_RESERVE_BYTES"],
            document_store.RESERVE_BYTES,
        )

    def test_the_reserve_covers_a_worst_case_record_and_a_mirror_rewrite(self):
        from magwrite_transport import document_store
        from magwrite_transport.journal import MAX_RECORD_BYTES

        self.assertGreater(
            document_store.RESERVE_BYTES,
            2 * MAX_RECORD_BYTES + MAX_DOCUMENT_CHARS,
        )


if __name__ == "__main__":
    unittest.main()
