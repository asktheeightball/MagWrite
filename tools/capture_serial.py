"""Read-only, reconnecting serial capture for one board.

Built from three failures recorded in ``docs/FRUITJAM_USB_KEYBOARD_TEST.md``:

1. **A CircuitPython board re-enumerates its USB CDC on reset**, which
   invalidates an already-open handle. A capture opened before the reset simply
   died there. This tool reconnects indefinitely and records every connect and
   disconnect, so the capture can be started *before* the operator presses
   reset, which is the only ordering that catches boot and handshake records.

2. **DTR must be asserted.** The earlier capture held DTR low to avoid
   resetting the board; CircuitPython reads DTR as "a terminal is attached" and
   *discards console output* when it is low, so both boards ran correctly while
   writing to a console nobody was reading and the first ~59 characters of the
   run were unattributable. DTR is asserted here.

3. **Never write to the port.** While a one-shot harness is armed, anything
   arriving on the console can land in the running program. This tool opens the
   port and only ever reads; there is no code path that writes.

Two files are produced:

* ``<out>`` — the board's own lines, verbatim, one per line. This is the
  evidence file and stays pure so it can be parsed as the board emitted it.
* ``<out>.timestamped.jsonl`` — ``{"host_time", "monotonic", "line"}`` per
  line, for correlating the two boards against each other. The measurements
  themselves come from the boards' own clocks, not from these.
"""

import argparse
import datetime
import json
import sys
import time

import serial

RECONNECT_DELAY_SECONDS = 0.5
READ_TIMEOUT_SECONDS = 0.2


def now_iso():
    return datetime.datetime.now().astimezone().isoformat()


def meta(stream, event, **fields):
    record = {"host_time": now_iso(), "capture_event": event}
    record.update(fields)
    stream.write(json.dumps(record) + "\n")
    stream.flush()


def capture(port, out_path, label, baud=115200):
    stamped_path = out_path + ".timestamped.jsonl"
    started = time.monotonic()
    with open(out_path, "a", encoding="utf-8", errors="replace") as raw, \
            open(stamped_path, "a", encoding="utf-8", errors="replace") as stamped:
        meta(stamped, "capture_start", port=port, label=label, baud=baud)
        connection = None
        while True:
            if connection is None:
                try:
                    connection = serial.Serial(
                        port, baud, timeout=READ_TIMEOUT_SECONDS
                    )
                    # CircuitPython discards console output unless a terminal
                    # is signalled as attached.
                    connection.dtr = True
                    meta(stamped, "connected", port=port, label=label)
                except (serial.SerialException, OSError):
                    time.sleep(RECONNECT_DELAY_SECONDS)
                    continue
            try:
                line = connection.readline()
            except (serial.SerialException, OSError) as error:
                meta(stamped, "disconnected", port=port, label=label,
                     detail=str(error))
                try:
                    connection.close()
                except Exception:
                    pass
                connection = None
                time.sleep(RECONNECT_DELAY_SECONDS)
                continue
            if not line:
                continue
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not text:
                continue
            raw.write(text + "\n")
            raw.flush()
            stamped.write(json.dumps({
                "host_time": now_iso(),
                "monotonic": round(time.monotonic() - started, 4),
                "line": text,
            }) + "\n")
            stamped.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args(argv)
    try:
        capture(args.port, args.out, args.label, args.baud)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
