"""CircuitPython compatibility of the device-runtime source.

These tests exist because of a real hardware failure. ``keyboard_layout`` built
its device layouts at import time and padded USB ids with ``str.zfill``, which
CPython implements and CircuitPython does not. Every host test passed, and every
Fruit Jam entry point that touched the keyboard adapter raised

    AttributeError: 'str' object has no attribute 'zfill'

before it could log anything or claim a guard. The host suite could not catch it
because the host suite runs on CPython.

So two layers here:

* the replacements are asserted behaviourally, against the semantics the removed
  methods provided;
* the device-runtime source is swept for the whole family of CPython-only string
  methods, which is the part that generalises. A behavioural test only protects
  the call site someone already found.

The sweep is deliberately source-level rather than import-level: the point is to
catch a method that no host test happens to execute.
"""

import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.editor import LineEditor
from magwrite.events import KeyEvent
from magwrite.renderer import LandscapeRenderer
from magwrite_transport.keyboard_layout import (
    EPOMAKER_TH40, STANDARD, normalize_id,
)

# str methods CPython provides and CircuitPython does not. Anything in here that
# reaches a board is a crash, not a degradation.
FORBIDDEN_STR_METHODS = (
    "zfill", "ljust", "rjust", "center", "casefold", "expandtabs",
    "format_map", "isidentifier", "isnumeric", "isdecimal", "isprintable",
    "isascii", "maketrans", "translate", "swapcase", "title",
    "removeprefix", "removesuffix",
)

# Modules unavailable on CircuitPython. Importing one at module scope fails the
# same way zfill did.
FORBIDDEN_IMPORTS = (
    "typing", "dataclasses", "functools", "itertools", "abc", "enum",
    "decimal", "fractions", "statistics", "copy", "textwrap", "string",
    "warnings", "logging", "inspect", "pathlib", "argparse", "datetime",
    "unittest", "subprocess", "threading",
)

# Only code that is copied to a board. Host tests and host tools legitimately
# run on CPython and are not swept.
DEVICE_DIRS = (
    os.path.join(ROOT, "fruitjam"),
    os.path.join(ROOT, "magtag"),
)


def device_sources():
    for base in DEVICE_DIRS:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in sorted(filenames):
                if name.endswith(".py"):
                    path = os.path.join(dirpath, name)
                    with open(path, encoding="utf-8") as handle:
                        yield os.path.relpath(path, ROOT), handle.read()


class NormalizeIdTests(unittest.TestCase):
    """The zfill replacement, asserted against zfill's actual semantics."""

    def test_short_ids_are_left_padded_to_four_hex_digits(self):
        self.assertEqual(normalize_id("B0"), "00B0")
        self.assertEqual(normalize_id("0"), "0000")
        self.assertEqual(normalize_id(""), "0000")

    def test_four_digit_ids_are_unchanged(self):
        self.assertEqual(normalize_id("36B0"), "36B0")
        self.assertEqual(normalize_id("304E"), "304E")

    def test_longer_ids_are_never_truncated(self):
        self.assertEqual(normalize_id("136B0"), "136B0")

    def test_lowercase_and_0x_prefix_and_whitespace_are_accepted(self):
        for value in ("0x36b0", "36b0", " 36B0 ", "0X36B0"):
            self.assertEqual(normalize_id(value), "36B0")

    def test_integers_are_formatted_as_four_hex_digits(self):
        self.assertEqual(normalize_id(0x36B0), "36B0")
        self.assertEqual(normalize_id(0xB0), "00B0")

    def test_none_stays_none(self):
        self.assertIsNone(normalize_id(None))

    def test_matches_cpython_zfill_across_the_plausible_range(self):
        # The replacement must not merely work; it must agree with what it
        # replaced, so this test would have failed on the original bug only on
        # hardware -- hence the source sweep below as well.
        for value in ("", "0", "B0", "36B0", "136B0", "ABCD", "1"):
            self.assertEqual(normalize_id(value), value.upper().zfill(4))

    def test_the_module_level_layouts_construct(self):
        # The original failure happened at import time, in exactly these two.
        self.assertEqual(EPOMAKER_TH40.vendor_id, "36B0")
        self.assertEqual(EPOMAKER_TH40.product_id, "304E")
        self.assertIsNone(STANDARD.vendor_id)


class RendererPaddingTests(unittest.TestCase):
    """The ljust replacement."""

    def test_short_lines_are_padded_to_the_column_count(self):
        editor = LineEditor()
        editor.apply(KeyEvent(0, "insert", "hi"))
        snapshot = LandscapeRenderer(columns=8, rows=2).snapshot(editor)
        self.assertEqual(snapshot.rows, ("hi_     ", "        "))
        for row in snapshot.rows:
            self.assertEqual(len(row), 8)

    def test_overlong_lines_are_clipped_not_padded(self):
        editor = LineEditor()
        editor.apply(KeyEvent(0, "insert", "abcdefghij"))
        snapshot = LandscapeRenderer(columns=4, rows=1).snapshot(editor)
        self.assertEqual(snapshot.rows, ("abcd",))

    def test_exact_width_lines_are_unchanged(self):
        editor = LineEditor()
        editor.apply(KeyEvent(0, "insert", "abc"))
        snapshot = LandscapeRenderer(columns=4, rows=1).snapshot(editor)
        self.assertEqual(snapshot.rows, ("abc_",))

    def test_matches_cpython_ljust(self):
        for line, width in (("hi", 8), ("", 4), ("abcd", 4)):
            self.assertEqual(line + " " * (width - len(line)),
                             line.ljust(width))


class DeviceSourceSweepTests(unittest.TestCase):
    """The part that generalises past the two call sites already found."""

    def test_no_device_source_uses_a_cpython_only_str_method(self):
        pattern = re.compile(
            r"\.(" + "|".join(FORBIDDEN_STR_METHODS) + r")\s*\(")
        offenders = []
        for relpath, source in device_sources():
            for number, line in enumerate(source.split("\n"), 1):
                code = line.split("#", 1)[0]
                match = pattern.search(code)
                if match:
                    offenders.append("%s:%d uses .%s()"
                                     % (relpath, number, match.group(1)))
        self.assertEqual(offenders, [], "CircuitPython lacks these: "
                                        + "; ".join(offenders))

    def test_no_device_source_imports_a_cpython_only_module(self):
        pattern = re.compile(
            r"^\s*(?:import|from)\s+(" + "|".join(FORBIDDEN_IMPORTS) + r")\b")
        offenders = []
        for relpath, source in device_sources():
            for number, line in enumerate(source.split("\n"), 1):
                if pattern.match(line.split("#", 1)[0]):
                    offenders.append("%s:%d" % (relpath, number))
        self.assertEqual(offenders, [], "unavailable on CircuitPython: "
                                        + "; ".join(offenders))

    def test_the_sweep_actually_matches_the_original_defect(self):
        # A sweep that cannot fail is worthless, so prove it catches the real
        # line that shipped, and does not fire on the replacement.
        pattern = re.compile(
            r"\.(" + "|".join(FORBIDDEN_STR_METHODS) + r")\s*\(")
        self.assertTrue(pattern.search("    return text.zfill(4)"))
        self.assertTrue(pattern.search("visible.append(l[:c].ljust(c))"))
        self.assertIsNone(pattern.search('text = "0" * (4 - len(text)) + text'))

    def test_the_sweep_covers_both_boards(self):
        seen = {relpath.split(os.sep)[0] for relpath, _ in device_sources()}
        self.assertIn("fruitjam", seen)
        self.assertIn("magtag", seen)


if __name__ == "__main__":
    unittest.main()
