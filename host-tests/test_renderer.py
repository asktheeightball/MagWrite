import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.editor import LineEditor
from magwrite.events import KeyEvent
from magwrite.renderer import LandscapeRenderer


class RendererTests(unittest.TestCase):
    def test_static_underscore_cursor_and_fixed_viewport(self):
        editor = LineEditor()
        editor.apply(KeyEvent(0, "insert", "hi"))
        snapshot = LandscapeRenderer(columns=8, rows=2).snapshot(editor)
        self.assertEqual(snapshot.revision, 1)
        self.assertEqual(snapshot.rows, ("hi_     ", "        "))


if __name__ == "__main__":
    unittest.main()
