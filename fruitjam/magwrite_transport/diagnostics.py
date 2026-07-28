import json


def log(record):
    print(json.dumps(record, separators=(",", ":")))
