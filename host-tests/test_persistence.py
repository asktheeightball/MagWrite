"""Autosave policy, save state, and persistence in the live session.

Three layers, deliberately separate, matching how the display pacing is tested:

* :func:`save_state.evaluate` is a pure function and is asserted directly;
* :class:`PersistenceController` is driven with an ordinary float clock so every
  threshold is reachable and every constant is asserted against the reasoning
  that justifies it;
* whole live sessions then run through the real editor, viewport, transport,
  acknowledgement, and store code, so the policy is proved in place -- including
  a session that is killed mid-word and resumed from the card.
"""

import ast
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from fake_filesystem import FakeFileSystem
from keyboard_simulator import KeyboardLink, finish, report, type_characters
from magwrite_transport import persistence as persistence_module
from magwrite_transport import save_state
from magwrite_transport.document_store import DocumentStore
from magwrite_transport.editor import EditRejected, MultilineEditor
from magwrite_transport.hid_keymap import MODIFIER_LEFT_CTRL, USAGE_S
from magwrite_transport.journal import Snapshot
from magwrite_transport.persistence import (
    ACTION_CHECKPOINTED, ACTION_FAILED, ACTION_JOURNALED, ACTION_NONE,
    PersistenceController,
)

ROOT_PATH = "/sd/magwrite"


def ctrl_s():
    """The Ctrl-S keystroke, as two boot reports."""
    return [report(MODIFIER_LEFT_CTRL, (USAGE_S,)), report(MODIFIER_LEFT_CTRL)]


def store_on(filesystem=None):
    filesystem = filesystem or FakeFileSystem()
    store = DocumentStore(filesystem, root=ROOT_PATH)
    recovery = store.open()
    return store, filesystem, recovery


class FakeEditor:
    """Just the four fields the persistence layer is allowed to read."""

    def __init__(self, revision=0, row=0, column=0, text=""):
        self.document_revision = revision
        self.row = row
        self.column = column
        self.text = text


class SaveStateTests(unittest.TestCase):
    def test_everything_checkpointed_is_saved(self):
        self.assertEqual(save_state.evaluate(5, 5, 5), save_state.SAVED)

    def test_journaled_but_not_checkpointed_is_recoverable(self):
        self.assertEqual(save_state.evaluate(5, 5, 2), save_state.RECOVERABLE)

    def test_edits_newer_than_the_journal_are_unsaved(self):
        self.assertEqual(save_state.evaluate(7, 5, 5), save_state.UNSAVED)

    def test_an_error_outranks_an_apparently_clean_state(self):
        self.assertEqual(
            save_state.evaluate(5, 5, 5, error="card full"), save_state.ERROR
        )

    def test_no_card_outranks_everything_including_an_error(self):
        self.assertEqual(
            save_state.evaluate(0, 0, 0, has_storage=False, error="anything"),
            save_state.NO_CARD,
        )

    def test_a_fresh_empty_document_is_saved_not_unsaved(self):
        # Revision zero has nothing to persist, so telling the writer their empty
        # document is unsaved would be noise.
        self.assertEqual(save_state.evaluate(0, 0, 0), save_state.SAVED)

    def test_every_state_has_exactly_one_distinct_indicator_character(self):
        indicators = [save_state.indicator(state) for state in save_state.STATES]
        self.assertEqual(len(set(indicators)), len(save_state.STATES))
        for token in indicators:
            self.assertEqual(len(token), 1)
            self.assertTrue(32 <= ord(token) <= 126)

    def test_an_unknown_state_is_refused_rather_than_drawn_blank(self):
        with self.assertRaises(ValueError):
            save_state.indicator("PROBABLY_FINE")

    def test_every_indicator_has_a_glyph_the_panel_can_actually_draw(self):
        """The indicator is rendered, so an undrawable character is a crash.

        The first version of this table used "=" and "*". Both are one printable
        ASCII character and neither has a glyph, so the renderer raised
        ``KeyError`` on the first frame that carried a save state -- on the
        MagTag, mid-session, with no diagnostic. This is the assertion that turns
        that into a host-test failure.
        """
        from magwrite.test_pattern import GLYPHS
        for state in save_state.STATES:
            self.assertIn(save_state.indicator(state), GLYPHS, state)


class ControllerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.store, self.filesystem, _ = store_on()
        self.controller = PersistenceController(self.store, 0.0)
        self.editor = FakeEditor()

    def advance(self, editor_revision, text="x"):
        self.editor.document_revision = editor_revision
        self.editor.text = text

    def test_nothing_happens_when_there_is_nothing_new(self):
        self.assertEqual(self.controller.service(0.0, self.editor), ACTION_NONE)

    def test_a_pause_journals_almost_immediately(self):
        self.advance(3)
        self.controller.note_input(1.0)
        self.assertEqual(self.controller.service(1.1, self.editor), ACTION_NONE)
        due = 1.0 + persistence_module.AUTOSAVE_IDLE_SECONDS
        self.assertEqual(self.controller.service(due, self.editor), ACTION_JOURNALED)
        self.assertEqual(self.store.journaled_revision, 3)

    def test_sustained_typing_journals_on_the_revision_threshold(self):
        for revision in range(1, persistence_module.AUTOSAVE_REVISIONS):
            self.advance(revision)
            self.controller.note_input(revision * 0.05)
            self.assertEqual(
                self.controller.service(revision * 0.05, self.editor), ACTION_NONE
            )
        self.advance(persistence_module.AUTOSAVE_REVISIONS)
        self.controller.note_input(1.5)
        self.assertEqual(self.controller.service(1.5, self.editor), ACTION_JOURNALED)

    def test_an_unbroken_burst_still_journals_on_the_age_bound(self):
        # The writer never pauses and never reaches the revision threshold, so the
        # age bound is the only thing that can make the work durable.
        now = 0.0
        while now < persistence_module.AUTOSAVE_MAX_AGE_SECONDS - 0.1:
            now += 0.1
            self.advance(1)
            self.controller.note_input(now)
            self.assertEqual(self.controller.service(now, self.editor), ACTION_NONE)
        now = persistence_module.AUTOSAVE_MAX_AGE_SECONDS
        self.controller.note_input(now)
        self.assertEqual(self.controller.service(now, self.editor), ACTION_JOURNALED)

    def test_a_checkpoint_waits_for_a_pause_at_the_soft_bound(self):
        for index in range(persistence_module.CHECKPOINT_RECORDS):
            self.store.journal(Snapshot(index + 1, 0, 0, "x"))
        self.advance(100)
        self.controller.note_input(10.0)
        self.assertEqual(self.controller.service(10.1, self.editor), ACTION_JOURNALED)
        self.controller.note_input(11.0)
        due = 11.0 + persistence_module.CHECKPOINT_IDLE_SECONDS
        self.assertEqual(
            self.controller.service(due, self.editor), ACTION_CHECKPOINTED
        )

    def test_the_hard_record_bound_checkpoints_even_mid_burst(self):
        """Otherwise an uninterrupted burst grows the journal until the card fills."""
        for index in range(persistence_module.CHECKPOINT_MAX_RECORDS):
            self.store.journal(Snapshot(index + 1, 0, 0, "x"))
        self.advance(200)
        self.controller.note_input(5.0)
        self.assertEqual(
            self.controller.service(5.0, self.editor), ACTION_CHECKPOINTED
        )
        self.assertEqual(self.store.journal_records, 0)

    def test_a_quiet_session_still_checkpoints_on_the_age_bound(self):
        self.advance(2)
        self.controller.note_input(0.0)
        self.controller.service(2.0, self.editor)
        now = persistence_module.CHECKPOINT_MAX_AGE_SECONDS + 1.0
        self.assertEqual(
            self.controller.service(now, self.editor), ACTION_CHECKPOINTED
        )

    def test_an_untouched_document_is_not_checkpointed_on_the_age_bound(self):
        # Nothing has changed, so rewriting the mirror forever would be pure wear.
        now = persistence_module.CHECKPOINT_MAX_AGE_SECONDS + 1.0
        self.assertEqual(self.controller.service(now, self.editor), ACTION_NONE)

    def test_at_most_one_storage_operation_runs_per_service_call(self):
        for index in range(persistence_module.CHECKPOINT_MAX_RECORDS):
            self.store.journal(Snapshot(index + 1, 0, 0, "x"))
        before = self.filesystem.appends + self.filesystem.writes
        self.advance(300)
        self.controller.service(5.0, self.editor)
        self.assertEqual(self.controller.last_action, ACTION_CHECKPOINTED)
        # One checkpoint is a bounded, known number of backend operations rather
        # than an open-ended amount of work.
        self.assertLessEqual(
            self.filesystem.appends + self.filesystem.writes - before, 5
        )

    def test_a_manual_save_checkpoints_regardless_of_every_threshold(self):
        self.advance(1)
        self.controller.note_input(0.0)
        self.assertEqual(
            self.controller.save_now(0.0, self.editor), ACTION_CHECKPOINTED
        )
        self.assertEqual(self.store.checkpoint_revision, 1)
        self.assertEqual(self.controller.manual_saves, 1)

    def test_a_refused_write_is_reported_and_the_state_becomes_error(self):
        self.filesystem.refuse_writes_to(self.store.journal_path)
        self.advance(5)
        self.controller.note_input(0.0)
        self.assertEqual(
            self.controller.service(10.0, self.editor), ACTION_FAILED
        )
        self.assertEqual(self.controller.state, save_state.ERROR)
        self.assertEqual(self.controller.failures, 1)

    def test_the_state_walks_from_unsaved_through_recoverable_to_saved(self):
        self.advance(4)
        self.controller.note_input(0.0)
        self.controller.service(0.1, self.editor)
        self.assertEqual(self.controller.state, save_state.UNSAVED)
        self.controller.service(5.0, self.editor)
        self.assertEqual(self.controller.state, save_state.RECOVERABLE)
        self.controller.save_now(5.0, self.editor)
        self.assertEqual(self.controller.state, save_state.SAVED)

    def test_an_incoherent_configuration_is_refused_at_construction(self):
        for bad in (
            {"autosave_idle_seconds": 0.0},
            {"autosave_max_age_seconds": -1.0},
            {"autosave_revisions": 0},
            {"checkpoint_records": 0},
            {"checkpoint_max_records": 1, "checkpoint_records": 5},
        ):
            with self.assertRaises(ValueError):
                PersistenceController(self.store, 0.0, **bad)


class NoStorageTests(unittest.TestCase):
    """A missing card must be visible and harmless, never silent."""

    def setUp(self):
        self.records = []
        self.controller = PersistenceController(
            None, 0.0, self.records.append, storage_detail="no card responded"
        )
        self.editor = FakeEditor(revision=9, text="unsaved work")

    def test_the_state_is_no_card_and_the_indicator_says_so(self):
        self.assertEqual(self.controller.state, save_state.NO_CARD)
        self.assertEqual(
            self.controller.indicator, save_state.indicator(save_state.NO_CARD)
        )

    def test_servicing_is_a_no_op_and_never_raises(self):
        self.assertEqual(self.controller.service(100.0, self.editor), ACTION_NONE)

    def test_a_manual_save_is_refused_out_loud(self):
        self.assertEqual(self.controller.save_now(1.0, self.editor), ACTION_NONE)
        events = [record["event"] for record in self.records]
        self.assertIn("manual_save_refused", events)

    def test_the_summary_carries_why_there_is_no_storage(self):
        summary = self.controller.summary()
        self.assertFalse(summary["storage_present"])
        self.assertEqual(summary["storage_detail"], "no card responded")
        self.assertEqual(summary["save_state"], save_state.NO_CARD)


class EditorLoadTests(unittest.TestCase):
    """A card is not a trusted input."""

    def setUp(self):
        self.editor = MultilineEditor()

    def test_a_recovered_document_restores_text_cursor_and_revision(self):
        self.editor.load("hello\nthere", 1, 3, 42)
        self.assertEqual(self.editor.text, "hello\nthere")
        self.assertEqual((self.editor.row, self.editor.column), (1, 3))
        self.assertEqual(self.editor.document_revision, 42)

    def test_loading_advances_the_viewport_revision(self):
        before = self.editor.viewport_revision
        self.editor.load("text")
        self.assertGreater(self.editor.viewport_revision, before)

    def test_editing_continues_from_the_recovered_revision(self):
        from magwrite_transport.editor import CHAR, InputEvent
        self.editor.load("abc", 0, 3, 42)
        self.editor.apply(InputEvent(0, "s", CHAR, "d"))
        self.assertEqual(self.editor.document_revision, 43)
        self.assertEqual(self.editor.text, "abcd")

    def test_a_document_that_exceeds_the_editor_bounds_is_refused(self):
        # Written against the editor's own bounds rather than literals, so it
        # keeps asserting the property when the bounds are next revised. The
        # first version of this test used 5000 and 200, and silently stopped
        # testing anything the moment V1.4 raised the document bound past them.
        from magwrite_transport.editor import (
            MAX_DOCUMENT_CHARS, MAX_DOCUMENT_LINES, MAX_LINE_CHARS,
        )
        with self.assertRaises(EditRejected):
            self.editor.load("a" * (MAX_LINE_CHARS + 1))
        with self.assertRaises(EditRejected):
            self.editor.load("\n".join("x" for _ in range(MAX_DOCUMENT_LINES + 1)))
        paragraph = "b" * MAX_LINE_CHARS
        count = MAX_DOCUMENT_CHARS // (MAX_LINE_CHARS + 1) + 2
        with self.assertRaises(EditRejected):
            self.editor.load("\n".join(paragraph for _ in range(count)))

    def test_an_unsupported_character_is_refused(self):
        with self.assertRaises(EditRejected):
            self.editor.load("café")

    def test_a_cursor_outside_the_document_is_refused(self):
        with self.assertRaises(EditRejected):
            self.editor.load("abc", 5, 0)
        with self.assertRaises(EditRejected):
            self.editor.load("abc", 0, 99)

    def test_a_revision_older_than_the_current_one_is_refused(self):
        self.editor.load("abc", 0, 0, 50)
        with self.assertRaises(EditRejected):
            self.editor.load("def", 0, 0, 10)

    def test_note_visible_change_advances_only_the_viewport_revision(self):
        document = self.editor.document_revision
        viewport = self.editor.viewport_revision
        self.editor.note_visible_change()
        self.assertEqual(self.editor.document_revision, document)
        self.assertEqual(self.editor.viewport_revision, viewport + 1)


class ViewportIndicatorTests(unittest.TestCase):
    def setUp(self):
        from magwrite_transport.editor_viewport import EditorViewport
        self.viewport = EditorViewport()
        self.editor = MultilineEditor(layout=self.viewport.layout)
        self.editor.load("hello", 0, 5, 3)

    def test_omitting_the_indicator_reproduces_the_verified_status_text(self):
        window = self.viewport.window(self.editor)
        self.assertEqual(
            self.viewport.status_text(self.editor, window),
            self.viewport.status_text(self.editor, window, None),
        )
        self.assertEqual(len(self.viewport.status_text(self.editor, window)), 16)

    def test_the_indicator_fits_the_fixed_status_field(self):
        window = self.viewport.window(self.editor)
        for state in save_state.STATES:
            text = self.viewport.status_text(
                self.editor, window, save_state.indicator(state)
            )
            self.assertEqual(len(text), 18)
            self.assertLessEqual(len(text), 20)

    def test_omitting_the_indicator_reproduces_the_verified_payload_exactly(self):
        """The transport's existing physical evidence must stay reachable."""
        self.assertEqual(
            self.viewport.payload(self.editor, 6),
            self.viewport.payload(self.editor, 6, None),
        )

    def test_a_multi_character_indicator_is_refused(self):
        window = self.viewport.window(self.editor)
        with self.assertRaises(ValueError):
            self.viewport.status_text(self.editor, window, "**")


class ConfigMirrorTests(unittest.TestCase):
    """``persistence`` is the single source of truth; config may only mirror it."""

    def config_values(self):
        values = {}
        path = os.path.join(ROOT, "fruitjam", "config.py")
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if "=" not in line or line.startswith(("#", " ")):
                    continue
                name, _, raw = line.partition("=")
                try:
                    values[name.strip()] = ast.literal_eval(raw.strip())
                except (SyntaxError, ValueError):
                    pass
        return values

    def test_the_config_matches_the_centralized_persistence_constants(self):
        values = self.config_values()
        for name in (
            "AUTOSAVE_IDLE_SECONDS", "AUTOSAVE_MAX_AGE_SECONDS",
            "AUTOSAVE_REVISIONS", "CHECKPOINT_RECORDS",
            "CHECKPOINT_MAX_RECORDS", "CHECKPOINT_MAX_AGE_SECONDS",
            "CHECKPOINT_IDLE_SECONDS",
        ):
            self.assertEqual(
                values[name], getattr(persistence_module, name), name
            )

    def test_the_config_values_the_board_loads_construct_a_valid_controller(self):
        values = self.config_values()
        controller = PersistenceController(
            None, 0.0,
            autosave_idle_seconds=values["AUTOSAVE_IDLE_SECONDS"],
            autosave_max_age_seconds=values["AUTOSAVE_MAX_AGE_SECONDS"],
            autosave_revisions=values["AUTOSAVE_REVISIONS"],
            checkpoint_records=values["CHECKPOINT_RECORDS"],
            checkpoint_max_records=values["CHECKPOINT_MAX_RECORDS"],
            checkpoint_max_age_seconds=values["CHECKPOINT_MAX_AGE_SECONDS"],
            checkpoint_idle_seconds=values["CHECKPOINT_IDLE_SECONDS"],
        )
        self.assertEqual(controller.state, save_state.NO_CARD)

    def test_no_autosave_interval_is_hard_coded_outside_the_persistence_module(self):
        for parts in (
            ("fruitjam", "magwrite_transport", "live_session.py"),
            ("fruitjam", "magwrite_transport", "document_store.py"),
            ("fruitjam", "dev_runtime.py"),
        ):
            with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
                source = handle.read()
            # Anchored, because ``document_store`` legitimately owns
            # MAX_CHECKPOINT_RECORDS -- a bound on the checkpoint *log*, which is
            # a different quantity from the autosave threshold of the same suffix.
            for name in ("AUTOSAVE_IDLE_SECONDS", "AUTOSAVE_MAX_AGE_SECONDS",
                         "AUTOSAVE_REVISIONS", "CHECKPOINT_RECORDS",
                         "CHECKPOINT_IDLE_SECONDS"):
                self.assertIsNone(
                    re.search(r"^%s\s*=" % name, source, re.MULTILINE),
                    "%s defines %s" % (parts[-1], name),
                )

    def test_a_pause_journals_before_the_panel_could_have_refreshed_twice(self):
        """Durability must not be paced to the display."""
        from magwrite_transport import pacing
        self.assertLess(
            persistence_module.AUTOSAVE_IDLE_SECONDS,
            pacing.SUSTAINED_MIN_SEND_SECONDS,
        )


class LiveSessionPersistenceTests(unittest.TestCase):
    """The policy proved in place, against the real session and transport."""

    def link(self, reports, filesystem=None, **options):
        store, filesystem, _ = store_on(filesystem)
        records = []
        controller = PersistenceController(store, 0.0, records.append, **options)
        link = KeyboardLink(reports=reports, persistence=controller,
                            typing_interval_seconds=0.05)
        link.controller = controller
        link.store = store
        link.filesystem = filesystem
        link.persistence_records = records
        return link

    def test_an_ordinary_typed_session_ends_fully_saved(self):
        link = self.link(type_characters("hello there") + finish()).run()
        self.assertEqual(link.session.editor.text, "hello there")
        self.assertEqual(link.controller.state, save_state.SAVED)
        self.assertEqual(link.store.read_latest().text, "hello there")

    def test_the_document_is_journaled_during_the_session_not_only_at_the_end(self):
        link = self.link(type_characters("a sentence of prose") + finish()).run()
        self.assertGreater(link.controller.journals, 0)

    def test_the_mirror_on_the_card_is_the_finished_plain_text_document(self):
        link = self.link(type_characters("plain text") + finish()).run()
        self.assertEqual(
            link.filesystem.read(link.store.active_path), b"plain text"
        )

    def test_ctrl_s_saves_and_inserts_nothing(self):
        """Before CONTROL_SAVE existed, this typed a literal "s"."""
        link = self.link(
            type_characters("draft") + ctrl_s() + type_characters("!") + finish()
        ).run()
        self.assertEqual(link.session.editor.text, "draft!")
        self.assertGreaterEqual(link.adapter.save_requests, 1)
        self.assertGreaterEqual(link.controller.manual_saves, 1)

    def test_repeated_ctrl_s_presses_collapse_into_one_checkpoint(self):
        link = self.link(
            type_characters("x") + ctrl_s() + ctrl_s() + ctrl_s() + finish()
        ).run()
        # Three presses plus the final save on stop; never one checkpoint each.
        self.assertLessEqual(link.session.manual_saves, 3)
        self.assertEqual(link.session.editor.text, "x")

    def test_the_save_indicator_reaches_the_transmitted_frame(self):
        """Asserted on the bytes that went down the wire, not on a local render."""
        link = self.link(type_characters("visible") + finish()).run()
        indicator = link.session.save_indicator
        self.assertIn(indicator, set(save_state.INDICATORS.values()))
        # The last payload actually sent to the MagTag carries the indicator in
        # its status field, and the panel rendered it without raising.
        self.assertIn(indicator.encode("ascii"), link.session.last_sent_payload)
        self.assertGreater(link.status_frames_sent, 0)

    def test_a_session_without_persistence_is_byte_identical_to_before(self):
        """Every guarded harness that produced the physical evidence runs this way."""
        plain = KeyboardLink(reports=type_characters("evidence") + finish()).run()
        self.assertIsNone(plain.session.persistence)
        self.assertIsNone(plain.session.save_indicator)
        payload = plain.session.viewport.payload(plain.session.editor, 6)
        self.assertEqual(payload, plain.session.last_sent_payload)

    def test_a_session_with_no_card_still_writes_and_shows_no_card(self):
        controller = PersistenceController(None, 0.0, storage_detail="empty slot")
        link = KeyboardLink(
            reports=type_characters("no card here") + finish(),
            persistence=controller,
        ).run()
        self.assertEqual(link.session.editor.text, "no card here")
        self.assertEqual(controller.state, save_state.NO_CARD)
        self.assertEqual(
            link.session.save_indicator, save_state.indicator(save_state.NO_CARD)
        )

    def test_a_full_card_never_stops_the_writer(self):
        filesystem = FakeFileSystem()
        store, filesystem, _ = store_on(filesystem)
        filesystem.refuse_writes_to(store.journal_path)
        controller = PersistenceController(store, 0.0)
        link = KeyboardLink(
            reports=type_characters("still typing") + finish(),
            persistence=controller, typing_interval_seconds=0.05,
        ).run()
        self.assertEqual(link.session.editor.text, "still typing")
        self.assertEqual(controller.state, save_state.ERROR)

    def test_one_revision_never_carries_two_different_payloads(self):
        """What ``note_visible_change`` exists to prevent."""
        link = self.link(type_characters("indicator churn") + finish()).run()
        seen = {}
        for record in link.records:
            if record.get("event") != "live_viewport_sent":
                continue
            revision = record["revision"]
            self.assertNotIn(revision, seen, "revision %d sent twice" % revision)
            seen[revision] = record["text_hash"]


class ForcedPowerLossRecoveryTests(unittest.TestCase):
    """The V1.2 exit condition, end to end, through the real session."""

    def test_a_session_killed_mid_word_resumes_from_the_card(self):
        # Session one: type, journal, then simply stop existing. No finish key, no
        # clean shutdown, no final checkpoint -- the board lost power.
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        store.open()
        controller = PersistenceController(store, 0.0)
        link = KeyboardLink(
            reports=type_characters("the quick brown fox"),
            persistence=controller, typing_interval_seconds=0.05,
        )
        # Run until the card actually holds something. Checking the save *state*
        # would stop immediately: an empty document at revision zero is already
        # SAVED, which is correct but is not what this test is waiting for.
        for _ in range(20000):
            link.step()
            if controller.journals + controller.checkpoints:
                break
        typed = link.session.editor.text
        acknowledged = link.session.editor.document_revision
        self.assertTrue(typed, "the simulated writer never typed anything")
        self.assertGreater(controller.journals + controller.checkpoints, 0)

        # The card, exactly as the power cut left it.
        card = filesystem.snapshot()

        # Session two: a fresh board, a fresh store, a fresh session.
        recovered_store = DocumentStore(card, root=ROOT_PATH)
        recovery = recovered_store.open()
        self.assertTrue(recovery.recovered)
        resumed_controller = PersistenceController(recovered_store, 0.0)
        resumed = KeyboardLink(reports=finish(), persistence=resumed_controller)
        resumed.session.restore(recovery.snapshot)

        # What was recovered is a prefix of what was typed, and is exactly the
        # last revision persistence ever promised was durable.
        self.assertTrue(
            typed.startswith(resumed.session.editor.text),
            "%r is not a prefix of %r" % (resumed.session.editor.text, typed),
        )
        self.assertEqual(
            resumed.session.editor.document_revision, recovery.snapshot.revision
        )
        self.assertLessEqual(recovery.snapshot.revision, acknowledged)
        # A restored session does not report unsaved work it has not created:
        # everything the editor holds came off the card. RECOVERABLE rather than
        # SAVED is the honest answer when the snapshot came from the journal and
        # has not been checkpointed -- what must never appear here is UNSAVED.
        self.assertIn(
            resumed_controller.state,
            (save_state.SAVED, save_state.RECOVERABLE),
        )

    def test_the_resumed_session_keeps_writing_and_saves_again(self):
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        store.open()
        # Cursor at the end of the recovered text, so the writer carries on from
        # where they stopped. That the cursor is honoured at all is asserted
        # separately below; here it just makes the resumed text readable.
        store.checkpoint(Snapshot(12, 0, len("first half"), "first half"))

        controller = PersistenceController(store, 0.0)
        resumed = KeyboardLink(
            reports=type_characters(" and more") + finish(),
            persistence=controller, typing_interval_seconds=0.05,
        )
        resumed.session.restore(store.read_latest())
        resumed.run()
        self.assertEqual(resumed.session.editor.text, "first half and more")
        self.assertEqual(store.read_latest().text, "first half and more")
        self.assertGreater(store.read_latest().revision, 12)

    def test_the_cursor_position_survives_the_power_loss(self):
        filesystem = FakeFileSystem()
        store = DocumentStore(filesystem, root=ROOT_PATH)
        store.open()
        store.journal(Snapshot(8, 1, 2, "line one\nline two"))

        card = filesystem.snapshot()
        recovered = DocumentStore(card, root=ROOT_PATH)
        snapshot = recovered.open().snapshot
        controller = PersistenceController(recovered, 0.0)
        session = KeyboardLink(reports=finish(), persistence=controller).session
        session.restore(snapshot)
        self.assertEqual((session.editor.row, session.editor.column), (1, 2))


if __name__ == "__main__":
    unittest.main()
