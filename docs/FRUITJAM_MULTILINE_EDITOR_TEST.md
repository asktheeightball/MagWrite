# Fruit Jam Multiline Editor Integration Test

**Status: NOT RUN**

This is one bounded integrated smoke test of the first usable MagWrite writing
prototype. It is not a new qualification campaign. Detailed editor correctness
is owned by the host suite; this device run exists only to confirm that the
integrated editor, layout, viewport, transport, acknowledgement, and physical
e-paper path work together on real hardware.

Every field in the Results section below must be filled in from observed
evidence only. Nothing in this document may be written in advance of the run.

## Repository state

| Item | Value |
| --- | --- |
| Repository | `asktheeightball/MagWrite` |
| Branch | `main` |
| Implementation commit | _record at run time_ |
| Host tests at implementation commit | 245/245 pass |
| `python -m compileall -q magtag fruitjam host-tests` | pass |
| `python tools/validate_uart_harness.py` | pass |
| `git diff --check` | pass |

## Architecture under test

```text
Deterministic scheduled input source   (editor_scenarios.py)
        |
        v
InputEvent / normalized boundary       (editor.py)
        |
        v
Bounded event queue, explicit overflow  (BoundedEventQueue)
        |
        v
Fruit Jam authoritative editor          (MultilineEditor)
        +--> document text and line structure
        +--> cursor row/column, preferred visual column
        +--> document_revision
        |
        v
Layout and viewport builder             (editor_layout.py, editor_viewport.py)
        +--> word wrap, hard wrap, vertical scroll
        +--> viewport_revision
        |
        v
Bidirectional UART transport            (protocol.py, ack_tracker.py)
        |
        v
MagTag display-only terminal            (ack_scheduler.py, viewport_renderer.py)
        +--> FRAME_ACCEPTED
        +--> REFRESH_STARTED
        +--> REFRESH_COMPLETED
        +--> DISPLAY_CAUGHT_UP
        +--> TEST_COMPLETE
```

The Fruit Jam is authoritative for document text, line structure, cursor
position, viewport selection, scrolling, and all three revision counters. The
MagTag is authoritative only for frame acceptance, refresh state, the physically
displayed revision, and display errors. The MagTag performs no editing,
wrapping, scrolling, persistence, or document interpretation.

## Hardware

| Item | Fruit Jam | MagTag |
| --- | --- | --- |
| Board | Adafruit Fruit Jam | original Adafruit MagTag 2.9-inch |
| MCU | RP2350B | ESP32-S2 |
| CircuitPython | 10.2.1 | 9.1.1 |
| Role | authoritative controller | display terminal |
| UART TX | `board.A0` | `board.A1` |
| UART RX | `board.A1` | `board.D10` |
| Display controller | — | UC8151D |

### Wiring

```text
Fruit Jam A0 signal --> MagTag D10 signal
MagTag A1 signal    --> Fruit Jam A1 signal
Fruit Jam GND       --- MagTag GND
```

Both boards are powered separately over USB. There is no inter-board power
conductor. Baud rate is 115200, 8N1.

### Pinned display driver

The UC8151 driver is unmodified at upstream commit
`61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`, SHA-256
`A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E`. The MagTag
entry point verifies this hash before it constructs the UART or touches the
panel, and fails closed on mismatch.

## Viewport geometry

The semantic viewport ceiling was raised from three to five lines for this
phase. Worst-case payload is `4 + 20 + 1 + 20 + 1 + 5 * (1 + 28) = 191` bytes,
inside the unchanged 192-byte protocol maximum. Three-line frames from the
earlier proven runs remain valid and their recorded hashes are unchanged.

```text
MAGWRITE L03 C66                     D081 V081 R05/05
-----------------------------------------------------
28 JULY 2026.

FIRST REAL WORDS ON THE
MAGWRITE PROTOTYPE. THE
SCREEN HOLDS THEM.
-----------------------------------------------------
```

The header carries the title plus the authoritative logical cursor line and
column. The status carries document revision, viewport revision, and the cursor
visual row within the total visual row count. Body text is 28 columns by 5 rows
at scale 2. Seven punctuation glyphs (`.` `,` `'` `-` `:` `!` `?`) were added to
the existing 3x5 glyph table; the cell size and every previously proven glyph
are unchanged, so earlier rendered frames remain bit-identical.

## Scenario definitions

All input is generated locally from a fixed script at a deterministic
words-per-minute schedule. There is no keyboard, Bluetooth, or wireless input.

| # | Name | WPM | Events | Purpose |
| --- | --- | --- | --- | --- |
| 1 | `paragraph` | 60 | 69 | multiline paragraph entry, three logical lines |
| 2 | `correction` | 60 | 88 | deliberate errors corrected with navigation and deletion |
| 3 | `fast_typing` | 80 | 54 | typing faster than the panel can refresh |
| 4 | `scrolling` | 60 | 70 | more visual rows than fit, cursor navigation |
| 5 | `journal` | 60 | 81 | final realistic, fully visible writing view |

Total: 362 normalized input events.

### Expected final documents

1. `paragraph`

   ```text
   MAGWRITE IS A WRITING TOOL.
   IT RUNS ON E-PAPER.
   CURSOR STAYS VISIBLE.
   ```

2. `correction` — typed as `TODAY I WROTE A JORUNAL` + line break + `ENTRY.`,
   then repaired by joining the line upward with Backspace, deleting the
   transposed `R` and reinserting it after the `U`, adding a second line,
   navigating with Up/Down/Left/Right/Home/End, and joining a third line upward
   with Delete.

   ```text
   TODAY I WROTE A JOURNAL ENTRY.
   SECOND LINE. AMEN.
   ```

3. `fast_typing`

   ```text
   MAGWRITE CAPTURES EVERY KEY WHILE THE DISPLAY IS BUSY.
   ```

4. `scrolling`

   ```text
   LINE ONE
   LINE TWO
   LINE THREE
   LINE FOUR
   LINE FIVE
   LINE SIX
   ```

5. `journal`

   ```text
   28 JULY 2026.

   FIRST REAL WORDS ON THE MAGWRITE PROTOTYPE. THE SCREEN HOLDS THEM.
   ```

## Authorised physical limits

| Limit | Ceiling | Host simulation |
| --- | --- | --- |
| Normalized input events | 400 | 362 |
| Viewport frames | 75 | 31 |
| Protocol frames per direction | 150 | 33 sent, 116 received |
| Partial refreshes | 40 | 28 |
| Initial full refreshes | 1 | 1 |
| Guarded physical attempts | 1 | — |

A second attempt requires explicit authorisation. The harness never retries
automatically.

## Activation

Both devices ship disabled and fail closed.

Fruit Jam `config.py`:

```python
ENABLE_EDITOR_INTEGRATION_TEST = False
EDITOR_INTEGRATION_TEST_MODE = "DISABLED"
```

MagTag `config.py`:

```python
ENABLE_PHYSICAL_DISPLAY = False
ENABLE_UART_RECEIVER = False
ENABLE_UART_STATUS_TX = False
PHYSICAL_TEST_MODE = "DISABLED"
EDITOR_DISPLAY_TEST_MODE = "DISABLED"
```

To arm the run, set the Fruit Jam to
`ENABLE_EDITOR_INTEGRATION_TEST = True` and
`EDITOR_INTEGRATION_TEST_MODE = "FRUITJAM_EDITOR_INTEGRATION"`, and the MagTag
to `ENABLE_PHYSICAL_DISPLAY = True`, `ENABLE_UART_RECEIVER = True`,
`ENABLE_UART_STATUS_TX = True`,
`PHYSICAL_TEST_MODE = "MAGTAG_EDITOR_DISPLAY"`, and
`EDITOR_DISPLAY_TEST_MODE = "MAGTAG_EDITOR_DISPLAY"`.

## Guards

New guards for this phase:

| Device | Started | Complete |
| --- | --- | --- |
| Fruit Jam | `/magwrite_editor_integration.started` | `/magwrite_editor_integration.complete` |
| MagTag | `/magwrite_editor_display.started` | `/magwrite_editor_display.complete` |

Either device refuses to run if its own started or complete guard already
exists. No prior guard is read, written, renamed, or deleted. The seventeen
guards from earlier phases must remain byte-identical.

## Procedure

1. Confirm the working tree is clean and record the commit.
2. Confirm both devices are disabled and both guard files are absent.
3. Wire the link as above; confirm common ground and separate USB power.
4. Copy `magtag/` to the MagTag CIRCUITPY volume and `fruitjam/` to the Fruit
   Jam CIRCUITPY volume.
5. Open both serial consoles and begin capturing to the two JSONL files.
6. Arm the MagTag first and confirm it reaches `editor_display_ready`.
7. Arm the Fruit Jam and confirm `editor_test_ready`.
8. Observe the run without touching either board.
9. Inspect the final screen and record the visual observations.
10. Record both summaries, restore both configurations to disabled, and confirm
    all four new guards exist and every prior guard is untouched.

## Stop conditions

Stop immediately and mark FAIL or INCONCLUSIVE on any of: input queue overflow,
missing/duplicate/out-of-order sequence, unexpected rejected edit, final
document mismatch, cursor or revision inconsistency, CRC failure, parser or
status queue overflow, unsupported protocol version, impossible revision, a
stale acknowledgement advancing state, acknowledgement timeout, final hash
mismatch, busy timeout, display initialization failure, unexpected full-screen
flash during a partial refresh, incomplete erase, severe ghosting, border or
pixel corruption, displayed revision exceeding transmitted revision, final
catch-up failure, unhandled exception, reset, memory failure, unstable power,
USB disconnect, wiring issue, unexpected heating, or driver hash mismatch.

On failure: stop both state machines, preserve the started guards and both
serial logs, record the exact scenario and event sequence and all seven
revision counters, restore the disabled configuration where safely possible, do
not delete guards, and do not retry automatically.

## Results

**Status: NOT RUN.** No device run has been performed. Every row below is a
placeholder and must be replaced with observed evidence.

| Field | Observed |
| --- | --- |
| Repository commit | NOT RUN |
| Fruit Jam CircuitPython version | NOT RUN |
| MagTag CircuitPython version | NOT RUN |
| Wiring and pin aliases confirmed | NOT RUN |
| Events generated | NOT RUN |
| Events processed | NOT RUN |
| Events rejected | NOT RUN |
| Maximum queue depth | NOT RUN |
| Scenario 1 final document | NOT RUN |
| Scenario 2 final document | NOT RUN |
| Scenario 3 final document | NOT RUN |
| Scenario 4 final document | NOT RUN |
| Scenario 5 final document | NOT RUN |
| Final document revision | NOT RUN |
| Final viewport revision | NOT RUN |
| Viewport frames sent | NOT RUN |
| Viewport frames rendered | NOT RUN |
| Viewport frames superseded (MagTag) | NOT RUN |
| Viewport states superseded (Fruit Jam) | NOT RUN |
| FRAME_ACCEPTED count | NOT RUN |
| REFRESH_STARTED count | NOT RUN |
| REFRESH_COMPLETED count | NOT RUN |
| DISPLAY_CAUGHT_UP count | NOT RUN |
| TEST_COMPLETE received | NOT RUN |
| Final transmitted revision | NOT RUN |
| Final displayed revision | NOT RUN |
| Final viewport hash | NOT RUN |
| Full refreshes | NOT RUN |
| Partial refreshes | NOT RUN |
| Refresh durations (ms) | NOT RUN |
| CRC failures | NOT RUN |
| Sequence gaps | NOT RUN |
| Status duplicates / stale | NOT RUN |
| Discarded prefix bytes | NOT RUN |
| Resynchronization events | NOT RUN |
| Timeouts | NOT RUN |
| Bytes sent / received | NOT RUN |
| Visual observations | NOT RUN |
| Photograph filename or explicit no-photo statement | NOT RUN |
| Fruit Jam guard states | NOT RUN |
| MagTag guard states | NOT RUN |
| Prior guards verified untouched | NOT RUN |
| Final activation states restored to disabled | NOT RUN |
| User approval of final screen | NOT RUN |
| Result (PASS / FAIL / INCONCLUSIVE) | NOT RUN |

## PASS criteria

Mark PASS only when every one of the following holds:

- every generated event is processed exactly once and in order;
- every scenario final document matches exactly;
- multiline editing works;
- scrolling keeps the cursor visible;
- no input queue overflow occurs;
- the Fruit Jam remains authoritative and the MagTag remains display-only;
- stale viewports are coalesced;
- skipped revisions are never falsely reported displayed;
- final displayed revision equals final transmitted revision;
- the final hash matches;
- final `DISPLAY_CAUGHT_UP` and `TEST_COMPLETE` are received;
- no CRC failure, timeout, queue overflow, or parser overflow occurs;
- no visible corruption occurs;
- the user approves the final screen;
- both devices return to the disabled state;
- all four new guards exist;
- every previous guard remains untouched.

## Measurement limitations

Refresh durations are measured by the MagTag between the physical
`begin_refresh` call and the first observation of an idle busy line, polled
cooperatively. They therefore include up to one loop period of quantisation and
are not a substitute for instrumented timing. Host simulation timings are
modelled, not measured, and are never evidence of physical behaviour.
