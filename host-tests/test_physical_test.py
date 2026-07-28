import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.physical_test import PARTIAL_UPDATE_COUNT, PhysicalRefreshTest


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
        self.initialized = False

    def initialize(self):
        self.initialized = True

    def begin_refresh(self, framebuffer, full=False):
        self.calls.append(full)
        return full

    def wait_until_idle(self, timeout_seconds):
        return self.timeout_at != len(self.calls)


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.1
        return self.value


class PhysicalTestTests(unittest.TestCase):
    def make_test(self, adapter=None, guard=None):
        adapter = adapter or FakeAdapter()
        guard = guard or MemoryGuard()
        logs = []
        test = PhysicalRefreshTest(
            adapter,
            lambda index: bytearray((index,)),
            guard,
            logs.append,
            Clock(),
            timeout_seconds=1.0,
        )
        return test, adapter, guard, logs

    def test_exactly_twenty_partial_updates_after_initial_full(self):
        test, adapter, guard, _ = self.make_test()
        summary = test.run()
        self.assertEqual(len(adapter.calls), PARTIAL_UPDATE_COUNT + 1)
        self.assertEqual(adapter.calls, [True] + [False] * 20)
        self.assertEqual(summary["completed_partial_updates"], 20)
        self.assertEqual(summary["final_displayed_revision"], 20)
        self.assertIsNotNone(guard.completed)

    def test_timeout_stops_subsequent_updates(self):
        test, adapter, guard, logs = self.make_test(FakeAdapter(timeout_at=4))
        summary = test.run()
        self.assertEqual(len(adapter.calls), 4)
        self.assertEqual(summary["completed_partial_updates"], 2)
        self.assertEqual(summary["timeout_count"], 1)
        self.assertIsNone(guard.completed)
        self.assertEqual(logs[-1]["event"], "physical_test_stopped")

    def test_persistent_guard_prevents_rerun(self):
        guard = MemoryGuard()
        first, _, _, _ = self.make_test(guard=guard)
        first.run()
        second, adapter, _, _ = self.make_test(guard=guard)
        with self.assertRaises(RuntimeError):
            second.run()
        self.assertFalse(adapter.initialized)


if __name__ == "__main__":
    unittest.main()
