import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.editor import EditorLimit, LineEditor
from magwrite.events import KeyEvent


class EditorTests(unittest.TestCase):
    def event(self, sequence, kind, value=""):
        return KeyEvent(sequence, kind, value)

    def test_line_editing_and_join(self):
        editor = LineEditor(max_lines=4, max_chars=32)
        for sequence, character in enumerate("abcd"):
            editor.apply(self.event(sequence, "insert", character))
        editor.apply(self.event(4, "left"))
        editor.apply(self.event(5, "left"))
        editor.apply(self.event(6, "enter"))
        editor.apply(self.event(7, "backspace"))
        editor.apply(self.event(8, "delete"))
        self.assertEqual(editor.text, "abd")
        self.assertEqual(editor.revision, 9)
        self.assertEqual(editor.accepted_events, 9)

    def test_limits_are_explicit(self):
        editor = LineEditor(max_lines=1, max_chars=2)
        editor.apply(self.event(0, "insert", "a"))
        editor.apply(self.event(1, "insert", "b"))
        with self.assertRaises(EditorLimit):
            editor.apply(self.event(2, "insert", "c"))
        with self.assertRaises(EditorLimit):
            editor.apply(self.event(3, "enter"))


if __name__ == "__main__":
    unittest.main()
