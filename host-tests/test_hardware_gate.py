import ast
import os
import sys
import types
import unittest

MAGTAG = os.path.join(os.path.dirname(__file__), "..", "magtag")
sys.path.insert(0, MAGTAG)

from hardware_gate import validate
from hardware_identity import DECISION, parse_decision
from magwrite.display_adapter import APPROVED_TEST_MODES


class HardwareGateTests(unittest.TestCase):
    def config(
        self,
        enabled=False,
        revision="UNCONFIRMED",
        controller="UNCONFIRMED",
        decision="UNCONFIRMED",
    ):
        return types.SimpleNamespace(
            ENABLE_PHYSICAL_DISPLAY=enabled,
            MAGTAG_REVISION=revision,
            DISPLAY_CONTROLLER=controller,
            HARDWARE_COMPATIBILITY_DECISION=decision,
        )

    def test_gate_fails_closed(self):
        with self.assertRaises(RuntimeError):
            validate(self.config())
        with self.assertRaises(RuntimeError):
            validate(self.config(True, "2025_MAGTAG", "SSD1680", "INCOMPATIBLE"))

    def test_confirmed_original_is_accepted(self):
        self.assertTrue(
            validate(
                self.config(True, "ORIGINAL_MAGTAG_2.9", "UC8151D", "COMPATIBLE")
            )
        )

    def test_decision_parser_is_strict(self):
        self.assertEqual(parse_decision(" unconfirmed "), "UNCONFIRMED")
        self.assertEqual(parse_decision("compatible"), "COMPATIBLE")
        with self.assertRaises(ValueError):
            parse_decision("probably-compatible")

    def test_recorded_identity_is_compatible_but_activation_stays_disabled(self):
        import config

        self.assertEqual(DECISION, "COMPATIBLE")
        self.assertEqual(config.HARDWARE_COMPATIBILITY_DECISION, DECISION)
        self.assertFalse(config.ENABLE_PHYSICAL_DISPLAY)
        with self.assertRaises(RuntimeError):
            validate(config)


class BootRemountGateTests(unittest.TestCase):
    """``hardware_test_boot.py`` ships as the MagTag ``/boot.py``.

    It cannot be imported on the host because it calls ``storage.remount``, so
    the armed mode tuple is read statically. A mode approved by the display
    adapter but missing here boots read-only, and the harness then dies writing
    its ``.started`` guard before it ever reaches the panel.
    """

    def boot_modes(self):
        path = os.path.join(MAGTAG, "hardware_test_boot.py")
        with open(path) as handle:
            tree = ast.parse(handle.read())
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and any(
                isinstance(op, ast.In) for op in node.ops
            ):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Tuple):
                        found.append(
                            tuple(
                                element.value
                                for element in comparator.elts
                                if isinstance(element, ast.Constant)
                            )
                        )
        self.assertEqual(len(found), 1, "expected exactly one armed mode tuple")
        return found[0]

    def test_boot_gate_covers_every_approved_mode(self):
        self.assertEqual(sorted(self.boot_modes()), sorted(APPROVED_TEST_MODES))

    def test_boot_gate_arms_the_editor_display_mode(self):
        self.assertIn("MAGTAG_EDITOR_DISPLAY", self.boot_modes())


if __name__ == "__main__":
    unittest.main()
