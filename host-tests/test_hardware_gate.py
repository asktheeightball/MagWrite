import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from hardware_gate import validate
from hardware_identity import DECISION, parse_decision


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


if __name__ == "__main__":
    unittest.main()
