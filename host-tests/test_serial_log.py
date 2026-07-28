import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "magtag"))

from magwrite.serial_log import StructuredSerialLogger


class SerialLogTests(unittest.TestCase):
    def test_logger_emits_one_structured_record(self):
        lines = []
        StructuredSerialLogger(lines.append)(
            {"event": "refresh_end", "refresh_duration_ms": 321}
        )
        self.assertEqual(
            json.loads(lines[0]),
            {"event": "refresh_end", "refresh_duration_ms": 321},
        )


if __name__ == "__main__":
    unittest.main()
