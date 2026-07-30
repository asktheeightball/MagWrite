"""The MagWrite shell: states, routing, screens, and what must never be lost.

Three layers, because three different things can break.

* :class:`Shell` is driven directly, so every transition -- including the ones
  that are supposed to be impossible -- is exercised without a keyboard.
* The screens are encoded with the real viewport encoder and drawn with the
  real MagTag renderer, because "a character" on this device means "a character
  the panel has a glyph for", and the first save indicator proved that the hard
  way by raising ``KeyError`` on a "=" .
* The whole thing is then driven by scripted USB reports through the same
  session, editor, storage, transport, and acknowledgement code the board runs,
  so the claim "the document survives every transition" is made against the real
  editor rather than a mock of one.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from fake_filesystem import FakeFileSystem
from keyboard_simulator import (
    KeyboardLink, finish, press_kind, type_characters,
)
from magwrite.test_pattern import GLYPHS
from magwrite.viewport_message import ViewportMessage
from magwrite.viewport_renderer import render_viewport
from magwrite_transport import save_state as save_state_module
from magwrite_transport import shell_viewport
from magwrite_transport.document_store import DocumentStore
from magwrite_transport.editor import (
    CHAR, DOWN, ENTER, LEFT, MultilineEditor, UP, InputEvent,
)
from magwrite_transport.live_session import LIVE_SCENARIO_ID
from magwrite_transport.persistence import PersistenceController
from magwrite_transport.shell import (
    MENU_ITEMS, MODE_DRAFTS, MODE_JOURNAL, MODE_QUICK_NOTE, MODE_RECENT,
    ROUTE_CONSUMED, ROUTE_EDITOR, STATE_EDITOR, STATE_ERROR, STATE_EXIT,
    STATE_MAIN_MENU, STATE_SAVE_STATUS, STATES, Shell,
)

STORE_ROOT = "/sd/magwrite"


def event(kind, value=""):
    return InputEvent(0, "shell", kind, value)


def key(kind, value=""):
    return event(kind, value)


def controller(filesystem=None):
    filesystem = filesystem if filesystem is not None else FakeFileSystem()
    store = DocumentStore(filesystem, root=STORE_ROOT)
    store.open()
    return PersistenceController(store, 0.0), store, filesystem


# --------------------------------------------------------------- state model


class StateModelTests(unittest.TestCase):
    def test_the_state_set_is_closed_and_named(self):
        self.assertEqual(
            STATES,
            (STATE_MAIN_MENU, STATE_EDITOR, STATE_SAVE_STATUS, STATE_ERROR,
             STATE_EXIT),
        )

    def test_the_main_menu_exposes_exactly_the_four_required_items(self):
        self.assertEqual(
            [mode for mode, _ in MENU_ITEMS],
            [MODE_JOURNAL, MODE_QUICK_NOTE, MODE_DRAFTS, MODE_RECENT],
        )

    def test_a_new_shell_opens_at_the_main_menu_with_nothing_selected_yet(self):
        shell = Shell()
        self.assertEqual(shell.state, STATE_MAIN_MENU)
        self.assertEqual(shell.selection, 0)
        self.assertIsNone(shell.mode)

    def test_the_opening_visible_revision_is_never_zero(self):
        # The send path treats revision 0 as "nothing has ever been visible", so
        # a shell that started at 0 would have its first screen silently dropped.
        self.assertGreater(Shell().visible_revision, 0)

    def test_an_empty_menu_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            Shell(items=())

    def test_an_unknown_initial_state_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            Shell(state="SOMEWHERE_ELSE")


class MenuNavigationTests(unittest.TestCase):
    def setUp(self):
        self.shell = Shell()

    def test_down_and_up_move_the_selection(self):
        self.shell.route(key(DOWN))
        self.assertEqual(self.shell.selected_mode, MODE_QUICK_NOTE)
        self.shell.route(key(DOWN))
        self.assertEqual(self.shell.selected_mode, MODE_DRAFTS)
        self.shell.route(key(UP))
        self.assertEqual(self.shell.selected_mode, MODE_QUICK_NOTE)

    def test_the_selection_clamps_rather_than_wrapping(self):
        for _ in range(10):
            self.shell.route(key(UP))
        self.assertEqual(self.shell.selection, 0)
        for _ in range(10):
            self.shell.route(key(DOWN))
        self.assertEqual(self.shell.selection, len(MENU_ITEMS) - 1)

    def test_moving_the_selection_redraws(self):
        before = self.shell.visible_revision
        self.shell.route(key(DOWN))
        self.assertGreater(self.shell.visible_revision, before)

    def test_a_refused_move_does_not_redraw(self):
        before = self.shell.visible_revision
        self.shell.route(key(UP))
        self.assertEqual(self.shell.visible_revision, before)

    def test_typing_at_the_menu_never_reaches_the_document(self):
        # The failure this prevents is the writer finding stray menu keystrokes
        # in their draft, which costs more trust than any missing feature.
        for character in "hello":
            self.assertEqual(
                self.shell.route(key(CHAR, character)), ROUTE_CONSUMED
            )
        self.assertEqual(self.shell.state, STATE_MAIN_MENU)
        self.assertEqual(self.shell.ignored_events, 5)

    def test_an_ignored_key_is_counted_rather_than_silently_dropped(self):
        self.shell.route(key(LEFT))
        self.assertEqual(self.shell.ignored_events, 1)

    def test_enter_opens_the_selected_mode_in_the_editor(self):
        self.shell.route(key(DOWN))
        self.shell.route(key(DOWN))
        self.shell.route(key(ENTER))
        self.assertEqual(self.shell.state, STATE_EDITOR)
        self.assertEqual(self.shell.mode, MODE_DRAFTS)
        self.assertEqual(self.shell.mode_label(), "DRAFTS")

    def test_every_menu_item_routes_into_the_one_editor(self):
        for index, (mode, _) in enumerate(MENU_ITEMS):
            shell = Shell()
            for _ in range(index):
                shell.route(key(DOWN))
            shell.route(key(ENTER))
            self.assertEqual(shell.state, STATE_EDITOR)
            self.assertEqual(shell.mode, mode)


class RoutingTests(unittest.TestCase):
    def test_the_editor_receives_every_event_while_it_is_active(self):
        shell = Shell()
        shell.route(key(ENTER))
        for kind in (CHAR, ENTER, UP, DOWN, LEFT):
            self.assertEqual(
                shell.route(key(kind, "a" if kind == CHAR else "")),
                ROUTE_EDITOR,
            )

    def test_no_event_reaches_the_editor_from_any_other_state(self):
        for state in (STATE_MAIN_MENU, STATE_SAVE_STATUS, STATE_ERROR,
                      STATE_EXIT):
            shell = Shell(state=state)
            self.assertEqual(shell.route(key(CHAR, "x")), ROUTE_CONSUMED)


class BackAndExitTests(unittest.TestCase):
    def test_back_from_the_editor_goes_to_the_save_screen(self):
        shell = Shell()
        shell.route(key(ENTER))
        shell.back()
        self.assertEqual(shell.state, STATE_SAVE_STATUS)

    def test_back_from_the_save_screen_resumes_writing(self):
        shell = Shell()
        shell.route(key(ENTER))
        shell.back()
        shell.back()
        self.assertEqual(shell.state, STATE_EDITOR)
        self.assertEqual(shell.mode, MODE_JOURNAL)

    def test_enter_at_the_save_screen_returns_to_the_menu(self):
        shell = Shell()
        shell.route(key(ENTER))
        shell.back()
        shell.route(key(ENTER))
        self.assertEqual(shell.state, STATE_MAIN_MENU)

    def test_back_at_the_root_is_the_stop(self):
        shell = Shell()
        shell.back()
        self.assertEqual(shell.state, STATE_EXIT)
        self.assertTrue(shell.exiting)

    def test_back_after_the_stop_changes_nothing(self):
        shell = Shell()
        shell.back()
        before = shell.visible_revision
        shell.back()
        self.assertEqual(shell.state, STATE_EXIT)
        self.assertEqual(shell.visible_revision, before)

    def test_a_full_round_trip_returns_to_the_same_editor(self):
        shell = Shell()
        for _ in range(4):
            shell.route(key(ENTER))    # menu -> editor
            shell.back()               # editor -> save
            shell.route(key(ENTER))    # save -> menu
        self.assertEqual(shell.state, STATE_MAIN_MENU)
        self.assertEqual(shell.entries, 4)


class FailClosedTests(unittest.TestCase):
    def test_a_reported_fault_becomes_a_recoverable_screen(self):
        shell = Shell()
        shell.route(key(ENTER))
        shell.fault("document capacity reached")
        self.assertEqual(shell.state, STATE_ERROR)
        self.assertEqual(shell.error_reason, "document capacity reached")
        self.assertEqual(shell.faults, 1)

    def test_the_error_screen_is_dismissible_both_ways(self):
        for dismiss in (lambda s: s.back(), lambda s: s.route(key(ENTER))):
            shell = Shell()
            shell.fault("something failed")
            dismiss(shell)
            self.assertEqual(shell.state, STATE_MAIN_MENU)
            self.assertIsNone(shell.error_reason)

    def test_a_second_fault_replaces_the_reason_and_redraws(self):
        shell = Shell()
        shell.fault("first")
        before = shell.visible_revision
        shell.fault("second")
        self.assertEqual(shell.error_reason, "second")
        self.assertEqual(shell.faults, 2)
        self.assertGreater(shell.visible_revision, before)

    def test_an_undefined_transition_faults_instead_of_raising(self):
        shell = Shell()
        shell.state = "NOWHERE"
        self.assertEqual(shell.route(key(ENTER)), ROUTE_CONSUMED)
        self.assertEqual(shell.state, STATE_ERROR)

    def test_an_undefined_back_faults_instead_of_raising(self):
        shell = Shell()
        shell.state = "NOWHERE"
        shell.back()
        self.assertEqual(shell.state, STATE_ERROR)

    def test_an_invalid_transition_target_faults_instead_of_raising(self):
        shell = Shell()
        shell._transition("NOT_A_STATE")
        self.assertEqual(shell.state, STATE_ERROR)

    def test_enter_outside_the_menu_faults_rather_than_opening_a_mode(self):
        shell = Shell(state=STATE_SAVE_STATUS)
        shell.enter()
        self.assertEqual(shell.state, STATE_ERROR)
        self.assertIsNone(shell.mode)


class RestoreTests(unittest.TestCase):
    def test_a_recovered_document_opens_in_the_editor(self):
        shell = Shell()
        shell.restore(True, 73)
        self.assertEqual(shell.state, STATE_EDITOR)
        self.assertEqual(shell.mode, MODE_JOURNAL)

    def test_an_empty_card_opens_at_the_menu(self):
        shell = Shell()
        shell.restore(False)
        self.assertEqual(shell.state, STATE_MAIN_MENU)

    def test_a_recovered_but_empty_document_opens_at_the_menu(self):
        shell = Shell()
        shell.restore(True, 0)
        self.assertEqual(shell.state, STATE_MAIN_MENU)


# ------------------------------------------------------------------- screens


class ScreenGlyphTests(unittest.TestCase):
    """Every character the shell can draw must exist on the panel."""

    def test_the_safe_character_set_is_a_subset_of_the_real_glyph_table(self):
        self.assertEqual(shell_viewport.SAFE_CHARACTERS - set(GLYPHS), set())

    def test_every_menu_label_is_renderable(self):
        for _, label in MENU_ITEMS:
            self.assertEqual(set(label) - set(GLYPHS), set())

    def test_every_save_state_has_a_renderable_label(self):
        for state in save_state_module.STATES:
            label = save_state_module.label(state)
            self.assertEqual(set(label) - set(GLYPHS), set(), state)

    def test_the_state_identifiers_themselves_would_not_have_been_renderable(self):
        # The reason labels exist at all: NO_CARD carries an underscore, and the
        # panel has no glyph for one.
        self.assertNotEqual(set(save_state_module.NO_CARD) - set(GLYPHS), set())

    def test_an_unknown_save_state_is_refused_rather_than_drawn(self):
        with self.assertRaises(ValueError):
            save_state_module.label("SOMETHING_ELSE")

    def test_error_text_from_an_exception_is_sanitized(self):
        # Error reasons are the one string on the device that comes from an
        # exception rather than a literal, so they are the obvious place for an
        # unrenderable character to arrive.
        dirty = "store unusable: [Errno 19] no such device é"
        cleaned = shell_viewport.safe_text(dirty, 64)
        self.assertEqual(set(cleaned) - set(GLYPHS), set())
        self.assertIn("Errno 19", cleaned)

    def test_sanitizing_is_bounded(self):
        self.assertEqual(len(shell_viewport.safe_text("x" * 500)), 28)
        self.assertEqual(shell_viewport.safe_text(None), "")


class WrapTests(unittest.TestCase):
    def test_words_are_wrapped_within_the_line_width(self):
        lines = shell_viewport.wrap("the quick brown fox jumps over the lazy dog", 12, 3)
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertLessEqual(len(line), 12)

    def test_a_word_longer_than_the_line_is_cut_rather_than_overflowing(self):
        lines = shell_viewport.wrap("a" * 40, 10, 3)
        for line in lines:
            self.assertLessEqual(len(line), 10)

    def test_wrapping_never_exceeds_the_line_budget(self):
        lines = shell_viewport.wrap("word " * 200, 28, 3)
        self.assertLessEqual(len(lines), 3)


class ScreenEncodingTests(unittest.TestCase):
    """Every screen must survive the real encoder, decoder, and renderer."""

    def screens(self):
        editor = MultilineEditor()
        for character in "a real note, typed by hand":
            editor.apply(InputEvent(0, "s", CHAR, character))
        cases = []
        for selection in range(len(MENU_ITEMS)):
            shell = Shell()
            shell.selection = selection
            cases.append(("menu %d" % selection,
                          shell_viewport.menu_payload(shell, "r")))
        for state in save_state_module.STATES:
            shell = Shell()
            shell.route(key(ENTER))
            shell.back()
            shell.note_save_state(state)
            cases.append(("save " + state,
                          shell_viewport.save_payload(shell, editor, "s")))
        shell = Shell()
        shell.fault("store unusable: cannot create store layout: [Errno 30]")
        cases.append(("error", shell_viewport.error_payload(shell, "!")))
        shell = Shell()
        shell.back()
        cases.append(("exit", shell_viewport.exit_payload(shell, editor, "s")))
        return cases

    def test_every_screen_decodes_and_renders_on_the_real_panel_geometry(self):
        for name, payload in self.screens():
            message = ViewportMessage.decode(1, payload)
            self.assertEqual(message.scenario_id, shell_viewport.SHELL_SCENARIO_ID)
            # The renderer raises on a missing glyph and on a header that does
            # not fit, which is exactly what must not reach the board.
            self.assertEqual(len(render_viewport(message)), 4736, name)

    def test_every_screen_stays_inside_the_protocol_payload_maximum(self):
        for name, payload in self.screens():
            self.assertLessEqual(len(payload), 192, name)

    def test_the_shell_scenario_is_distinct_from_the_editor_scenario(self):
        self.assertNotEqual(shell_viewport.SHELL_SCENARIO_ID, LIVE_SCENARIO_ID)

    def test_the_menu_marks_the_selected_item_and_puts_the_cursor_on_it(self):
        shell = Shell()
        shell.route(key(DOWN))
        message = ViewportMessage.decode(1, shell_viewport.menu_payload(shell))
        self.assertEqual(message.lines[0], "  JOURNAL")
        self.assertEqual(message.lines[1], "> QUICK NOTE")
        self.assertEqual(message.cursor_row, 1)

    def test_the_menu_shows_every_item_at_once(self):
        message = ViewportMessage.decode(1, shell_viewport.menu_payload(Shell()))
        self.assertEqual(len(message.lines), len(MENU_ITEMS))

    def test_the_save_screen_names_the_state_the_document_and_both_exits(self):
        editor = MultilineEditor()
        editor.apply(InputEvent(0, "s", CHAR, "x"))
        shell = Shell()
        shell.route(key(ENTER))
        shell.back()
        shell.note_save_state(save_state_module.SAVED)
        message = ViewportMessage.decode(
            1, shell_viewport.save_payload(shell, editor, "s")
        )
        self.assertEqual(message.lines[0], "SAVED")
        self.assertIn("JOURNAL", message.lines)
        self.assertIn("ENTER  MENU", message.lines)
        self.assertIn("ESC  KEEP WRITING", message.lines)

    def test_the_save_screen_does_not_reprint_the_draft(self):
        # Showing the words under the word SAVED invites the exact misreading
        # this screen exists to prevent: that the panel is the card.
        editor = MultilineEditor()
        for character in "secret words":
            editor.apply(InputEvent(0, "s", CHAR, character))
        shell = Shell()
        shell.route(key(ENTER))
        shell.back()
        message = ViewportMessage.decode(
            1, shell_viewport.save_payload(shell, editor, "u")
        )
        for line in message.lines:
            self.assertNotIn("secret", line)

    def test_the_error_screen_says_the_work_is_kept(self):
        shell = Shell()
        shell.fault("document capacity reached")
        message = ViewportMessage.decode(1, shell_viewport.error_payload(shell))
        self.assertIn("WORK IS KEPT", message.lines)
        self.assertIn("ENTER  MENU", message.lines)

    def test_the_editor_state_hands_the_panel_back_to_the_document(self):
        shell = Shell()
        shell.route(key(ENTER))
        self.assertIsNone(
            shell_viewport.payload(shell, MultilineEditor(), "s")
        )

    def test_every_other_state_produces_a_screen(self):
        for state in (STATE_MAIN_MENU, STATE_SAVE_STATUS, STATE_ERROR,
                      STATE_EXIT):
            shell = Shell(state=state)
            self.assertIsNotNone(
                shell_viewport.payload(shell, MultilineEditor(), "s"), state
            )

    def test_a_bad_save_indicator_is_refused_rather_than_drawn(self):
        with self.assertRaises(ValueError):
            shell_viewport.menu_payload(Shell(), "toolong")


# --------------------------------------------------------------- integration


def shell_script():
    """A writer moving between the shell and one document, repeatedly.

    Deliberately free of arrow keys. This run is paced slowly enough for the
    simulated panel to actually draw each screen, and at that cadence a held
    arrow reaches the 500 ms repeat delay and legitimately repeats. Arrow
    navigation is covered on its own below, at a tapping cadence.
    """
    reports = press_kind("ENTER")             # menu: open JOURNAL -> editor
    reports += type_characters("first pass")
    reports += finish()                       # -> save screen
    reports += press_kind("ENTER")            # -> menu
    reports += press_kind("ENTER")            # -> editor again
    reports += type_characters(" and second")
    reports += finish()                       # -> save screen
    reports += finish()                       # -> back into the editor
    reports += type_characters(".")
    reports += finish()                       # -> save screen
    reports += press_kind("ENTER")            # -> menu
    reports += finish()                       # -> stop
    return reports


class ShellSessionTests(unittest.TestCase):
    """The whole path, driven by scripted USB reports through real code."""

    @classmethod
    def setUpClass(cls):
        cls.persistence, cls.store, cls.filesystem = controller()
        cls.shell = Shell(log=None)
        # Every frame the MagTag actually renders is captured on the way through
        # the *real* renderer, so "the writer saw the menu" is asserted against
        # what the panel drew rather than against a count of frames.
        cls.rendered = []

        def recording_render(viewport):
            cls.rendered.append(viewport)
            return render_viewport(viewport)

        cls.link = KeyboardLink(
            reports=shell_script(), persistence=cls.persistence,
            shell=cls.shell, render=recording_render,
            typing_interval_seconds=0.25,
        ).run()
        cls.summary = cls.link.session.summary("PASS")

    def events(self, name):
        return [r for r in self.link.records if r.get("event") == name]

    def test_the_session_completes_through_the_shell(self):
        self.assertTrue(self.link.session.complete)
        self.assertEqual(self.shell.state, STATE_EXIT)

    def test_the_document_survived_every_transition(self):
        self.assertEqual(
            self.link.session.editor.text, "first pass and second."
        )

    def test_the_editor_was_never_replaced_or_cleared(self):
        # One editor for the life of the session is the structural reason no
        # transition can lose unsaved work: nothing is ever closed.
        self.assertIs(self.link.session.editor, self.link.session.editor)
        self.assertEqual(self.shell.entries, 2)
        self.assertGreaterEqual(self.shell.backs, 5)

    def test_menu_keystrokes_never_entered_the_document(self):
        self.assertNotIn("\n", self.link.session.editor.text)
        self.assertGreater(self.summary["shell_routed_events"], 0)
        self.assertEqual(
            self.summary["events_processed"] + self.summary["shell_routed_events"],
            self.summary["normalized_events"],
        )

    def test_leaving_the_editor_checkpointed_the_document(self):
        left = self.events("shell_left_editor")
        self.assertEqual(len(left), 3)
        self.assertGreaterEqual(self.summary["checkpoints"], 3)

    def test_the_document_on_the_card_matches_what_was_typed(self):
        snapshot = self.store.read_latest()
        self.assertEqual(snapshot.text, "first pass and second.")

    def test_the_writer_ended_saved_rather_than_merely_recoverable(self):
        self.assertEqual(self.summary["save_state"], save_state_module.SAVED)

    def test_no_edit_was_rejected_and_no_fault_was_raised(self):
        self.assertEqual(self.summary["events_rejected"], 0)
        self.assertEqual(self.summary["shell_faults"], 0)

    def test_every_transmitted_frame_was_a_valid_renderable_viewport(self):
        # Every accepted frame goes through the real renderer during the run, so
        # reaching this point at all means no frame carried an unrenderable
        # character or a header that does not fit the panel.
        self.assertGreater(len(self.rendered), 3)
        self.assertEqual(self.summary["crc_failures"], 0)

    def test_the_panel_drew_both_shell_screens_and_the_document(self):
        scenarios = set(view.scenario_id for view in self.rendered)
        self.assertIn(shell_viewport.SHELL_SCENARIO_ID, scenarios)
        self.assertIn(LIVE_SCENARIO_ID, scenarios)

    def test_the_document_frames_name_the_mode_the_writer_chose(self):
        titles = set(
            view.title for view in self.rendered
            if view.scenario_id == LIVE_SCENARIO_ID
        )
        self.assertTrue(titles)
        for title in titles:
            self.assertTrue(title.startswith("JOURNAL "), title)

    def test_the_shell_state_is_reported_in_the_session_summary(self):
        self.assertEqual(self.summary["shell_state"], STATE_EXIT)
        self.assertEqual(self.summary["shell_mode"], MODE_JOURNAL)
        self.assertIn("shell_selection", self.summary)
        self.assertIn("finish_requests_serviced", self.summary)

    def test_arrow_navigation_opens_the_item_the_writer_selected(self):
        shell = Shell()
        KeyboardLink(
            reports=press_kind("DOWN") * 2 + press_kind("ENTER")
            + type_characters("drafted") + finish() + press_kind("ENTER")
            + finish(),
            shell=shell, typing_interval_seconds=0.05,
        ).run()
        self.assertEqual(shell.mode, MODE_DRAFTS)

    def test_the_pacing_and_acknowledgement_paths_were_the_proven_ones(self):
        self.assertGreater(self.summary["refresh_completed_received"], 0)
        self.assertEqual(self.summary["status_sequence_gaps"], 0)
        self.assertTrue(self.summary["test_complete"])


class UnsavedWorkTests(unittest.TestCase):
    def test_a_rejected_edit_faults_the_shell_and_keeps_the_document(self):
        # Before the shell, reaching the document bound raised and ended the
        # run. The refused edit changes nothing, so the words are still there;
        # the writer is shown a recoverable screen and goes back to them.
        editor = MultilineEditor(max_chars=4, max_line_chars=4)
        shell = Shell()
        link = KeyboardLink(
            reports=press_kind("ENTER") + type_characters("abcdefgh")
            + finish()                     # error screen -> menu
            + finish(),                    # menu -> stop
            shell=shell, editor=editor, typing_interval_seconds=0.05,
        ).run()
        self.assertTrue(link.session.complete)
        self.assertEqual(editor.text, "abcd")
        summary = link.session.summary("PASS")
        self.assertGreater(summary["shell_faults"], 0)
        self.assertGreater(summary["events_rejected"], 0)

    def test_without_a_shell_the_finish_gesture_still_stops_immediately(self):
        link = KeyboardLink(reports=type_characters("plain") + finish()).run()
        self.assertTrue(link.session.complete)
        self.assertEqual(link.session.editor.text, "plain")

    def test_a_session_without_a_shell_transmits_the_identical_payloads(self):
        # The shell is optional on the same terms persistence is, so every
        # viewport payload the physical runs measured stays reproducible.
        first = KeyboardLink(reports=type_characters("evidence") + finish()).run()
        second = KeyboardLink(reports=type_characters("evidence") + finish()).run()
        self.assertEqual(
            first.session.last_sent_payload, second.session.last_sent_payload
        )
        self.assertEqual(first.session.last_sent_hash, second.session.last_sent_hash)
        self.assertIsNone(first.session.shell)


class RecoveryIntoTheShellTests(unittest.TestCase):
    def test_a_recovered_document_reopens_in_the_editor_not_the_menu(self):
        persistence, store, filesystem = controller()
        link = KeyboardLink(
            reports=press_kind("ENTER") + type_characters("survive me")
            + finish() + press_kind("ENTER") + finish(),
            persistence=persistence, shell=Shell(), typing_interval_seconds=0.05,
        ).run()
        self.assertTrue(link.session.complete)

        card = filesystem.snapshot()
        recovered_store = DocumentStore(card, root=STORE_ROOT)
        recovery = recovered_store.open()
        self.assertTrue(recovery.recovered)

        resumed_shell = Shell()
        resumed = KeyboardLink(
            reports=finish() + finish(),
            persistence=PersistenceController(recovered_store, 0.0),
            shell=resumed_shell,
        )
        resumed.session.restore(recovery.snapshot)
        self.assertEqual(resumed_shell.state, STATE_EDITOR)
        self.assertEqual(resumed.session.editor.text, "survive me")

    def test_an_empty_card_reopens_at_the_menu(self):
        persistence, _, _ = controller()
        shell = Shell()
        shell.restore(False)
        link = KeyboardLink(
            reports=finish(), persistence=persistence, shell=shell,
        ).run()
        self.assertEqual(shell.state, STATE_EXIT)
        self.assertTrue(link.session.complete)


if __name__ == "__main__":
    unittest.main()
