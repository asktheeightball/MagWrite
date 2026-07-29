# Host Tests

Logic that does not require CircuitPython or ESP32 hardware should be testable under normal CPython or a native C test runner.

## Required coverage

- protocol frame encoding and decoding;
- CRC validation;
- duplicate suppression;
- reconnect replay;
- sequence rollover and gaps;
- queue overflow behavior;
- US keyboard translation;
- Shift and Caps Lock interaction;
- key press, release, and repeat handling;
- insertion, Backspace, Delete, and line joins;
- cursor and word movement;
- wrapping and viewport calculations;
- recovery-log replay;
- truncated final recovery record;
- autosave and checkpoint thresholds;
- simulated display-busy typing at 40, 60, and 80 WPM.
- bounded UART framing, CRC-32, chunking, resynchronization, and malformed input;
- semantic viewport bounds, deterministic scenarios, newest-frame coalescing,
  drain-before-render ordering, final revision catch-up, and hash reconciliation;
- adaptive display pacing under isolated, burst, sustained, and display-busy
  input, including maximum pending time, final catch-up, and the guarantee that
  no obsolete frame is transmitted and no input is lost or duplicated;
- per-device keyboard layout compatibility, and every essential key asserted by
  the document it produces.

Hardware acceptance tests must remain separate and must not be marked passed by host simulation.

Run the current feasibility suite from the repository root:

```powershell
python -m unittest discover -s host-tests -p "test_*.py" -v
```

The current suite contains 572 tests and has no third-party host dependencies.
