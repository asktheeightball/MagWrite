"""Essential keyboard behaviour, end to end, and the device layout rule.

``test_hid_keyboard`` proves translation and ``test_usb_keyboard_adapter``
proves the adapter. This module proves the *writer-visible* result: a real
report stream is pushed through the real adapter into the real authoritative
editor, and the resulting document is asserted. A key is only counted as
working here if pressing it changes the document the way a person would expect.

It also owns the device layout rule, which exists because one specific keyboard
does not follow the HID specification. See ``keyboard_layout`` for the measured
evidence; the tests below pin both halves of the rule — that the TH40 is fixed,
and that nobody else's behaviour moved.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from keyboard_simulator import (
    FakeKeyboardBackend, press_release, report, type_characters,
    type_characters_overlapping,
)
from magwrite.test_pattern import GLYPHS
from magwrite_transport.editor import (
    BoundedEventQueue, EditRejected, MultilineEditor,
)
from magwrite_transport.editor_viewport import EditorViewport
from magwrite_transport.hid_keyboard import HidKeyboardTranslator
from magwrite_transport.hid_keymap import (
    MODIFIER_LEFT_SHIFT, MODIFIER_RIGHT_SHIFT, REPEATABLE_KINDS,
    USAGE_APPLICATION, USAGE_CAPS_LOCK, USAGE_ESCAPE, translate,
)
from magwrite_transport.keyboard_layout import (
    AUTO, EPOMAKER_TH40, LAYOUTS, LAYOUTS_BY_NAME, STANDARD,
    USAGE_APOSTROPHE_AND_QUOTE, USAGE_EQUALS_AND_PLUS, DeviceLayout,
    layout_for, normalize_id, resolve,
)
from magwrite_transport.keyboard_repeat import REPEAT_DELAY_MS, REPEAT_INTERVAL_MS
from magwrite_transport.usb_keyboard_adapter import UsbKeyboardAdapter

USAGE_APOSTROPHE = 0x34
USAGE_ENTER = 0x28
USAGE_BACKSPACE = 0x2A
USAGE_DELETE = 0x4C
USAGE_HOME = 0x4A
USAGE_END = 0x4D
USAGE_RIGHT = 0x4F
USAGE_LEFT = 0x50
USAGE_DOWN = 0x51
USAGE_UP = 0x52
USAGE_A = 0x04

TH40_DESCRIPTOR = {
    "vendor_id": "36B0", "product_id": "304E", "interface": 0,
    "endpoint": 0x81, "protocol": "boot_keyboard",
    "product": "EPOMAKER TH40",
}
DONGLE_DESCRIPTOR = {
    "vendor_id": "36B0", "product_id": "3002", "interface": 0,
    "endpoint": 0x81, "protocol": "boot_keyboard",
    "product": "Wireless 2.4G Dongle",
}


class Typist:
    """One adapter feeding one authoritative editor, driven by raw reports."""

    def __init__(self, descriptor=None, layout=AUTO, **options):
        self.records = []
        self.backend = FakeKeyboardBackend((), reports_per_poll=64)
        if descriptor is not None:
            self.backend.descriptor = descriptor
        self.queue = BoundedEventQueue(128)
        self.viewport = EditorViewport()
        self.editor = MultilineEditor(layout=self.viewport.layout)
        options.setdefault("poll_budget", 64)
        self.adapter = UsbKeyboardAdapter(
            self.backend, self.queue, self.records.append, layout=layout,
            **options
        )
        self.now = 0.0

    def send(self, reports, advance=0.02):
        """Deliver reports, then apply everything they produced."""
        self.backend.reports.extend(reports)
        while self.backend.reports:
            self.adapter.poll(self.now)
            self.now += advance
            self._apply()
        self.adapter.poll(self.now)
        self._apply()
        return self

    def hold(self, seconds):
        """Advance time with a key still held, so repeats can fall due."""
        step = 0.01
        elapsed = 0.0
        while elapsed < seconds:
            self.now += step
            elapsed += step
            self.adapter.poll(self.now)
            self._apply()
        return self

    def _apply(self):
        while True:
            event = self.queue.get()
            if event is None:
                return
            self.editor.apply(event)

    @property
    def text(self):
        return self.editor.text

    def events(self, name):
        return [r for r in self.records if r.get("event") == name]


def key(usage, shift=False):
    return press_release(usage, shift=shift)


# --------------------------------------------------------------- layout rule


class DeviceLayoutTest(unittest.TestCase):
    def test_the_standard_layout_remaps_nothing(self):
        self.assertEqual(STANDARD.remaps, 0)
        for usage in range(0x00, 0x100):
            self.assertEqual(STANDARD.usage(usage), usage)

    def test_an_unrecognised_keyboard_gets_the_standard_layout(self):
        self.assertIs(layout_for(DONGLE_DESCRIPTOR), STANDARD)
        self.assertIs(layout_for({}), STANDARD)
        self.assertIs(layout_for(None), STANDARD)
        self.assertIs(layout_for({"vendor_id": "FFFF"}), STANDARD)

    def test_the_th40_is_recognised_by_its_usb_identifiers(self):
        self.assertIs(layout_for(TH40_DESCRIPTOR), EPOMAKER_TH40)

    def test_identifiers_normalize_across_the_forms_a_backend_may_report(self):
        self.assertEqual(normalize_id("36b0"), "36B0")
        self.assertEqual(normalize_id("0x36B0"), "36B0")
        self.assertEqual(normalize_id(0x36B0), "36B0")
        self.assertEqual(normalize_id("4e"), "004E")
        self.assertIsNone(normalize_id(None))

    def test_the_th40_remaps_only_the_one_measured_usage(self):
        self.assertEqual(EPOMAKER_TH40.remaps, 1)
        self.assertEqual(
            EPOMAKER_TH40.usage(USAGE_EQUALS_AND_PLUS),
            USAGE_APOSTROPHE_AND_QUOTE,
        )

    def test_no_layout_redefines_a_finish_usage(self):
        """Escape and Application must mean FINISH on every keyboard."""
        for layout in LAYOUTS:
            for usage in (USAGE_ESCAPE, USAGE_APPLICATION):
                self.assertEqual(layout.usage(usage), usage)
                self.assertNotIn(usage, layout.usage_remap.values())

    def test_no_layout_redefines_caps_lock_or_an_editing_key(self):
        protected = (
            USAGE_CAPS_LOCK, USAGE_BACKSPACE, USAGE_DELETE, USAGE_HOME,
            USAGE_END, USAGE_LEFT, USAGE_RIGHT, USAGE_UP, USAGE_DOWN,
        )
        for layout in LAYOUTS:
            for usage in protected:
                self.assertEqual(layout.usage(usage), usage)

    def test_a_configured_selection_overrides_detection(self):
        self.assertIs(resolve("STANDARD", TH40_DESCRIPTOR), STANDARD)
        self.assertIs(resolve("EPOMAKER_TH40", DONGLE_DESCRIPTOR), EPOMAKER_TH40)

    def test_auto_and_none_both_mean_detect(self):
        self.assertIs(resolve(AUTO, TH40_DESCRIPTOR), EPOMAKER_TH40)
        self.assertIs(resolve(None, TH40_DESCRIPTOR), EPOMAKER_TH40)

    def test_an_unknown_layout_name_is_refused(self):
        with self.assertRaises(ValueError):
            resolve("NO_SUCH_KEYBOARD", TH40_DESCRIPTOR)

    def test_the_adapter_refuses_a_bad_layout_at_construction(self):
        """Fail closed before an armed run, not midway through one."""
        with self.assertRaises(ValueError):
            Typist(layout="NO_SUCH_KEYBOARD")

    def test_every_layout_is_reachable_by_name(self):
        for layout in LAYOUTS:
            self.assertIs(LAYOUTS_BY_NAME[layout.name], layout)

    def test_a_layout_describes_itself_for_the_run_record(self):
        described = EPOMAKER_TH40.describe()
        self.assertEqual(described["layout"], "EPOMAKER_TH40")
        self.assertEqual(described["vendor_id"], "36B0")
        self.assertEqual(described["usage_remaps"], {"0x2E": "0x34"})

    def test_the_selected_layout_is_logged_when_the_keyboard_connects(self):
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send(key(USAGE_A))
        selected = typist.events("usb_keyboard_layout_selected")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["layout"]["layout"], "EPOMAKER_TH40")

    def test_a_remap_never_disturbs_press_release_or_repeat_tracking(self):
        """The raw usage is what the keyboard released, so it must be tracked."""
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send([report(0, (USAGE_EQUALS_AND_PLUS,))])
        self.assertEqual(
            typist.adapter.translator.held, (USAGE_EQUALS_AND_PLUS,)
        )
        # A printable is not a repeating key, so nothing may be armed either.
        self.assertFalse(typist.adapter.repeat.armed)
        typist.send([report(0)])
        self.assertEqual(typist.adapter.translator.held, ())
        self.assertFalse(typist.adapter.repeat.armed)

    def test_the_diagnostic_reports_the_raw_usage_the_keyboard_sent(self):
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        normalized = None
        typist.send(key(USAGE_EQUALS_AND_PLUS))
        for record in typist.events("keyboard_event_normalized"):
            normalized = record
        self.assertEqual(normalized["usage"], USAGE_EQUALS_AND_PLUS)
        self.assertEqual(normalized["mapped_usage"], USAGE_APOSTROPHE_AND_QUOTE)

    def test_the_summary_records_which_layout_ran(self):
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send(key(USAGE_EQUALS_AND_PLUS))
        summary = typist.adapter.summary()
        self.assertEqual(summary["keyboard_layout"], "EPOMAKER_TH40")
        self.assertEqual(summary["remapped_usages"], 1)

    def test_a_layout_can_be_built_without_identifiers(self):
        layout = DeviceLayout("BARE")
        self.assertIsNone(layout.vendor_id)
        self.assertEqual(layout.remaps, 0)


# ------------------------------------------------------------- the apostrophe


class ApostropheTest(unittest.TestCase):
    """The one key the physical run could not type."""

    def test_the_standard_apostrophe_usage_is_unchanged(self):
        self.assertEqual(translate(USAGE_APOSTROPHE, False, False), ("CHAR", "'"))
        self.assertEqual(translate(USAGE_APOSTROPHE, True, False), ("CHAR", '"'))

    def test_a_standard_keyboard_still_types_an_apostrophe_from_0x34(self):
        typist = Typist(descriptor=DONGLE_DESCRIPTOR)
        typist.send(type_characters("it") + key(USAGE_APOSTROPHE)
                    + type_characters("s"))
        self.assertEqual(typist.text, "it's")

    def test_a_standard_keyboard_types_equals_nowhere_because_it_has_no_glyph(self):
        """0x2E stays what the specification says it is, and stays unrenderable."""
        self.assertIsNone(translate(USAGE_EQUALS_AND_PLUS, False, False))
        self.assertIsNone(translate(USAGE_EQUALS_AND_PLUS, True, False))
        typist = Typist(descriptor=DONGLE_DESCRIPTOR)
        typist.send(key(USAGE_EQUALS_AND_PLUS))
        self.assertEqual(typist.text, "")
        self.assertEqual(typist.adapter.unsupported_usages, 1)

    def test_the_th40_now_types_an_apostrophe_from_the_usage_it_actually_sends(self):
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send(type_characters("it") + key(USAGE_EQUALS_AND_PLUS)
                    + type_characters("s"))
        self.assertEqual(typist.text, "it's")
        self.assertEqual(typist.adapter.unsupported_usages, 0)

    def test_the_th40_types_a_double_quote_with_shift(self):
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send(key(USAGE_EQUALS_AND_PLUS, shift=True))
        self.assertEqual(typist.text, '"')

    def test_the_th40_still_types_an_apostrophe_from_the_standard_usage(self):
        """A remap adds a source; it must not remove the specified one."""
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send(key(USAGE_APOSTROPHE))
        self.assertEqual(typist.text, "'")

    def test_the_words_the_physical_run_could_not_type_now_type(self):
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send(
            type_characters("It") + key(USAGE_EQUALS_AND_PLUS)
            + type_characters("s a test. I don")
            + key(USAGE_EQUALS_AND_PLUS) + type_characters("t mind.")
        )
        self.assertEqual(typist.text, "It's a test. I don't mind.")

    def test_both_quote_characters_exist_in_the_proven_glyph_table(self):
        for character in ("'", '"'):
            self.assertIn(character, GLYPHS)


# ------------------------------------------------------- editing completeness


class EditingKeyTest(unittest.TestCase):
    """Every listed editing key, asserted by what it does to the document."""

    def test_delete_removes_the_character_under_the_cursor(self):
        typist = Typist()
        typist.send(type_characters("abcd") + key(USAGE_HOME) + key(USAGE_DELETE))
        self.assertEqual(typist.text, "bcd")

    def test_delete_at_the_end_of_the_document_changes_nothing(self):
        typist = Typist()
        typist.send(type_characters("abc") + key(USAGE_DELETE))
        self.assertEqual(typist.text, "abc")

    def test_delete_joins_the_next_line_onto_this_one(self):
        typist = Typist()
        typist.send(type_characters("ab\ncd") + key(USAGE_UP) + key(USAGE_END)
                    + key(USAGE_DELETE))
        self.assertEqual(typist.text, "abcd")

    def test_backspace_removes_the_character_before_the_cursor(self):
        typist = Typist()
        typist.send(type_characters("abcd") + key(USAGE_BACKSPACE))
        self.assertEqual(typist.text, "abc")

    def test_home_moves_to_the_start_of_the_line_and_inserts_there(self):
        typist = Typist()
        typist.send(type_characters("world") + key(USAGE_HOME)
                    + type_characters("hello "))
        self.assertEqual(typist.text, "hello world")

    def test_end_moves_to_the_end_of_the_line(self):
        typist = Typist()
        typist.send(type_characters("hello") + key(USAGE_HOME)
                    + key(USAGE_END) + type_characters("!"))
        self.assertEqual(typist.text, "hello!")

    def test_home_and_end_act_on_the_current_line_only(self):
        typist = Typist()
        typist.send(type_characters("one\ntwo") + key(USAGE_HOME)
                    + type_characters("X"))
        self.assertEqual(typist.text, "one\nXtwo")

    def test_home_and_end_are_idempotent(self):
        typist = Typist()
        typist.send(type_characters("abc") + key(USAGE_HOME) * 1
                    + key(USAGE_HOME) + key(USAGE_END) + key(USAGE_END)
                    + type_characters("!"))
        self.assertEqual(typist.text, "abc!")

    def test_the_arrows_move_the_cursor_in_all_four_directions(self):
        typist = Typist()
        typist.send(type_characters("ab\ncd"))
        typist.send(key(USAGE_UP) + key(USAGE_LEFT))
        self.assertEqual((typist.editor.row, typist.editor.column), (0, 1))
        typist.send(key(USAGE_RIGHT) + key(USAGE_DOWN))
        self.assertEqual(typist.editor.row, 1)


class CapsLockTest(unittest.TestCase):
    def test_caps_lock_on_then_off_bounds_the_uppercase_run(self):
        typist = Typist()
        typist.send(type_characters("a") + key(USAGE_CAPS_LOCK)
                    + type_characters("bc") + key(USAGE_CAPS_LOCK)
                    + type_characters("d"))
        self.assertEqual(typist.text, "aBCd")

    def test_caps_lock_reports_both_transitions(self):
        typist = Typist()
        typist.send(key(USAGE_CAPS_LOCK) + key(USAGE_CAPS_LOCK))
        enabled = [r["enabled"] for r in typist.events("usb_keyboard_caps_lock")]
        self.assertEqual(enabled, [True, False])

    def test_shift_with_caps_lock_returns_a_letter_to_lowercase(self):
        typist = Typist()
        typist.send(key(USAGE_CAPS_LOCK))
        typist.send(key(USAGE_A) + key(USAGE_A, shift=True))
        self.assertEqual(typist.text, "Aa")

    def test_either_shift_key_works_with_caps_lock(self):
        for modifier in (MODIFIER_LEFT_SHIFT, MODIFIER_RIGHT_SHIFT):
            typist = Typist()
            typist.send(key(USAGE_CAPS_LOCK))
            typist.send([report(modifier, (USAGE_A,)), report(modifier)])
            self.assertEqual(typist.text, "a", hex(modifier))

    def test_caps_lock_does_not_change_punctuation(self):
        typist = Typist()
        typist.send(key(USAGE_CAPS_LOCK) + key(USAGE_APOSTROPHE))
        self.assertEqual(typist.text, "'")

    def test_caps_lock_produces_no_character_of_its_own(self):
        typist = Typist()
        typist.send(key(USAGE_CAPS_LOCK))
        self.assertEqual(typist.text, "")


class KeyRepeatTest(unittest.TestCase):
    """Held keys, through the adapter and into the document."""

    HOLD_SECONDS = (REPEAT_DELAY_MS + 4 * REPEAT_INTERVAL_MS) / 1000.0

    def hold_usage(self, usage, setup=(), seconds=None):
        typist = Typist()
        if setup:
            typist.send(setup)
        typist.send([report(0, (usage,))])
        typist.hold(self.HOLD_SECONDS if seconds is None else seconds)
        typist.send([report(0)])
        return typist

    def test_a_held_printable_never_duplicates_the_character(self):
        """A resting finger is not a request for more of that letter."""
        typist = self.hold_usage(USAGE_A, seconds=4.0)
        self.assertEqual(typist.text, "a")
        self.assertEqual(typist.adapter.repeat_events, 0)
        self.assertFalse(typist.adapter.repeat.armed)

    def test_a_held_enter_never_adds_extra_line_breaks(self):
        typist = self.hold_usage(
            USAGE_ENTER, setup=type_characters("ab"), seconds=4.0
        )
        self.assertEqual(typist.text, "ab\n")
        self.assertEqual(typist.adapter.repeat_events, 0)
        self.assertFalse(typist.adapter.repeat.armed)

    def test_a_held_application_key_never_repeats_and_finishes_once(self):
        typist = self.hold_usage(USAGE_APPLICATION, seconds=4.0)
        self.assertTrue(typist.adapter.finish_requested)
        self.assertEqual(len(typist.events("usb_keyboard_finish_requested")), 1)
        self.assertEqual(typist.adapter.repeat_events, 0)

    def test_a_held_backspace_repeats(self):
        typist = self.hold_usage(
            USAGE_BACKSPACE, setup=type_characters("abcdefghij")
        )
        self.assertLess(len(typist.text), 9)
        self.assertTrue("abcdefghij".startswith(typist.text))

    def test_a_held_delete_repeats(self):
        typist = self.hold_usage(
            USAGE_DELETE,
            setup=type_characters("abcdefghij") + key(USAGE_HOME),
        )
        self.assertLess(len(typist.text), 9)
        self.assertTrue("abcdefghij".endswith(typist.text))

    def test_a_held_arrow_repeats(self):
        typist = self.hold_usage(
            USAGE_LEFT, setup=type_characters("abcdefghij")
        )
        self.assertEqual(typist.text, "abcdefghij")
        self.assertLess(typist.editor.column, 9)

    def test_repeat_is_exactly_erasing_and_moving(self):
        """The whole repeating set, both halves asserted."""
        for kind in ("BACKSPACE", "DELETE", "LEFT", "RIGHT", "UP", "DOWN"):
            self.assertIn(kind, REPEATABLE_KINDS)
        for kind in ("CHAR", "ENTER", "HOME", "END"):
            self.assertNotIn(kind, REPEATABLE_KINDS)

    def test_home_and_end_never_repeat_because_they_are_idempotent(self):
        for usage in (USAGE_HOME, USAGE_END):
            typist = self.hold_usage(usage, setup=type_characters("abc"))
            self.assertEqual(typist.adapter.repeat_events, 0, hex(usage))

    def test_releasing_the_key_cancels_the_repeat_immediately(self):
        typist = Typist()
        typist.send(type_characters("abcdefghij"))
        typist.send([report(0, (USAGE_BACKSPACE,))])
        typist.hold(self.HOLD_SECONDS)
        before = typist.text
        self.assertLess(len(before), 9)
        typist.send([report(0)])
        typist.hold(4.0)
        self.assertEqual(typist.text, before)
        self.assertFalse(typist.adapter.repeat.armed)

    def test_a_release_carried_with_the_next_press_still_cancels(self):
        """Hardware releases one key in the same report that presses the next."""
        typist = Typist()
        typist.send(type_characters("abcdefghij"))
        typist.send([report(0, (USAGE_BACKSPACE,))])
        typist.hold(self.HOLD_SECONDS)
        erased = typist.text
        repeats = typist.adapter.repeat_events
        self.assertGreater(repeats, 0)
        # One report drops Backspace and presses "a" at the same time.
        typist.send([report(0, (USAGE_A,))])
        typist.hold(4.0)
        self.assertEqual(typist.text, erased + "a")
        self.assertEqual(typist.adapter.repeat_events, repeats)
        self.assertFalse(typist.adapter.repeat.armed)

    def test_a_tapped_key_never_repeats(self):
        for usage in (USAGE_A, USAGE_BACKSPACE, USAGE_ENTER, USAGE_LEFT):
            typist = Typist()
            typist.send(type_characters("abc"))
            characters = len(typist.text)
            typist.send(key(usage))
            typist.hold(4.0)
            self.assertEqual(typist.adapter.repeat_events, 0, hex(usage))
            # One tap changed the document at most once.
            self.assertLessEqual(abs(len(typist.text) - characters), 1)

    def test_typing_a_realistic_overlapping_stream_produces_exactly_that_text(self):
        """Normal writing, at the rate the bench capture recorded, is verbatim."""
        typist = Typist()
        text = "the quick brown fox jumps"
        # 90 ms per report: each key is held about as long as the captured
        # session's slowest ordinary keystroke, and well inside the repeat delay.
        typist.send(type_characters_overlapping(text), advance=0.09)
        typist.hold(4.0)
        self.assertEqual(typist.text, text)
        self.assertEqual(typist.adapter.repeat_events, 0)

    def test_the_newest_held_key_takes_over_the_repeat(self):
        typist = Typist()
        typist.send(type_characters("abcdefghij"))
        typist.send([report(0, (USAGE_BACKSPACE,))])
        typist.send([report(0, (USAGE_BACKSPACE, USAGE_LEFT))])
        self.assertEqual(typist.adapter.repeat.usage, USAGE_LEFT)
        typist.hold(self.HOLD_SECONDS)
        typist.send([report(0)])
        # The newest key owns the repeat, so only the arrow repeated: one
        # backspace was applied and the rest of the text is intact.
        self.assertEqual(typist.text, "abcdefghi")
        self.assertLess(typist.editor.column, 8)

    def test_repeats_are_flagged_so_a_run_record_can_separate_them(self):
        typist = self.hold_usage(
            USAGE_BACKSPACE, setup=type_characters("abcdefghij")
        )
        flags = [r["repeat"] for r in typist.events("keyboard_event_normalized")]
        self.assertIn(True, flags)
        self.assertIn(False, flags)

    def test_a_repeated_edit_is_never_rejected_by_the_editor(self):
        typist = self.hold_usage(USAGE_BACKSPACE, setup=type_characters("ab"))
        # Backspace at the very start of an empty document must be harmless.
        self.assertEqual(typist.text, "")


class PreservedBehaviourTest(unittest.TestCase):
    """Nothing this phase touched may have moved."""

    def test_escape_is_still_the_finish_control(self):
        typist = Typist()
        typist.send(key(USAGE_ESCAPE))
        self.assertTrue(typist.adapter.finish_requested)
        self.assertEqual(typist.text, "")

    def test_the_application_key_is_still_the_finish_control(self):
        typist = Typist()
        typist.send(key(USAGE_APPLICATION))
        self.assertTrue(typist.adapter.finish_requested)
        self.assertEqual(typist.text, "")

    def test_both_finish_usages_work_under_a_device_layout_too(self):
        for usage in (USAGE_ESCAPE, USAGE_APPLICATION):
            typist = Typist(descriptor=TH40_DESCRIPTOR)
            typist.send(key(usage))
            self.assertTrue(typist.adapter.finish_requested, hex(usage))

    def test_an_unsupported_usage_is_still_bounded_and_reported(self):
        typist = Typist()
        typist.send(key(0x68))          # F13: no glyph, no editor meaning
        self.assertEqual(typist.text, "")
        self.assertEqual(typist.adapter.unsupported_usages, 1)
        reported = typist.events("usb_keyboard_unsupported_usage")
        self.assertEqual([r["usage"] for r in reported], [0x68])

    def test_an_unsupported_usage_under_a_layout_reports_the_raw_usage(self):
        typist = Typist(descriptor=TH40_DESCRIPTOR)
        typist.send(key(0x68))
        reported = typist.events("usb_keyboard_unsupported_usage")
        self.assertEqual([r["usage"] for r in reported], [0x68])

    def test_every_character_any_layout_can_emit_is_renderable(self):
        for layout in LAYOUTS:
            translator = HidKeyboardTranslator(layout=layout)
            for usage in range(0x00, 0x100):
                for shift in (False, True):
                    for caps in (False, True):
                        result = translate(
                            layout.usage(usage), shift, caps
                        )
                        if result is not None and result[0] == "CHAR":
                            self.assertIn(result[1], GLYPHS, repr(result))


if __name__ == "__main__":
    unittest.main()
