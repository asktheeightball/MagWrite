import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.characterization import (
    KNOWN_GUARDS,
    CharacterizationTest,
    TimingSafety,
    guard_paths,
)
from magwrite.display_adapter import REFRESH_50_MODE, REFRESH_100_MODE
from magwrite.test_pattern import GLYPHS


class MemoryGuard:
    def __init__(self):
        self.claimed = False
        self.completed = None

    def claim(self):
        if self.claimed:
            return False
        self.claimed = True
        return True

    def complete(self, summary):
        self.completed = summary


class FakeAdapter:
    def __init__(self, timeout_at=None):
        self.timeout_at = timeout_at
        self.calls = []

    def initialize(self):
        pass

    def begin_refresh(self, framebuffer, full=False):
        self.calls.append(full)
        return full

    def wait_until_idle(self, timeout_seconds):
        return len(self.calls) != self.timeout_at


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.1
        return self.value


def make_test(mode, adapter=None, guard=None, checkpoint=None, prerequisite=True):
    adapter = adapter or FakeAdapter()
    guard = guard or MemoryGuard()
    logs = []
    test = CharacterizationTest(
        mode,
        adapter,
        lambda index, total: bytes((index % 256, total)),
        guard,
        logs.append,
        Clock(),
        checkpoint or (lambda test_name, index: True),
        prerequisite_passed=prerequisite,
    )
    return test, adapter, guard, logs


class CharacterizationTests(unittest.TestCase):
    def test_modes_have_distinct_exact_counts_and_guards(self):
        expected = ((REFRESH_50_MODE, 50), (REFRESH_100_MODE, 100))
        for mode, count in expected:
            test, adapter, guard, _ = make_test(mode)
            result = test.run()
            self.assertEqual(adapter.calls, [True] + [False] * count)
            self.assertEqual(result["completed_partial_updates"], count)
            self.assertIsNotNone(guard.completed)
        self.assertNotEqual(guard_paths(REFRESH_50_MODE), guard_paths(REFRESH_100_MODE))

    def test_100_requires_recorded_50_pass_before_claim(self):
        guard = MemoryGuard()
        test, adapter, _, _ = make_test(
            REFRESH_100_MODE, guard=guard, prerequisite=False
        )
        with self.assertRaises(RuntimeError):
            test.run()
        self.assertFalse(guard.claimed)
        self.assertEqual(adapter.calls, [])

    def test_timeout_stops_all_later_updates(self):
        test, adapter, guard, logs = make_test(
            REFRESH_50_MODE, adapter=FakeAdapter(timeout_at=4)
        )
        result = test.run()
        self.assertEqual(len(adapter.calls), 4)
        self.assertEqual(result["completed_partial_updates"], 2)
        self.assertEqual(result["timeout_count"], 1)
        self.assertIsNone(guard.completed)
        self.assertEqual(logs[-1]["event"], "physical_test_stopped")

    def test_visual_stop_prevents_continuation(self):
        test, adapter, guard, _ = make_test(
            REFRESH_50_MODE,
            checkpoint=lambda test_name, index: index < 20,
        )
        result = test.run()
        self.assertEqual(result["completed_partial_updates"], 20)
        self.assertEqual(len(adapter.calls), 21)
        self.assertIsNone(guard.completed)

    def test_timing_stop_conditions(self):
        safety = TimingSafety()
        self.assertIn("1500", safety.add(1501))
        safety = TimingSafety()
        self.assertIsNone(safety.add(1001))
        self.assertIsNone(safety.add(1002))
        self.assertIn("three consecutive", safety.add(1003))
        safety = TimingSafety()
        for _ in range(10):
            self.assertIsNone(safety.add(700))
        for _ in range(9):
            self.assertIsNone(safety.add(900))
        self.assertIn("drift", safety.add(900))

    def test_previous_20_guards_remain_recognized(self):
        self.assertIn("UC8151_20_UPDATE", KNOWN_GUARDS)
        self.assertEqual(
            guard_paths("UC8151_20_UPDATE")[1],
            "/magwrite_refresh_test_20.complete",
        )

    def test_host_imports_do_not_load_hardware_modules(self):
        importlib.import_module("magwrite.characterization")
        importlib.import_module("magwrite.test_pattern")
        for name in ("board", "busio", "digitalio", "storage", "supervisor"):
            self.assertNotIn(name, sys.modules)

    def test_visual_pattern_text_has_every_required_glyph(self):
        text = "MAGWRITE REFRESH TEST UPDATE / BLACK TO WHITE"
        self.assertEqual(set(text) - set(GLYPHS), set())


if __name__ == "__main__":
    unittest.main()
