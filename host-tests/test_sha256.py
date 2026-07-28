"""The pure-Python SHA-256 fallback must match hashlib exactly."""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.sha256 import Sha256, sha256_file

DRIVER = os.path.join(os.path.dirname(__file__), "..", "magtag", "uc8151.py")
PINNED = "A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E"


def reference(data):
    return hashlib.sha256(data).hexdigest().upper()


class Sha256Test(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(Sha256().hexdigest(), reference(b""))

    def test_short_input(self):
        digest = Sha256()
        digest.update(b"abc")
        self.assertEqual(digest.hexdigest(), reference(b"abc"))

    def test_block_boundaries(self):
        # 55/56/57 and 63/64/65 exercise every padding branch.
        for size in (54, 55, 56, 57, 63, 64, 65, 119, 120, 128, 1000):
            payload = bytes((index * 7 + 11) & 0xFF for index in range(size))
            digest = Sha256()
            digest.update(payload)
            self.assertEqual(digest.hexdigest(), reference(payload), size)

    def test_incremental_matches_single_update(self):
        payload = bytes((index * 13 + 3) & 0xFF for index in range(500))
        chunked = Sha256()
        for start in range(0, len(payload), 7):
            chunked.update(payload[start:start + 7])
        self.assertEqual(chunked.hexdigest(), reference(payload))

    def test_hexdigest_is_repeatable(self):
        digest = Sha256()
        digest.update(b"magwrite")
        self.assertEqual(digest.hexdigest(), digest.hexdigest())

    def test_driver_file_matches_pinned_hash(self):
        self.assertEqual(sha256_file(DRIVER), PINNED)

    def test_fallback_matches_native_on_driver_file(self):
        with open(DRIVER, "rb") as handle:
            payload = handle.read()
        digest = Sha256()
        digest.update(payload)
        self.assertEqual(digest.hexdigest(), PINNED)


if __name__ == "__main__":
    unittest.main()
