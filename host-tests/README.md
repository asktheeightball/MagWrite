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
  duplicate-or-reversed sequence failure latched on either board;
- the standalone appliance, which is the shipped configuration from V1.6: a
  keyboard connected 120 s after the device was switched on, with the same
  adapter under the old bounded budget asserted to *miss* it; the rate bound
  surviving the removal of the attempt count; a device on the port that cannot be
  driven, fatal for a harness and survivable for the appliance; a clock jumped a
  day forward with neither run-length bound firing, and the bounded profile still
  giving up; five Escapes at the main menu leaving the session running and the
  words intact; a stored document the editor refuses, asserted **byte-for-byte**
  against the card, with the empty editor's autosave and manual save both refused
  and the hold released only by an actual open; a paragraph typed into a device
  whose panel is not powered for nine seconds; and the MagTag's own startup
  screens encoded, decoded, and drawn through the real renderer, including a
  fault screen built from an exception message full of characters the panel has
  no glyph for;
- the panel's font, its derived geometry, and the button footer: that the UI
  resolves the firmware's own `terminalio.FONT` wherever it exists and the
  metrics-only host stand-in only where it does not; that the font has a glyph
  for every character either board may draw and refuses one it does not; that the
  row pitch, row count, and column count follow the bounding box the font reports
  rather than a literal, including the assertion that **one more row or one more
  column would not fit**; that the Fruit Jam's layout constants, the viewport
  message bounds, and the shell screen bounds all equal the capacity the MagTag
  derives, because the two boards share no import; that the glyph cache cannot
  grow past the alphabet; and that every screen — editor, menu, drafts, startup,
  waiting, error, and one filled to the last row and column — carries the footer,
  draws nothing in the gap above it, and renders it **pixel for pixel identically**,
  which is what lets a partial refresh leave it alone;
- the wire-format literal each device entry point re-asserts, statically, because
  those files import `board` and no host test can run them. V1.7 raised the
  payload maximum and left `dev_runtime.py` demanding the old one, which passed
  every host check and then refused to start the appliance on the bench. The
  product entry point must equal the current `protocol.MAX_PAYLOAD_SIZE`; the two
  guarded harnesses must stay pinned at what they were verified against.

No test asserts a bound as a literal. Every size is derived from the editor's own
constants, so these keep testing the property the next time the bounds move --
which is a correction of a real defect: a test asserting that 5,000 characters
were refused stopped testing anything the moment V1.4 raised the bound past it.

There is exactly one deliberate exception, added in V1.7: the two guarded
harnesses are asserted to still say `192`. That is not a bound being tested, it
is a record of the wire format those harnesses produced their evidence against,
and it is supposed to stop tracking the current constant.

Hardware acceptance tests must remain separate and must not be marked passed by host simulation.

Run the current feasibility suite from the repository root:

```powershell
python -m unittest discover -s host-tests -p "test_*.py" -v
```

The current suite contains 1,228 tests and has no third-party host dependencies.
