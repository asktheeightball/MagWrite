# Physical Single-Line Typing Test

Status: **PASS**

## Fixed configuration

- Hardware: original MagTag 2.9, `UC8151D`, compatibility `COMPATIBLE`
- CircuitPython: 9.1.1
- Driver upstream commit:
  `61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`
- Driver SHA-256:
  `A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E`
- Mode: `SINGLE_LINE_TYPING`
- Event limit: 250; configured scenarios: 201 events
- Partial-refresh limit: 100
- Queue capacity: 128
- Editor capacity: 96 characters
- Viewport: 34 fixed character cells
- Full-refresh interval: 50 refresh commands
- Start guard: `/magwrite_single_line_typing.started`
- Completion guard: `/magwrite_single_line_typing.complete`
- Activation before execution: `False` / `DISABLED`

## Scenarios

1. `ordinary`, 40 WPM, 43 events:
   `THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG`
2. `fast_typing`, 80 WPM, 53 events:
   `MAGWRITE CAPTURES EVERY KEY WHILE THE DISPLAY IS BUSY`
3. `correction`, 80 WPM, 52 events: type
   `TODAY I WROTE A JORUNAL ENTRY`, then Home, Right x18, Delete, Right,
   insert `R`, End; expected `TODAY I WROTE A JOURNAL ENTRY`
4. `viewport`, 80 WPM, 53 events: type
   `PACK MY BOX WITH FIVE DOZEN LIQUOR JUGS`, Left x8, Home, End, Left x4.

## Files copied

Pending physical execution. Required mapping:

```text
magtag/hardware_test_boot.py                 -> /boot.py
magtag/hardware_single_line_typing_test.py   -> /code.py
magtag/config.py                             -> /config.py
magtag/uc8151.py                             -> /uc8151.py
magtag/magwrite/*.py                         -> /magwrite/*.py
```

Results, serial statistics, visual observations, photographs, final activation
state, and guard state remain pending. Host mocks do not establish physical
behavior.

## First physical attempt

- The explicit mode was armed and the `.started` guard was created.
- Serial reconnect incorrectly matched an earlier fail-closed traceback and
  closed before preserving the new run's summary.
- The harness caught a failure before the initial full seed; the display
  retained the prior CircuitPython traceback screen.
- No typing events or typing-test refreshes were verified.
- The attempt was stopped without continuing or retrying.
- Photograph: `PHYSICAL_SINGLE_LINE_TYPING_TEST_ATTEMPT_1.png`
- Guard: `/magwrite_single_line_typing.started` present;
  `/magwrite_single_line_typing.complete` absent.
- Activation was restored to `False` / `DISABLED`.

Conclusion: **INCONCLUSIVE**. A rerun requires explicit authorization and
manual deletion of only the typing-test `.started` guard.

### Authorized second attempt

Clean serial capture identified a CircuitPython compatibility failure before
the initial seed: `str.ljust` is unavailable on CircuitPython 9.1.1. The
persisted failure summary records zero generated/processed events, zero
refreshes, no timeout, and no queue overflow. The start guard remains present,
the completion guard remains absent, and no automatic retry was made.

### Authorized third attempt

The CircuitPython-compatible viewport fix was verified on-device before this
attempt. The initial full seed completed in 3,329 ms without timeout and the
run is paused for visual inspection before event generation.
- Initial checkpoint: user approved the layout and noted that the font is a
  bit small. The fixed font is unchanged for this feasibility run.
- Ordinary insertion: all 43 events processed in order; exact final text
  reached and displayed revision 43 caught up to render revision 43.
- Ordinary final checkpoint: user confirmed good.
- Fast typing: all 53 events processed in order; exact final text reached.
  Multiple document revisions accumulated during active refreshes, intermediate
  snapshots were skipped, and displayed revision 96 caught up to render
  revision 96. Maximum observed queue depth increased to 16 without overflow.
- Fast typing final checkpoint: user confirmed good.
- Correction: all 52 events processed in order. Cursor-only operations advanced
  render revision without falsely advancing document revision. The deliberate
  `JORUNAL` typo was corrected to exact final text
  `TODAY I WROTE A JOURNAL ENTRY`; displayed revision 148 caught up.
- Correction final checkpoint: user confirmed good.
- Viewport: all 53 events processed in order. The authoritative 39-character
  line remained exact through Left x8, Home, End, and Left x4; document
  revision stayed 166 during cursor-only motion and displayed revision 201
  caught up to render revision 201. Maximum observed queue depth was 17.

## Successful physical result

- Completed: 2026-07-28, America/Toronto
- Exact files copied: `/boot.py`, `/code.py`, `/config.py`, `/uc8151.py`, and
  `/magwrite/*.py` from the mappings above
- Initial full seed: 3,329 ms
- Events generated/processed: 201/201
- Events rejected and queue overflows: 0/0
- Maximum queue depth: 18 of 128
- Document/render/in-flight/displayed revisions: 166/201/none/201
- Physical refreshes: 36 partial, 1 full
- Periodic full refreshes: 0; the only full refresh was the initial seed
- Stale snapshots skipped: 165
- Catch-up refreshes: 32
- Partial completion-observation latency: 714 ms minimum, 5,758 ms maximum,
  1,711.6 ms mean, 1,533.7 ms standard deviation
- Timeouts and busy anomalies: 0
- Completion guard: `/magwrite_single_line_typing.complete`, present
- Start guard: `/magwrite_single_line_typing.started`, present
- Activation after run: `False` / `DISABLED`, repository/device hashes equal

The completion latency includes time spent rendering every intermediate event
before the cooperative loop polled the busy pin. Final catch-up refreshes were
approximately 715–718 ms, consistent with the characterized panel. Rendering
only once after draining currently due events is the main scheduler improvement
identified by this run.

## Visual observations

- User approved the initial layout, all four final scenario states, and the
  final cursor position.
- The font was readable but described as a bit small.
- The final cursor appeared on the `J` cell of `JUGS`; `UGS` was intentionally
  outside the fixed viewport and represented as hidden text at the right edge.
- No unexpected flashing, incomplete erasure, severe ghosting, border
  corruption, pixel degradation, heating, or unstable power was reported.
- No successful-run photographs were supplied. The only photograph is from the
  earlier inconclusive attempt and is not represented as PASS evidence.

Conclusion: **PASS**. Every event was processed once in order, all four final
texts matched exactly, the queue remained bounded without overflow, stale
frames were coalesced, each scenario caught up physically, and the device was
returned to its safe disabled state.
