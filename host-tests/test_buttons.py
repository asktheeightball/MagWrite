"""MagTag buttons as the primary shell controls. V1.5.

Four layers, because four different things can break, and each layer is the
cheapest place to catch its own family of failure.

* ``ButtonPad`` is driven against a simulated contact that actually bounces, so
  debounce and duplicate suppression are asserted against the physical behaviour
  they exist for rather than against a clean square edge nobody's hardware
  produces;
* the two boards' action tables and the wire payload are asserted for parity,
  because the boards share no import and a renumbering on one side would be a
  silent misinterpretation on the other rather than an error;
* ``Shell.button`` is driven directly, including in every state where a button
  must do nothing;
* the whole path is then driven end to end -- real pad, real encoder, real frame,
  real parser, real acknowledgement tracker, real shell, real editor -- so the
  claim "the intended product flow works from the buttons" is made against the
  code the boards run rather than against a mock of it.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

import config as magtag_config

from fake_filesystem import FakeFileSystem
from keyboard_simulator import (
    KeyboardLink, SimulatedButton, finish, type_characters,
)
from magwrite import buttons as magtag_buttons
from magwrite.status_message import decode_status, encode_status
from magwrite.uart_protocol import BUTTON_EVENT, encode_frame
from magwrite_transport import button_input
from magwrite_transport.button_input import ButtonInbox
from magwrite_transport.document_store import DocumentStore
from magwrite_transport.persistence import PersistenceController
from magwrite_transport.shell import (
    BUTTON_DOWN, BUTTON_MENU, BUTTON_SELECT, BUTTON_UP, MODE_DRAFTS,
    MODE_JOURNAL, MODE_QUICK_NOTE, STATE_DRAFTS, STATE_EDITOR, STATE_ERROR,
    STATE_EXIT, STATE_MAIN_MENU, Shell,
)

STORE_ROOT = "/sd/magwrite"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def pad(clock, **options):
    """A four-button pad over four independently controllable contacts."""
    contacts = {
        action: SimulatedButton(clock)
        for action in magtag_buttons.ACTIONS
    }
    return magtag_buttons.ButtonPad(
        [(action, contacts[action]) for action in magtag_buttons.ACTIONS],
        **options
    ), contacts


def run(pad_, clock, seconds, step=0.005):
    """Advance the clock, polling as the display loop does. Returns events."""
    events = []
    end = clock.now + seconds
    while clock.now < end:
        events.extend(pad_.poll(clock.now))
        clock.now += step
    return events


# ------------------------------------------------------------------ the pad


class ButtonPadTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.pad, self.contacts = pad(self.clock)

    def test_a_clean_press_produces_exactly_one_event(self):
        self.contacts[magtag_buttons.DOWN].press(0.1)
        events = run(self.pad, self.clock, 0.5)
        self.assertEqual([e[0] for e in events], [magtag_buttons.DOWN])

    def test_a_bouncing_contact_still_produces_exactly_one_event(self):
        # The failure this prevents: contact chatter read as several presses,
        # which walks the menu selection past what the writer chose.
        self.contacts[magtag_buttons.UP].press(0.1)
        events = run(self.pad, self.clock, 0.5)
        self.assertEqual(len(events), 1)
        self.assertGreater(self.pad.bounces_rejected, 0)

    def test_a_held_button_never_repeats(self):
        # A four-item menu on a panel that takes about a second to redraw:
        # auto-repeat could only overshoot something the writer cannot see yet.
        self.contacts[magtag_buttons.DOWN].press(0.1, seconds=3.0)
        events = run(self.pad, self.clock, 4.0)
        self.assertEqual(len(events), 1)

    def test_release_chatter_is_not_read_as_a_second_press(self):
        # The specific reason debounce is stability rather than a press lockout:
        # the release edge bounces too, and it bounces after any lockout expired.
        self.contacts[magtag_buttons.SELECT].press(0.1, seconds=0.6)
        events = run(self.pad, self.clock, 1.2)
        self.assertEqual(len(events), 1)

    def test_two_deliberate_presses_produce_two_events(self):
        self.contacts[magtag_buttons.DOWN].press(0.1)
        self.contacts[magtag_buttons.DOWN].press(1.0)
        events = run(self.pad, self.clock, 1.6)
        self.assertEqual(len(events), 2)

    def test_a_second_press_inside_the_minimum_interval_is_suppressed(self):
        self.contacts[magtag_buttons.DOWN].press(0.1, seconds=0.05)
        self.contacts[magtag_buttons.DOWN].press(0.2, seconds=0.05)
        events = run(self.pad, self.clock, 1.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(self.pad.repeats_suppressed, 1)

    def test_the_minimum_interval_is_per_button_not_global(self):
        # Down then Select in quick succession is an ordinary thing to do; it
        # must not be mistaken for a bouncing Down.
        self.contacts[magtag_buttons.DOWN].press(0.1, seconds=0.05)
        self.contacts[magtag_buttons.SELECT].press(0.2, seconds=0.05)
        events = run(self.pad, self.clock, 1.0)
        self.assertEqual(
            [e[0] for e in events], [magtag_buttons.DOWN, magtag_buttons.SELECT]
        )

    def test_ordinals_are_monotonic_across_every_button(self):
        self.contacts[magtag_buttons.MENU].press(0.1)
        self.contacts[magtag_buttons.UP].press(0.6)
        self.contacts[magtag_buttons.DOWN].press(1.1)
        ordinals = [e[1] for e in run(self.pad, self.clock, 1.8)]
        self.assertEqual(ordinals, [1, 2, 3])

    def test_one_poll_returns_at_most_one_event_per_button(self):
        for action in magtag_buttons.ACTIONS:
            self.contacts[action].press(0.1)
        events = run(self.pad, self.clock, 0.5)
        self.assertEqual(len(events), len(magtag_buttons.ACTIONS))

    def test_a_pad_with_no_buttons_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            magtag_buttons.ButtonPad([])

    def test_an_unknown_action_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            magtag_buttons.ButtonPad([("PRINT", lambda: False)])

    def test_the_timestamp_fits_the_wire_field(self):
        self.clock.now = 4_000_000.0
        self.contacts[magtag_buttons.UP].press(self.clock.now + 0.1)
        events = run(self.pad, self.clock, 0.5)
        self.assertLessEqual(events[0][2], 0xFFFFFFFF)


# ------------------------------------------------------------ the two boards


class ParityTests(unittest.TestCase):
    """The boards share no import, so the tables are asserted rather than reused."""

    def test_the_action_names_agree(self):
        self.assertEqual(magtag_buttons.ACTIONS, button_input.ACTIONS)

    def test_the_wire_codes_agree(self):
        self.assertEqual(magtag_buttons.ACTION_CODES, button_input.ACTION_CODES)

    def test_the_shell_re_exports_the_same_four_actions(self):
        self.assertEqual(
            (BUTTON_MENU, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT),
            button_input.ACTIONS,
        )

    def test_the_magtag_config_mirrors_the_button_module(self):
        # Same rule as pacing and persistence: config may mirror the module that
        # owns a constant, never disagree with it.
        self.assertEqual(
            magtag_config.BUTTON_DEBOUNCE_SECONDS,
            magtag_buttons.DEBOUNCE_SECONDS,
        )
        self.assertEqual(
            magtag_config.BUTTON_MINIMUM_INTERVAL_SECONDS,
            magtag_buttons.MINIMUM_INTERVAL_SECONDS,
        )

    def test_the_config_names_a_pin_alias_for_every_action(self):
        for setting in ("BUTTON_MENU_PIN_ALIAS", "BUTTON_UP_PIN_ALIAS",
                        "BUTTON_DOWN_PIN_ALIAS", "BUTTON_SELECT_PIN_ALIAS"):
            self.assertTrue(getattr(magtag_config, setting), setting)

    def test_a_button_payload_round_trips_through_the_real_frame(self):
        fields = {"action_code": magtag_buttons.ACTION_CODES[magtag_buttons.UP],
                  "ordinal": 9, "pressed_ms": 1234}
        payload = encode_status(BUTTON_EVENT, fields)
        self.assertEqual(decode_status(BUTTON_EVENT, payload), fields)
        # And inside a real frame, so the type is one the parser accepts.
        wire = encode_frame(BUTTON_EVENT, 1, 0, payload)
        self.assertEqual(wire[3], BUTTON_EVENT)

    def test_a_malformed_button_payload_is_refused(self):
        with self.assertRaises(ValueError):
            decode_status(BUTTON_EVENT, b"")


# -------------------------------------------------------------- the inbox


class ButtonInboxTests(unittest.TestCase):
    def setUp(self):
        self.inbox = ButtonInbox()

    def offer(self, action, ordinal):
        return self.inbox.offer({
            "action_code": button_input.ACTION_CODES[action],
            "ordinal": ordinal, "pressed_ms": 0,
        })

    def test_an_accepted_press_becomes_one_pending_action(self):
        self.assertEqual(self.offer(BUTTON_DOWN, 1), BUTTON_DOWN)
        self.assertEqual(self.inbox.take(), (BUTTON_DOWN, 1))
        self.assertIsNone(self.inbox.take())

    def test_a_replayed_ordinal_is_refused_and_counted(self):
        # The transport already rejects a duplicate *frame*; a resynchronisation
        # after line noise can still redeliver one, and a press applied twice
        # moves the selection past what the writer saw.
        self.offer(BUTTON_DOWN, 1)
        self.assertIsNone(self.offer(BUTTON_DOWN, 1))
        self.assertEqual(self.inbox.duplicates, 1)

    def test_an_out_of_order_ordinal_is_refused(self):
        self.offer(BUTTON_DOWN, 5)
        self.assertIsNone(self.offer(BUTTON_UP, 4))
        self.assertEqual(self.inbox.duplicates, 1)

    def test_an_unknown_action_code_is_refused_rather_than_guessed(self):
        self.assertIsNone(self.inbox.offer(
            {"action_code": 99, "ordinal": 1, "pressed_ms": 0}
        ))
        self.assertEqual(self.inbox.unknown, 1)
        self.assertEqual(len(self.inbox), 0)

    def test_the_queue_is_bounded_and_drops_the_oldest(self):
        for ordinal in range(1, self.inbox.capacity + 3):
            self.offer(BUTTON_DOWN, ordinal)
        self.assertEqual(len(self.inbox), self.inbox.capacity)
        self.assertEqual(self.inbox.dropped, 2)
        # The newest press survived: a backlog is stale intention.
        self.assertEqual(
            self.inbox.pending[-1][1], self.inbox.capacity + 2
        )

    def test_a_zero_capacity_inbox_is_refused(self):
        with self.assertRaises(ValueError):
            ButtonInbox(capacity=0)

    def test_every_refusal_is_reported(self):
        self.offer(BUTTON_UP, 1)
        self.inbox.offer({"action_code": 99, "ordinal": 2, "pressed_ms": 0})
        summary = self.inbox.summary()
        self.assertEqual(summary["button_events_received"], 2)
        self.assertEqual(summary["button_events_accepted"], 1)
        self.assertEqual(summary["button_events_unknown"], 1)


# --------------------------------------------------------------- the shell


class ShellButtonTests(unittest.TestCase):
    def setUp(self):
        self.shell = Shell()

    def test_up_and_down_move_the_menu_selection(self):
        self.shell.button(BUTTON_DOWN)
        self.assertEqual(self.shell.selected_mode, MODE_QUICK_NOTE)
        self.shell.button(BUTTON_UP)
        self.assertEqual(self.shell.selected_mode, MODE_JOURNAL)

    def test_select_opens_the_highlighted_item(self):
        self.shell.button(BUTTON_DOWN)
        self.shell.button(BUTTON_SELECT)
        self.assertEqual(self.shell.state, STATE_EDITOR)
        self.assertEqual(self.shell.mode, MODE_QUICK_NOTE)

    def test_the_selection_clamps_from_buttons_too(self):
        for _ in range(10):
            self.shell.button(BUTTON_DOWN)
        self.assertEqual(self.shell.selection, len(self.shell.items) - 1)

    def test_the_menu_button_leaves_the_drafts_list(self):
        self.shell.button(BUTTON_DOWN)
        self.shell.button(BUTTON_DOWN)
        self.shell.button(BUTTON_SELECT)
        self.assertEqual(self.shell.state, STATE_DRAFTS)
        self.shell.button(BUTTON_MENU)
        self.assertEqual(self.shell.state, STATE_MAIN_MENU)

    def test_the_menu_button_dismisses_the_error_screen(self):
        self.shell.fault("something failed")
        self.shell.button(BUTTON_MENU)
        self.assertEqual(self.shell.state, STATE_MAIN_MENU)
        self.assertIsNone(self.shell.error_reason)

    def test_select_also_dismisses_the_error_screen(self):
        self.shell.fault("something failed")
        self.shell.button(BUTTON_SELECT)
        self.assertEqual(self.shell.state, STATE_MAIN_MENU)

    def test_the_menu_button_at_the_menu_does_not_stop_the_session(self):
        # The one place buttons deliberately differ from Escape. A thumb on a
        # bezel must never be able to end a writing session; a writer who pressed
        # Escape twice at the root meant it.
        for _ in range(5):
            self.shell.button(BUTTON_MENU)
        self.assertEqual(self.shell.state, STATE_MAIN_MENU)
        self.assertFalse(self.shell.exiting)
        self.assertEqual(self.shell.buttons_ignored, 5)

    def test_no_button_reaches_the_document(self):
        self.shell.button(BUTTON_SELECT)
        self.assertEqual(self.shell.state, STATE_EDITOR)
        before = self.shell.visible_revision
        for action in (BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT):
            self.shell.button(action)
        self.assertEqual(self.shell.state, STATE_EDITOR)
        self.assertEqual(self.shell.visible_revision, before)
        self.assertEqual(self.shell.buttons_ignored, 3)

    def test_an_unknown_action_faults_rather_than_raising(self):
        self.shell.button("PRINT")
        self.assertEqual(self.shell.state, STATE_ERROR)

    def test_a_button_after_the_stop_changes_nothing(self):
        self.shell.back()
        self.assertEqual(self.shell.state, STATE_EXIT)
        for action in (BUTTON_MENU, BUTTON_UP, BUTTON_SELECT):
            self.shell.button(action)
        self.assertEqual(self.shell.state, STATE_EXIT)

    def test_button_actions_are_counted_in_the_summary(self):
        self.shell.button(BUTTON_DOWN)
        self.shell.button(BUTTON_SELECT)
        summary = self.shell.summary()
        self.assertEqual(summary["shell_button_actions"], 2)
        self.assertEqual(summary["shell_buttons_ignored"], 0)


# --------------------------------------------------------------- end to end


def controller():
    filesystem = FakeFileSystem()
    store = DocumentStore(filesystem, root=STORE_ROOT)
    store.open()
    return PersistenceController(store, 0.0), store, filesystem


class ButtonSessionTests(unittest.TestCase):
    """The intended product flow, driven entirely from the four buttons."""

    @classmethod
    def setUpClass(cls):
        cls.persistence, cls.store, cls.filesystem = controller()
        cls.shell = Shell()
        cls.link = KeyboardLink(
            # The keyboard writes and does nothing else. Every navigation below
            # is a physical button, which is the requirement of the phase: the
            # product flow must work without the keyboard's shell keys.
            reports=type_characters("written with the keyboard"),
            persistence=cls.persistence, shell=cls.shell,
            typing_interval_seconds=0.05, typing_start_seconds=1.0,
            buttons=True,
        )
        contacts = cls.link.contacts
        contacts[BUTTON_SELECT].press(0.5)   # menu -> JOURNAL in the editor
        #                      typing runs from 1.0 and is well done by 9.0
        contacts[BUTTON_MENU].press(9.0)     # editor -> menu, checkpointed
        contacts[BUTTON_DOWN].press(10.0)    # -> QUICK NOTE
        contacts[BUTTON_DOWN].press(11.0)    # -> DRAFTS
        contacts[BUTTON_SELECT].press(12.0)  # -> the drafts list
        contacts[BUTTON_MENU].press(13.0)    # -> back to the menu
        contacts[BUTTON_UP].press(14.0)      # -> QUICK NOTE
        contacts[BUTTON_UP].press(15.0)      # -> JOURNAL
        contacts[BUTTON_SELECT].press(16.0)  # -> back into the document
        cls.link.run_until(18.0)
        cls.summary = cls.link.session.summary("COMPLETE")

    def events(self, name):
        return [r for r in self.link.records if r.get("event") == name]

    def test_every_press_reached_the_fruit_jam_exactly_once(self):
        self.assertEqual(self.summary["button_frames_received"], 9)
        self.assertEqual(self.summary["button_events_accepted"], 9)
        self.assertEqual(self.summary["button_events_duplicate"], 0)
        self.assertEqual(self.summary["button_events_dropped"], 0)
        self.assertEqual(self.summary["button_actions_applied"], 9)

    def test_the_buttons_walked_the_menu_and_opened_the_drafts_list(self):
        entered = [r["to"] for r in self.events("shell_button_applied")]
        self.assertIn(STATE_DRAFTS, entered)
        self.assertIn(STATE_EDITOR, entered)
        self.assertIn(STATE_MAIN_MENU, entered)

    def test_a_mode_was_opened_and_left_and_reopened_from_buttons_alone(self):
        self.assertEqual(self.shell.state, STATE_EDITOR)
        self.assertEqual(self.shell.mode, MODE_JOURNAL)
        self.assertGreaterEqual(self.shell.entries, 3)

    def test_leaving_the_document_with_a_button_checkpointed_it(self):
        left = self.events("shell_left_editor")
        self.assertTrue(left)
        for record in left:
            self.assertEqual(record["save_action"], "CHECKPOINTED")

    def test_no_text_was_lost_and_none_was_added(self):
        # The whole risk of a control surface: a button that reaches the
        # document. The text is exactly what the keyboard typed.
        self.assertEqual(
            self.link.session.editor.text, "written with the keyboard"
        )
        self.assertEqual(self.summary["events_rejected"], 0)
        self.assertEqual(self.summary["shell_faults"], 0)

    def test_the_card_holds_what_was_typed(self):
        self.assertEqual(
            self.store.read_latest().text, "written with the keyboard"
        )

    def test_the_display_acknowledgements_were_unaffected(self):
        # Buttons share the return channel with the acknowledgements. The point
        # of that decision is that neither starves the other.
        self.assertGreater(self.summary["refresh_completed_received"], 0)
        self.assertEqual(self.summary["status_sequence_gaps"], 0)
        self.assertEqual(self.summary["crc_failures"], 0)
        self.assertEqual(self.summary["status_duplicates"], 0)


class ButtonsWithoutAShellTests(unittest.TestCase):
    def test_button_frames_are_counted_even_with_no_shell_to_apply_them(self):
        # "The MagTag is sending and the Fruit Jam is ignoring" has to be a
        # distinguishable state on the bench, so the frames are counted rather
        # than dropped unrecorded.
        link = KeyboardLink(
            reports=type_characters("plain") + finish(), buttons=True,
        )
        link.contacts[BUTTON_DOWN].press(0.5)
        link.run()
        summary = link.session.summary("COMPLETE")
        self.assertEqual(link.session.editor.text, "plain")
        self.assertGreaterEqual(summary["button_events_accepted"], 1)
        self.assertEqual(summary["button_actions_applied"], 0)


if __name__ == "__main__":
    unittest.main()
