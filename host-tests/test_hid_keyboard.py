"""HID report parsing, keymap translation, repeat, and descriptor handling.

These tests own detailed keyboard correctness so the physical run can stay a
single bounded live-typing smoke test.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from keyboard_simulator import (
    REAL_CONFIGURATION_DESCRIPTOR, press_release, report,
)
from magwrite.test_pattern import GLYPHS
from magwrite_transport.editor import (
    BACKSPACE, CHAR, DELETE, DOWN, END, ENTER, HOME, LEFT, RIGHT, UP,
)
from magwrite_transport.hid_keyboard import (
    FIRST_USAGE_INDEX, HidKeyboardTranslator, HidReportError, REPORT_SIZE,
    parse_report,
)
from magwrite_transport.hid_keymap import (
    CONTROL_CAPS_LOCK, CONTROL_FINISH, CONTROL_SAVE, CONTROL_UNSUPPORTED,
    CONTROL_USAGES, CTRL_MASK, CTRL_USAGES, FINISH_USAGES, MODIFIER_LEFT_CTRL,
    MODIFIER_LEFT_SHIFT, MODIFIER_RIGHT_CTRL, MODIFIER_RIGHT_SHIFT,
    REPEATABLE_KINDS, SAVE_USAGES, SHIFT_MASK, USAGE_APPLICATION,
    USAGE_CAPS_LOCK, USAGE_ERROR_ROLLOVER, USAGE_ESCAPE, ctrl_active,
    is_modifier_usage, shift_active, supported_characters, translate,
)
from magwrite_transport.keyboard_repeat import (
    MAX_CATCH_UP, REPEAT_DELAY_MS, REPEAT_INTERVAL_MS, KeyRepeat,
)
from magwrite_transport.usb_hid_descriptors import (
    BOOT_REPORT_SIZE, DescriptorParseError, EndpointInitializationError,
    UnsupportedKeyboardInterface, configuration_total_length,
    parse_configuration, select_boot_keyboard,
)

USAGE_A = 0x04
USAGE_B = 0x05
USAGE_S = 0x16
USAGE_D = 0x07
USAGE_1 = 0x1E
USAGE_9 = 0x26
USAGE_0 = 0x27
USAGE_SPACE = 0x2C
USAGE_MINUS = 0x2D
USAGE_SEMICOLON = 0x33
USAGE_APOSTROPHE = 0x34
USAGE_COMMA = 0x36
USAGE_PERIOD = 0x37
USAGE_SLASH = 0x38
USAGE_EQUALS = 0x2E
USAGE_F1 = 0x3A
USAGE_TAB = 0x2B
USAGE_MENU = 0x65
USAGE_LEFT_SHIFT = 0xE1


class ReportParsingTest(unittest.TestCase):
    def test_boot_report_splits_into_modifier_and_six_usages(self):
        raw = report(MODIFIER_LEFT_SHIFT, (USAGE_A, USAGE_D, USAGE_S))
        modifier, usages = parse_report(raw)
        self.assertEqual(modifier, MODIFIER_LEFT_SHIFT)
        self.assertEqual(usages, (USAGE_A, USAGE_D, USAGE_S, 0, 0, 0))

    def test_the_real_observed_rollover_report_parses(self):
        """``00 00 04 07 16 00 00 00`` was captured from the real keyboard."""
        raw = bytes.fromhex("0000040716000000")
        self.assertEqual(len(raw), REPORT_SIZE)
        modifier, usages = parse_report(raw)
        self.assertEqual(modifier, 0)
        self.assertEqual(usages, (USAGE_A, USAGE_D, USAGE_S, 0, 0, 0))

    def test_a_short_or_missing_report_is_refused(self):
        with self.assertRaises(HidReportError):
            parse_report(bytes(7))
        with self.assertRaises(HidReportError):
            parse_report(None)

    def test_a_padded_report_is_truncated_not_refused(self):
        raw = report(0, (USAGE_A,)) + b"\xff\xff"
        modifier, usages = parse_report(raw)
        self.assertEqual(modifier, 0)
        self.assertEqual(usages[0], USAGE_A)

    def test_the_reserved_byte_is_never_read_as_a_usage(self):
        raw = bytearray(report(0, (USAGE_A,)))
        raw[1] = 0xFF
        self.assertEqual(parse_report(bytes(raw))[1], (USAGE_A, 0, 0, 0, 0, 0))
        self.assertEqual(FIRST_USAGE_INDEX, 2)


class ModifierDecodingTest(unittest.TestCase):
    def test_either_shift_counts_and_other_modifiers_do_not(self):
        self.assertTrue(shift_active(MODIFIER_LEFT_SHIFT))
        self.assertTrue(shift_active(MODIFIER_RIGHT_SHIFT))
        self.assertTrue(shift_active(SHIFT_MASK))
        self.assertFalse(shift_active(0))
        self.assertFalse(shift_active(MODIFIER_LEFT_CTRL))

    def test_modifier_usages_are_recognised_as_modifiers(self):
        for usage in range(0xE0, 0xE8):
            self.assertTrue(is_modifier_usage(usage))
        self.assertFalse(is_modifier_usage(USAGE_A))


class CtrlCombinationTest(unittest.TestCase):
    """Held Ctrl is a command, never a character.

    Before ``CTRL_USAGES`` existed, Ctrl-S emitted a literal "s". The reflex
    every writer has for "save" therefore inserted a stray character into the
    authoritative document -- silently, and at the exact moment the writer
    believed they were protecting it. These tests exist so that cannot return.
    """

    def setUp(self):
        self.translator = HidKeyboardTranslator()

    def press(self, usage, modifier=MODIFIER_LEFT_CTRL):
        return self.translator.step(report(modifier, (usage,)))

    def test_either_ctrl_counts_and_other_modifiers_do_not(self):
        self.assertTrue(ctrl_active(MODIFIER_LEFT_CTRL))
        self.assertTrue(ctrl_active(MODIFIER_RIGHT_CTRL))
        self.assertTrue(ctrl_active(CTRL_MASK))
        self.assertFalse(ctrl_active(0))
        self.assertFalse(ctrl_active(MODIFIER_LEFT_SHIFT))

    def test_ctrl_s_is_a_save_control_and_emits_no_character(self):
        outcome = self.press(USAGE_S)
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(outcome.controls, ((CONTROL_SAVE, USAGE_S),))

    def test_ctrl_s_works_with_the_right_hand_ctrl_too(self):
        outcome = self.press(USAGE_S, MODIFIER_RIGHT_CTRL)
        self.assertEqual(outcome.controls, ((CONTROL_SAVE, USAGE_S),))

    def test_an_unmapped_ctrl_combination_inserts_nothing(self):
        """The correction generalises past the one combination that has a home."""
        for usage in (USAGE_A, USAGE_B):
            self.translator.reset()
            outcome = self.press(usage)
            self.assertEqual(outcome.decisions, (), hex(usage))
            self.assertEqual(
                outcome.controls, ((CONTROL_UNSUPPORTED, usage),), hex(usage)
            )

    def test_s_without_ctrl_is_still_an_ordinary_character(self):
        outcome = self.translator.step(report(0, (USAGE_S,)))
        self.assertEqual(len(outcome.decisions), 1)
        self.assertEqual(outcome.decisions[0].value, "s")
        self.assertEqual(outcome.controls, ())

    def test_shift_s_is_still_an_ordinary_capital(self):
        outcome = self.translator.step(report(MODIFIER_LEFT_SHIFT, (USAGE_S,)))
        self.assertEqual(outcome.decisions[0].value, "S")

    def test_ctrl_does_not_take_precedence_over_finishing(self):
        # Escape and Application are checked before the Ctrl table, so a writer
        # holding Ctrl can still stop the session.
        for usage in FINISH_USAGES:
            self.translator.reset()
            outcome = self.press(usage)
            self.assertEqual(outcome.controls, ((CONTROL_FINISH, usage),))

    def test_ctrl_does_not_break_caps_lock(self):
        outcome = self.press(USAGE_CAPS_LOCK)
        self.assertEqual(outcome.controls, ((CONTROL_CAPS_LOCK, True),))

    def test_a_ctrl_combination_is_never_repeatable(self):
        # Nothing was decided, so nothing can be armed for repeat: a held Ctrl-S
        # cannot turn into a stream of checkpoints.
        outcome = self.press(USAGE_S)
        self.assertEqual(outcome.decisions, ())

    def test_the_save_table_does_not_redefine_a_finish_or_editing_key(self):
        for usage in CTRL_USAGES:
            self.assertNotIn(usage, CONTROL_USAGES, hex(usage))
        self.assertEqual(SAVE_USAGES, (USAGE_S,))

    def test_releasing_a_ctrl_combination_leaves_no_held_key_behind(self):
        self.press(USAGE_S)
        outcome = self.translator.step(report(MODIFIER_LEFT_CTRL))
        self.assertEqual(outcome.released, (USAGE_S,))
        self.assertEqual(self.translator.held, ())


class KeymapTranslationTest(unittest.TestCase):
    def test_letters_are_lowercase_unshifted_and_uppercase_shifted(self):
        self.assertEqual(translate(USAGE_A, False, False), (CHAR, "a"))
        self.assertEqual(translate(USAGE_A, True, False), (CHAR, "A"))

    def test_caps_lock_uppercases_letters(self):
        self.assertEqual(translate(USAGE_A, False, True), (CHAR, "A"))

    def test_shift_and_caps_lock_together_return_lowercase(self):
        self.assertEqual(translate(USAGE_A, True, True), (CHAR, "a"))

    def test_caps_lock_does_not_affect_punctuation_or_digits(self):
        self.assertEqual(translate(USAGE_1, False, True), (CHAR, "1"))
        self.assertEqual(translate(USAGE_COMMA, False, True), (CHAR, ","))
        self.assertEqual(translate(USAGE_1, True, True), (CHAR, "!"))

    def test_every_required_punctuation_character_is_reachable(self):
        expected = {
            (USAGE_PERIOD, False): ".", (USAGE_COMMA, False): ",",
            (USAGE_APOSTROPHE, False): "'", (USAGE_MINUS, False): "-",
            (USAGE_SEMICOLON, True): ":", (USAGE_SEMICOLON, False): ";",
            (USAGE_1, True): "!", (USAGE_SLASH, True): "?",
            (USAGE_APOSTROPHE, True): '"', (USAGE_9, True): "(",
            (USAGE_0, True): ")", (USAGE_SLASH, False): "/",
        }
        for (usage, shift), character in expected.items():
            self.assertEqual(
                translate(usage, shift, False), (CHAR, character),
                "usage 0x%02X shift=%s" % (usage, shift),
            )

    def test_space_and_digits_translate(self):
        self.assertEqual(translate(USAGE_SPACE, False, False), (CHAR, " "))
        self.assertEqual(translate(USAGE_SPACE, True, False), (CHAR, " "))
        for offset, digit in enumerate("1234567890"):
            self.assertEqual(
                translate(USAGE_1 + offset, False, False), (CHAR, digit)
            )

    def test_every_letter_of_the_alphabet_translates_both_ways(self):
        for offset in range(26):
            lower = chr(ord("a") + offset)
            self.assertEqual(
                translate(USAGE_A + offset, False, False), (CHAR, lower)
            )
            self.assertEqual(
                translate(USAGE_A + offset, True, False), (CHAR, lower.upper())
            )

    def test_named_editing_keys_translate_to_normalized_kinds(self):
        expected = {
            0x28: ENTER, 0x58: ENTER, 0x2A: BACKSPACE, 0x4C: DELETE,
            0x4A: HOME, 0x4D: END, 0x4F: RIGHT, 0x50: LEFT, 0x51: DOWN,
            0x52: UP,
        }
        for usage, kind in expected.items():
            self.assertEqual(translate(usage, False, False), (kind, ""))
            # A modifier must not change what an editing key means.
            self.assertEqual(translate(usage, True, True), (kind, ""))

    def test_unsupported_usages_translate_to_none(self):
        for usage in (USAGE_F1, USAGE_TAB, USAGE_MENU, 0x00, 0xFF):
            self.assertIsNone(translate(usage, False, False))

    def test_a_mapped_key_with_no_glyph_for_its_variant_is_unsupported(self):
        # Shift-2 is "@", which the proven glyph table does not contain.
        self.assertEqual(translate(0x1F, False, False), (CHAR, "2"))
        self.assertIsNone(translate(0x1F, True, False))
        # The "=" key has no supported variant at all.
        self.assertIsNone(translate(USAGE_EQUALS, False, False))
        self.assertIsNone(translate(USAGE_EQUALS, True, False))

    def test_every_emittable_character_exists_in_the_proven_glyph_table(self):
        for character in supported_characters():
            self.assertIn(character, GLYPHS, repr(character))

    def test_only_erasing_and_moving_keys_are_repeatable(self):
        for kind in (BACKSPACE, DELETE, LEFT, RIGHT, UP, DOWN):
            self.assertIn(kind, REPEATABLE_KINDS)
        # Home and End are idempotent; a character and a line break are what the
        # writer typed once and must not become several.
        for kind in (HOME, END, CHAR, ENTER):
            self.assertNotIn(kind, REPEATABLE_KINDS)


class TranslatorStateTest(unittest.TestCase):
    def setUp(self):
        self.translator = HidKeyboardTranslator()

    def press(self, usage, modifier=0):
        return self.translator.step(report(modifier, (usage,)))

    def release(self, modifier=0):
        return self.translator.step(report(modifier))

    def test_a_press_emits_one_decision(self):
        outcome = self.press(USAGE_A)
        self.assertEqual(len(outcome.decisions), 1)
        self.assertEqual(outcome.decisions[0].kind, CHAR)
        self.assertEqual(outcome.decisions[0].value, "a")
        self.assertEqual(outcome.pressed, (USAGE_A,))
        self.assertEqual(outcome.held, (USAGE_A,))

    def test_release_is_detected_and_emits_nothing(self):
        self.press(USAGE_A)
        outcome = self.release()
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(outcome.released, (USAGE_A,))
        self.assertEqual(outcome.held, ())

    def test_a_held_key_emits_only_once(self):
        self.assertEqual(len(self.press(USAGE_A).decisions), 1)
        # An identical report is a duplicate, not a second press.
        outcome = self.press(USAGE_A)
        self.assertTrue(outcome.duplicate)
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(self.translator.duplicate_reports, 1)

    def test_a_second_key_pressed_while_the_first_is_held_emits_once(self):
        self.press(USAGE_A)
        outcome = self.translator.step(report(0, (USAGE_A, USAGE_D)))
        self.assertEqual([d.value for d in outcome.decisions], ["d"])
        self.assertEqual(outcome.pressed, (USAGE_D,))
        self.assertEqual(outcome.held, (USAGE_A, USAGE_D))

    def test_simultaneous_presses_resolve_in_report_order(self):
        outcome = self.translator.step(report(0, (USAGE_A, USAGE_D, USAGE_S)))
        self.assertEqual([d.value for d in outcome.decisions], ["a", "d", "s"])
        # The reverse array order yields the reverse event order, deterministically.
        translator = HidKeyboardTranslator()
        outcome = translator.step(report(0, (USAGE_S, USAGE_D, USAGE_A)))
        self.assertEqual([d.value for d in outcome.decisions], ["s", "d", "a"])

    def test_releasing_one_of_two_held_keys_reports_only_that_release(self):
        self.translator.step(report(0, (USAGE_A, USAGE_D)))
        outcome = self.translator.step(report(0, (USAGE_D,)))
        self.assertEqual(outcome.released, (USAGE_A,))
        self.assertEqual(outcome.held, (USAGE_D,))
        self.assertEqual(outcome.decisions, ())

    def test_a_rollover_report_emits_nothing_and_preserves_held_state(self):
        self.press(USAGE_A)
        outcome = self.translator.step(
            report(0, (USAGE_ERROR_ROLLOVER,) * 6)
        )
        self.assertTrue(outcome.rollover)
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(self.translator.held, (USAGE_A,))
        self.assertEqual(self.translator.rollover_reports, 1)
        self.assertEqual(self.translator.consecutive_rollover, 1)

    def test_consecutive_rollovers_are_counted_and_then_cleared(self):
        for _ in range(3):
            self.translator.step(report(0, (USAGE_ERROR_ROLLOVER,)))
        self.assertEqual(self.translator.consecutive_rollover, 3)
        self.press(USAGE_A)
        self.assertEqual(self.translator.consecutive_rollover, 0)

    def test_modifiers_alone_create_no_editor_event(self):
        outcome = self.translator.step(report(MODIFIER_LEFT_SHIFT))
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(outcome.pressed, ())
        self.assertEqual(outcome.controls, ())

    def test_a_modifier_usage_in_the_array_is_ignored_not_unsupported(self):
        outcome = self.translator.step(
            report(MODIFIER_LEFT_SHIFT, (USAGE_LEFT_SHIFT, USAGE_A))
        )
        self.assertEqual([d.value for d in outcome.decisions], ["A"])
        self.assertEqual(outcome.held, (USAGE_A,))
        self.assertEqual(self.translator.unsupported_usages, 0)

    def test_shift_state_comes_from_the_current_report(self):
        self.assertEqual(self.press(USAGE_A, MODIFIER_LEFT_SHIFT)
                         .decisions[0].value, "A")
        self.release(MODIFIER_LEFT_SHIFT)
        self.assertEqual(self.press(USAGE_A).decisions[0].value, "a")

    def test_caps_lock_toggles_deterministically_and_emits_no_event(self):
        outcome = self.press(USAGE_CAPS_LOCK)
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(outcome.controls, ((CONTROL_CAPS_LOCK, True),))
        self.assertTrue(self.translator.caps_lock)
        self.release()
        self.assertEqual(self.press(USAGE_A).decisions[0].value, "A")
        self.release()
        self.press(USAGE_CAPS_LOCK)
        self.assertFalse(self.translator.caps_lock)
        self.release()
        self.assertEqual(self.press(USAGE_A).decisions[0].value, "a")
        self.assertEqual(self.translator.caps_lock_toggles, 2)

    def test_holding_caps_lock_does_not_toggle_repeatedly(self):
        self.press(USAGE_CAPS_LOCK)
        self.press(USAGE_CAPS_LOCK)
        self.assertTrue(self.translator.caps_lock)
        self.assertEqual(self.translator.caps_lock_toggles, 1)

    def test_escape_raises_a_finish_control_and_no_editor_event(self):
        outcome = self.press(USAGE_ESCAPE)
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(outcome.controls, ((CONTROL_FINISH, USAGE_ESCAPE),))

    def test_the_application_key_also_raises_a_finish_control(self):
        """0x65 is a deliberate second finish control, not a probe hack.

        The 40% keyboard used for the physical phase cannot deliver 0x29
        without an Fn combination that switches it out of USB mode, so a
        standalone key sending 0x65 is the only finish gesture it can produce.
        """
        outcome = self.press(USAGE_APPLICATION)
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(
            outcome.controls, ((CONTROL_FINISH, USAGE_APPLICATION),)
        )

    def test_both_finish_usages_are_registered_as_finish(self):
        self.assertEqual(
            set(FINISH_USAGES), {USAGE_ESCAPE, USAGE_APPLICATION}
        )
        for usage in FINISH_USAGES:
            self.assertEqual(CONTROL_USAGES[usage], CONTROL_FINISH, usage)

    def test_the_application_key_is_no_longer_unsupported(self):
        outcome = self.press(USAGE_APPLICATION)
        self.assertEqual(self.translator.unsupported_usages, 0)
        for control, _ in outcome.controls:
            self.assertNotEqual(control, CONTROL_UNSUPPORTED)

    def test_each_finish_usage_emits_exactly_one_action_per_press(self):
        for usage in (USAGE_ESCAPE, USAGE_APPLICATION):
            translator = HidKeyboardTranslator()
            finishes = 0
            for _ in range(3):
                for raw in press_release(usage):
                    finishes += sum(
                        1 for control, _ in translator.step(raw).controls
                        if control == CONTROL_FINISH
                    )
            self.assertEqual(finishes, 3, usage)

    def test_holding_a_finish_usage_does_not_finish_repeatedly(self):
        """A held key stays in the held set, so it is pressed exactly once."""
        for usage in (USAGE_ESCAPE, USAGE_APPLICATION):
            translator = HidKeyboardTranslator()
            report = bytes((0, 0, usage, 0, 0, 0, 0, 0))
            finishes = 0
            for _ in range(5):
                # A distinct trailing byte defeats duplicate suppression, so
                # this proves held-key tracking and not merely deduplication.
                for raw in (report, bytes((0, 0, usage, 0, 0, 0, 0, 1))):
                    finishes += sum(
                        1 for control, _ in translator.step(raw).controls
                        if control == CONTROL_FINISH
                    )
            self.assertEqual(finishes, 1, usage)

    def test_a_duplicate_finish_report_emits_nothing(self):
        for usage in (USAGE_ESCAPE, USAGE_APPLICATION):
            translator = HidKeyboardTranslator()
            report = bytes((0, 0, usage, 0, 0, 0, 0, 0))
            translator.step(report)
            outcome = translator.step(report)
            self.assertTrue(outcome.duplicate, usage)
            self.assertEqual(outcome.controls, (), usage)
            self.assertEqual(translator.duplicate_reports, 1, usage)

    def test_releasing_a_finish_usage_clears_the_held_state(self):
        for usage in (USAGE_ESCAPE, USAGE_APPLICATION):
            translator = HidKeyboardTranslator()
            translator.step(bytes((0, 0, usage, 0, 0, 0, 0, 0)))
            self.assertEqual(translator.held, (usage,), usage)
            outcome = translator.step(bytes(8))
            self.assertEqual(translator.held, (), usage)
            self.assertEqual(outcome.released, (usage,), usage)
            self.assertEqual(outcome.controls, (), usage)

    def test_adding_a_finish_usage_left_other_usages_unchanged(self):
        """The new control must not disturb characters, named keys, or errors."""
        self.assertEqual(self.press(USAGE_A).decisions[0].value, "a")
        self.release()
        self.assertEqual(CONTROL_USAGES[USAGE_CAPS_LOCK], CONTROL_CAPS_LOCK)
        self.assertNotIn(USAGE_F1, CONTROL_USAGES)
        self.assertEqual(
            self.press(USAGE_F1).controls, ((CONTROL_UNSUPPORTED, USAGE_F1),)
        )
        self.assertIsNone(translate(USAGE_APPLICATION, False, False))

    def test_an_unsupported_usage_is_counted_and_reported(self):
        outcome = self.press(USAGE_F1)
        self.assertEqual(outcome.decisions, ())
        self.assertEqual(outcome.controls, ((CONTROL_UNSUPPORTED, USAGE_F1),))
        self.assertEqual(self.translator.unsupported_usages, 1)

    def test_reset_forgets_held_keys_and_the_caps_latch(self):
        self.press(USAGE_CAPS_LOCK)
        self.release()
        self.press(USAGE_A)
        self.assertEqual(self.translator.held, (USAGE_A,))
        self.assertTrue(self.translator.caps_lock)
        self.translator.reset()
        self.assertEqual(self.translator.held, ())
        self.assertFalse(self.translator.caps_lock)
        self.assertIsNone(self.translator.previous_raw)
        self.assertEqual(self.translator.resets, 1)

    def test_after_reset_the_same_report_is_a_fresh_press_not_a_duplicate(self):
        """A reconnect must not swallow the first real keystroke either."""
        self.press(USAGE_A)
        self.translator.reset()
        outcome = self.press(USAGE_A)
        self.assertFalse(outcome.duplicate)
        self.assertEqual(len(outcome.decisions), 1)


class KeyRepeatTest(unittest.TestCase):
    def setUp(self):
        self.repeat = KeyRepeat()

    def test_nothing_repeats_before_the_delay(self):
        self.repeat.arm(USAGE_A, object(), 1000.0)
        self.assertTrue(self.repeat.armed)
        self.assertEqual(self.repeat.due(1000.0), 0)
        self.assertEqual(self.repeat.due(1000.0 + REPEAT_DELAY_MS - 1), 0)

    def test_the_first_repeat_lands_exactly_at_the_delay(self):
        self.repeat.arm(USAGE_A, object(), 0.0)
        self.assertEqual(self.repeat.due(REPEAT_DELAY_MS), 1)
        self.assertEqual(self.repeat.repeats_emitted, 1)

    def test_subsequent_repeats_follow_the_interval(self):
        self.repeat.arm(USAGE_A, object(), 0.0)
        self.repeat.due(REPEAT_DELAY_MS)
        self.assertEqual(self.repeat.due(REPEAT_DELAY_MS + 1), 0)
        self.assertEqual(self.repeat.due(REPEAT_DELAY_MS + REPEAT_INTERVAL_MS), 1)

    def test_release_cancels_the_repeat_immediately(self):
        self.repeat.arm(USAGE_A, object(), 0.0)
        self.assertTrue(self.repeat.cancel_if_released((USAGE_A,)))
        self.assertFalse(self.repeat.armed)
        self.assertEqual(self.repeat.due(999999.0), 0)

    def test_releasing_a_different_key_does_not_cancel(self):
        self.repeat.arm(USAGE_A, object(), 0.0)
        self.assertFalse(self.repeat.cancel_if_released((USAGE_B,)))
        self.assertTrue(self.repeat.armed)

    def test_the_newest_press_takes_over_the_repeat(self):
        first, second = object(), object()
        self.repeat.arm(USAGE_A, first, 0.0)
        self.repeat.arm(USAGE_B, second, 100.0)
        self.assertEqual(self.repeat.usage, USAGE_B)
        self.assertIs(self.repeat.decision, second)
        self.assertEqual(self.repeat.due(100.0 + REPEAT_DELAY_MS), 1)

    def test_catch_up_is_bounded_and_resynchronizes(self):
        self.repeat.arm(USAGE_A, object(), 0.0)
        # Far overdue: a stalled loop must not emit an unbounded burst.
        self.assertEqual(self.repeat.due(1000000.0), MAX_CATCH_UP)
        self.assertEqual(self.repeat.resynchronizations, 1)

    def test_repeat_timings_are_validated(self):
        for bad in ({"delay_ms": 0}, {"interval_ms": 0}, {"max_catch_up": 0}):
            with self.assertRaises(ValueError):
                KeyRepeat(**bad)


class DescriptorTest(unittest.TestCase):
    """Parsed against the exact descriptor read off the real receiver."""

    def setUp(self):
        self.interfaces = parse_configuration(REAL_CONFIGURATION_DESCRIPTOR)

    def test_the_real_descriptor_declares_three_hid_interfaces(self):
        self.assertEqual(len(REAL_CONFIGURATION_DESCRIPTOR), 98)
        self.assertEqual(
            configuration_total_length(REAL_CONFIGURATION_DESCRIPTOR[:9]), 98
        )
        self.assertEqual(len(self.interfaces), 3)
        for interface in self.interfaces:
            self.assertEqual(interface.interface_class, 0x03)

    def test_only_the_first_interface_is_a_boot_keyboard(self):
        self.assertTrue(self.interfaces[0].is_boot_keyboard)
        self.assertFalse(self.interfaces[1].is_boot_keyboard)
        self.assertFalse(self.interfaces[2].is_boot_keyboard)

    def test_selection_returns_the_observed_interface_and_endpoint(self):
        interface, endpoint = select_boot_keyboard(self.interfaces)
        self.assertEqual(interface.number, 0)
        self.assertEqual(interface.subclass, 0x01)
        self.assertEqual(interface.protocol, 0x01)
        self.assertEqual(endpoint.address, 0x81)
        self.assertEqual(endpoint.max_packet_size, 8)
        self.assertEqual(endpoint.interval, 1)
        self.assertTrue(endpoint.is_in)
        self.assertTrue(endpoint.is_interrupt)
        self.assertGreaterEqual(endpoint.max_packet_size, BOOT_REPORT_SIZE)

    def test_the_other_interfaces_endpoints_are_parsed_but_never_chosen(self):
        self.assertEqual(
            [e.address for e in self.interfaces[1].endpoints], [0x82, 0x03]
        )
        self.assertEqual(
            [e.address for e in self.interfaces[2].endpoints], [0x84, 0x05]
        )

    def test_a_device_with_no_keyboard_interface_is_refused(self):
        mouse_only = bytes.fromhex(
            "09021900010100A0FA" "090400000103010200" "0705810308000A"
        )
        with self.assertRaises(UnsupportedKeyboardInterface):
            select_boot_keyboard(parse_configuration(mouse_only))

    def test_a_keyboard_interface_with_no_interrupt_in_endpoint_is_refused(self):
        no_endpoint = bytes.fromhex(
            "09021200010100A0FA" "090400000003010100"
        )
        with self.assertRaises(EndpointInitializationError):
            select_boot_keyboard(parse_configuration(no_endpoint))

    def test_an_endpoint_too_small_for_a_boot_report_is_refused(self):
        tiny = bytes.fromhex(
            "09021900010100A0FA" "090400000103010100" "0705810304000A"
        )
        with self.assertRaises(EndpointInitializationError):
            select_boot_keyboard(parse_configuration(tiny))

    def test_malformed_descriptors_are_refused_explicitly(self):
        for data in (
            None,
            b"",
            bytes(4),
            bytes.fromhex("09010900010100A0FA"),                 # wrong type
            bytes.fromhex("09020900010100A0FA") + bytes(4),      # zero length
            bytes.fromhex("09021900010100A0FA") + bytes.fromhex("2004"),
        ):
            with self.assertRaises(DescriptorParseError):
                parse_configuration(data)

    def test_a_configuration_header_is_validated_before_the_full_read(self):
        with self.assertRaises(DescriptorParseError):
            configuration_total_length(bytes(4))
        with self.assertRaises(DescriptorParseError):
            configuration_total_length(bytes.fromhex("090100000100A0FA"))
        with self.assertRaises(DescriptorParseError):
            configuration_total_length(bytes.fromhex("090204000100A0FA00"))

    def test_an_endpoint_before_any_interface_is_refused(self):
        with self.assertRaises(DescriptorParseError):
            parse_configuration(
                bytes.fromhex("09021000010100A0FA") + bytes.fromhex("0705810308000A")
            )

    def test_a_configuration_with_no_interface_is_refused(self):
        with self.assertRaises(DescriptorParseError):
            parse_configuration(bytes.fromhex("09020900010100A0FA"))


if __name__ == "__main__":
    unittest.main()
