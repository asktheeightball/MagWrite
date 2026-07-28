"""JSON-lines serial logging without retaining records in memory."""

try:
    import json
except ImportError:
    import ujson as json


class StructuredSerialLogger:
    def __init__(self, output=print):
        self.output = output

    def __call__(self, fields):
        self.output(json.dumps(fields, separators=(",", ":")))
