# Fruit Jam Multiline Editor Integration Test

**Status: ATTEMPT 1 — FAIL (harness timeout defect; editor behaviour correct so far as observed)**

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
| Implementation commit | `d9ff23e` |
| Attempt 1 run commit | `dc5ac00` |
| Host tests at `d9ff23e` | 245/245 pass |
| Host tests at `dc5ac00` (run commit) | 247/247 pass |
| `python -m compileall -q magtag fruitjam host-tests` | pass |
| `python tools/validate_uart_harness.py` | pass |
| `git diff --check` | pass |

### Defect found during preflight, before attempt 1

`magtag/hardware_test_boot.py`, which ships as the MagTag `/boot.py`, gated the
writable remount on a hardcoded mode tuple that the editor phase never updated.
`MAGTAG_EDITOR_DISPLAY` was added to `display_adapter.APPROVED_TEST_MODES`,
`magtag/code.py`, and the display harness, but not to that tuple, so arming the
MagTag would have booted read-only and the harness would have raised `OSError`
writing its `.started` guard before touching the panel. The Fruit Jam `boot.py`
already had its matching branch. Fixed and covered by host tests in `dc5ac00`.

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

### Attempt 1 — 2026-07-28, run commit `dc5ac00`

**Result: FAIL.** Stop condition: `editor display test timeout`, raised by the
MagTag. Both devices halted, both `.started` guards preserved, no retry
attempted, no guard deleted.

#### Root cause

The MagTag started its test deadline at `editor_display_ready` and compared it
against `EDITOR_TEST_TIMEOUT_SECONDS = 150`. The arming order in this document
requires the MagTag to be armed, reset, and *confirmed ready* before the Fruit
Jam is armed and reset, so the operator-paced arming wait was charged to the
run budget.

| Event | Host time |
| --- | --- |
| MagTag `editor_display_ready` — deadline started | 23:20:28 |
| Fruit Jam first frame — test actually began | 23:22:20 |
| MagTag timeout fired (23:20:29 + 150 s) | 23:22:59 |

The wait consumed 112 s of the 150 s budget, leaving 39 s for a run that needs
roughly 90–100 s. The Fruit Jam's own 240 s budget was never approached. This
is a harness-clock defect, not an editor, layout, transport, or display defect.
Fixed after the attempt by `magwrite/run_clock.py`, which gives the arming wait
its own separate bound; covered by `host-tests/test_run_clock.py`.

#### Observed values

| Field | Observed |
| --- | --- |
| Repository commit | `dc5ac00` |
| Fruit Jam CircuitPython version | 10.2.1 (`adafruit_fruit_jam`, UID `FFDBA7B15146C218`) |
| MagTag CircuitPython version | 9.1.1 (`adafruit_magtag_2.9_grayscale`, UID `C7FD1A005DEA`) |
| Wiring and pin aliases confirmed | yes — wiring confirmed by operator; `board.A0`/`board.A1` on Fruit Jam and `board.D10`/`board.A1` on MagTag all confirmed present on-device via REPL |
| Baud / protocol version | 115200 8N1 / protocol version 1 |
| Events generated | 193 (of 362 scripted; run aborted during scenario 3) |
| Events processed | 193 |
| Sequence integrity | contiguous 0–192, strictly increasing, 0 duplicates, 0 out-of-order |
| Events rejected | 0 |
| Maximum queue depth | 1 of 64 |
| Queue overflows | 0 |
| Scenario 1 final document | **exact match** — `MAGWRITE IS A WRITING TOOL.\nIT RUNS ON E-PAPER.\nCURSOR STAYS VISIBLE.` |
| Scenario 2 final document | **exact match** — `TODAY I WROTE A JOURNAL ENTRY.\nSECOND LINE. AMEN.` |
| Scenario 3 final document | NOT REACHED — aborted at event 192 of 54-event scenario segment |
| Scenario 4 final document | NOT REACHED |
| Scenario 5 final document | NOT REACHED |
| Final document revision | 162 |
| Final viewport revision | 195 |
| Viewports built | 192 |
| Viewport frames sent | 17 |
| Viewport frames rendered | 15 |
| Viewport frames superseded (MagTag) | 2 |
| Viewport states superseded (Fruit Jam) | 174 |
| FRAME_ACCEPTED count | 17 |
| REFRESH_STARTED count | 15 |
| REFRESH_COMPLETED count | 15 |
| DISPLAY_CAUGHT_UP count | 11 |
| TEST_COMPLETE received | no |
| Final transmitted revision | 175 |
| Final displayed revision | 175 (equal; displayed never exceeded transmitted) |
| Final viewport hash | `76871CA5` (Fruit Jam); no expected value — run aborted mid-scenario |
| Full refreshes | 1 |
| Partial refreshes | 14 |
| Refresh durations (ms) | 3493 (full), then 894, 941, 1007, 1080, 876, 930, 953, 947, 994, 1015, 842, 882, 888, 908 |
| CRC failures | 0 |
| Parser rejections | 0 |
| Sequence gaps | 0 |
| Status duplicates / stale | 0 / 0 |
| Discarded prefix bytes | 4266 of 5674 received (MagTag); 0 (Fruit Jam) |
| Maximum discarded prefix | 120 bytes |
| Resynchronization events | 36 (MagTag); 0 (Fruit Jam) |
| Status queue maximum depth | 2 of 32 |
| Timeouts | 1 |
| Bytes sent / received | Fruit Jam 1408 / 1821; MagTag 1762 / 5674 |
| Visual observations | Operator reported the panel holding `MAGWRITE CAPTURE_` after the run. Reconciles exactly with displayed revision 175 — see note below. |
| Photograph filename or explicit no-photo statement | **No photograph was taken.** |
| Fruit Jam guard states | `/magwrite_editor_integration.started` present (1267 bytes, holds failure summary); `.complete` absent |
| MagTag guard states | `/magwrite_editor_display.started` present; `.complete` absent |
| Prior guards verified untouched | yes — all 17 prior guards SHA-256 inventoried before the run and re-verified byte-identical after |
| Final activation states restored to disabled | yes — both `config.py` files restored to the disabled repository versions |
| User approval of final screen | not sought — no final screen was produced |
| Result (PASS / FAIL / INCONCLUSIVE) | **FAIL** |

#### Note on discarded prefix bytes

The MagTag discarded 4266 of 5674 received bytes before the frame magic, with
36 resynchronizations, while accepting 17 of 17 frames with zero CRC failures
and zero parser rejections. The earlier *passing* bidirectional acknowledgement
run recorded 567 discarded of 1087 received with 5 resynchronizations, so this
is the same pre-existing, proportionally similar link characteristic, amplified
by the 112 s window in which the MagTag listened to an idle line while the Fruit
Jam was being armed and reset. No frame was corrupted. It is not a new fault,
but it remains uncharacterized and is worth instrumenting.

#### Note on visual observations

The run aborted 39 s in, during scenario 3, so the final expected screen was
never produced and no photograph was taken. The operator did read the panel
after the run and reported it holding:

```text
MAGWRITE CAPTURE_
```

That reconciles exactly with the logs, and is the one piece of independent
physical confirmation attempt 1 produced:

- viewport revision 175 is the event that typed the `E` of `CAPTURE`, at
  authoritative cursor column 16, document revision 142;
- `MAGWRITE CAPTURE` is exactly 16 characters, and the trailing `_` is the
  cursor at column 16;
- that frame's `text_hash` is `76871CA5`, identical to the recorded
  `final_hash`;
- the Fruit Jam had already advanced to viewport revision 195 and 36
  characters, so the panel was a genuine 20-revision behind — the MagTag
  rendered exactly revision 175, reported exactly 175, and never claimed a
  revision it had not drawn.

So single-line rendering, cursor placement, authoritative-revision reporting,
and stale-frame coalescing are all physically confirmed. What the observation
does **not** cover: the substring contains no punctuation, so the seven new
glyphs are unverified, as is anything multi-row.

Scenario 4 (`scrolling`) never ran, so **vertical scrolling and cursor
visibility remain physically unverified**, as do the scenario 5 journal view and
the five-line adjacent-row readability check.

The following PASS criteria are therefore **unverified**, not merely unmet:
multiline scrolling with cursor visibility, the final expected screen, final
hash reconciliation against an expected value, `TEST_COMPLETE`, complete erase
between major viewport replacements, ghosting, border integrity, and operator
approval of the final screen.

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
