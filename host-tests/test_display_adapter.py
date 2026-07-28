import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.display_adapter import (
    PHYSICAL_TEST_MODE,
    REFRESH_50_MODE,
    REFRESH_100_MODE,
)
from magwrite.uc8151_adapter import UC8151DisplayAdapter


class FakeDriver:
    def __init__(self):
        self.buf = bytearray(16)
        self.busy = False
        self.full_calls = 0
        self.partial_calls = 0
        self.power_off_calls = 0

    def update(self, full=False):
        self.full_calls += int(full)

    def update_start(self):
        self.partial_calls += 1

    def is_busy(self):
        return self.busy

    def power_off(self):
        self.power_off_calls += 1


def config(enabled=True, decision="COMPATIBLE", controller="UC8151D"):
    return types.SimpleNamespace(
        ENABLE_PHYSICAL_DISPLAY=enabled,
        HARDWARE_COMPATIBILITY_DECISION=decision,
        DISPLAY_CONTROLLER=controller,
    )


class DisplayAdapterTests(unittest.TestCase):
    def adapter(self, cfg=None, mode=PHYSICAL_TEST_MODE):
        driver = FakeDriver()
        adapter = UC8151DisplayAdapter(
            cfg or config(), mode, driver_factory=lambda: driver
        )
        return adapter, driver

    def test_activation_false_cannot_initialize(self):
        adapter, _ = self.adapter(config(enabled=False))
        with self.assertRaises(RuntimeError):
            adapter.initialize()
        self.assertIsNone(adapter.driver)

    def test_noncompatible_decision_cannot_initialize(self):
        adapter, _ = self.adapter(config(decision="UNCONFIRMED"))
        with self.assertRaises(RuntimeError):
            adapter.initialize()

    def test_wrong_controller_cannot_initialize(self):
        adapter, _ = self.adapter(config(controller="SSD1680"))
        with self.assertRaises(RuntimeError):
            adapter.initialize()

    def test_explicit_test_mode_is_required(self):
        adapter, _ = self.adapter(mode="DISABLED")
        with self.assertRaises(RuntimeError):
            adapter.initialize()

    def test_distinct_characterization_modes_are_approved(self):
        for mode in (REFRESH_50_MODE, REFRESH_100_MODE):
            adapter, _ = self.adapter(mode=mode)
            adapter.initialize()

    def test_initial_is_full_and_later_may_be_partial(self):
        adapter, driver = self.adapter()
        adapter.initialize()
        self.assertTrue(adapter.begin_refresh(bytearray(16)))
        self.assertEqual(driver.full_calls, 1)
        self.assertFalse(adapter.begin_refresh(bytearray(16)))
        self.assertEqual(driver.partial_calls, 1)

    def test_power_off_invalidates_state_and_forces_next_full(self):
        adapter, driver = self.adapter()
        adapter.initialize()
        adapter.begin_refresh(bytearray(16))
        adapter.power_off()
        self.assertFalse(adapter.differential_state_valid)
        self.assertEqual(driver.power_off_calls, 1)
        self.assertTrue(adapter.begin_refresh(bytearray(16)))
        self.assertEqual(driver.full_calls, 2)

    def test_import_does_not_load_circuitpython_modules(self):
        self.assertNotIn("board", sys.modules)
        self.assertNotIn("busio", sys.modules)
        self.assertNotIn("displayio", sys.modules)
        self.assertNotIn("digitalio", sys.modules)


if __name__ == "__main__":
    unittest.main()
