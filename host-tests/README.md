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
  the document it produces;
- held Ctrl as a command rather than a character, and Ctrl-S as manual save;
- recovery record encoding, escaping, and every corruption defence individually;
- microSD detection, including an empty slot, an unformatted card, a wrong pin
  alias, and a firmware build with no SD driver;
- autosave and checkpoint thresholds, save state, and the save indicator;
- forced power loss at every byte offset of a journal append, each checkpoint
  interruption window, and a live session killed mid-word and resumed;
- every shell transition, including the ones that are supposed to be impossible,
  the document surviving repeated moves between the shell and the editor, and
  every shell screen encoded, decoded, and drawn with the real MagTag renderer;
- documents far longer than the pre-V1.4 32-line bound; scrolling at the
  beginning, middle, and end of one; editing at the very edge of the document
  limit; and clean refusal at the real limit, with the text, the cursor, both
  revisions, and the recovered document all asserted unchanged;
- the catalogue record against every corruption a power cut produces, catalogue
  ordering, compaction, a truncated final append, and a bounded refusal when
  full;
- Journal, Quick Note, Drafts, and Recent as document policy, including the
  journal rollover and the guarantee that a document keeps its kind however it is
  reached;
- migration of a card written by V1.2 or V1.3, asserted file-by-file: every
  pre-existing file byte-identical, one new file;
- two modes captured in one session and a forced power loss that recovers the
  words, the document identity, and the mode;
- MagTag button debounce against a simulated contact that bounces on **both**
  edges, a held button that must not repeat, and a second press inside the
  minimum interval;
- the two boards’ button action tables and the `BUTTON_EVENT` payload for
  parity, because the boards share no import;
- every shell state in which a button must do nothing, including the menu button
  at the main menu, which must never end a session, and every button in the
  editor, which must never reach the document;
- button duplicate suppression by press ordinal, an unknown action code, and a
  bounded inbox that drops the oldest;
- one whole session navigated entirely by button through the real pad, encoder,
  frame, parser, acknowledgement tracker, shell, and editor, asserting the text
  is exactly what the keyboard typed and the acknowledgement path was unaffected;
- leaving the editor in one gesture, the silent checkpoint it still performs, and
  the absence of the removed save state and save screen;
- a simultaneous cold boot in which the Fruit Jam starts first and the MagTag is
  not powered yet: handshake attempts that go nowhere, a panel arriving long
  after the old hello timeout would have ended the run, the handshake completing,
  the restored document intact through the wait and untouched *during* it, and no
  duplicate-or-reversed sequence failure latched on either board.

No test asserts a bound as a literal. Every size is derived from the editor's own
constants, so these keep testing the property the next time the bounds move --
which is a correction of a real defect: a test asserting that 5,000 characters
were refused stopped testing anything the moment V1.4 raised the bound past it.

Hardware acceptance tests must remain separate and must not be marked passed by host simulation.

Run the current feasibility suite from the repository root:

```powershell
python -m unittest discover -s host-tests -p "test_*.py" -v
```

The current suite contains 1,135 tests and has no third-party host dependencies.
