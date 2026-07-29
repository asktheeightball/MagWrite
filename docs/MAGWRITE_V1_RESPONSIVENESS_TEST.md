# MagWrite V1 Phase 1 — Responsiveness and Keyboard Verification

**Status: PREPARED, NOT YET RUN.** No guard has been created, no board has been
armed, and no physical measurement exists. Everything in this document is a
plan and a set of pass criteria. Nothing here is a result.

Authorisation for the four guard paths in "Guards" below is required before any
of it happens.

## Purpose

The adaptive pacing policy and the TH40 keyboard-layout rule are host-verified
only. This run exists to answer two questions with numbers rather than
impressions:

1. does the display actually keep up with live typing better than the previous
   fixed 2.6 s send interval did?
2. does the TH40 compatibility mapping actually produce an apostrophe on real
   hardware?

## Relationship to the completed USB-keyboard milestone

This is an **independent phase with its own guards, activation modes, entry
points, and evidence files.** It is not a re-run of the USB-keyboard milestone
and must not disturb it.

The following four guards belong to that completed, physically verified
milestone. They exist on the two boards and **must remain byte-identical.**
This phase never reads, writes, renames, deletes, or requires the absence of
any of them:

| Device | Guard |
| --- | --- |
| Fruit Jam | `/magwrite_usb_keyboard.started` |
| Fruit Jam | `/magwrite_usb_keyboard.complete` |
| MagTag | `/magwrite_usb_keyboard_display.started` |
| MagTag | `/magwrite_usb_keyboard_display.complete` |

The same protection applies to the twenty guards from earlier milestones. The
completed milestone's entry points, `fruitjam/hardware_usb_keyboard_test.py` and
`magtag/hardware_usb_keyboard_display_test.py`, are **unmodified**; this phase
added siblings rather than editing proven code.

Its evidence files — `FRUITJAM_USB_KEYBOARD_TEST.md`,
`FRUITJAM_USB_KEYBOARD_SERIAL.jsonl`, `MAGTAG_USB_KEYBOARD_DISPLAY_SERIAL.jsonl`
— are likewise closed. This phase writes only its own, listed below.

## Guards

New and independent, requiring explicit authorisation:

| Device | Started | Complete |
| --- | --- | --- |
| Fruit Jam | `/magwrite_v1_responsiveness.started` | `/magwrite_v1_responsiveness.complete` |
| MagTag | `/magwrite_v1_responsiveness_display.started` | `/magwrite_v1_responsiveness_display.complete` |

Either device refuses to run if **its own** started or complete guard already
exists. One guarded attempt. The harness never retries automatically.

## Activation

Both devices ship disabled and fail closed.

Fruit Jam `config.py`, currently:

```python
ENABLE_V1_RESPONSIVENESS_TEST = False
V1_RESPONSIVENESS_TEST_MODE = "DISABLED"
```

Armed values:

```python
ENABLE_V1_RESPONSIVENESS_TEST = True
V1_RESPONSIVENESS_TEST_MODE = "FRUITJAM_V1_RESPONSIVENESS"
```

MagTag `config.py`, currently:

```python
ENABLE_PHYSICAL_DISPLAY = False
ENABLE_UART_RECEIVER = False
ENABLE_UART_STATUS_TX = False
PHYSICAL_TEST_MODE = "DISABLED"
V1_RESPONSIVENESS_DISPLAY_TEST_MODE = "DISABLED"
```

Armed values:

```python
ENABLE_PHYSICAL_DISPLAY = True
ENABLE_UART_RECEIVER = True
ENABLE_UART_STATUS_TX = True
PHYSICAL_TEST_MODE = "MAGTAG_V1_RESPONSIVENESS_DISPLAY"
V1_RESPONSIVENESS_DISPLAY_TEST_MODE = "MAGTAG_V1_RESPONSIVENESS_DISPLAY"
```

Entry points: `fruitjam/hardware_v1_responsiveness_test.py` and
`magtag/hardware_v1_responsiveness_display_test.py`.

## Evidence

Written by this phase only:

- `docs/MAGWRITE_V1_RESPONSIVENESS_TEST.md` — this document, with results
  appended after the run;
- `docs/FRUITJAM_V1_RESPONSIVENESS_SERIAL.jsonl`;
- `docs/MAGTAG_V1_RESPONSIVENESS_SERIAL.jsonl`.

## Ceilings

Unchanged from the completed milestone, and enforced by both entry points:

| Bound | Ceiling |
| --- | --- |
| Normalized keyboard events | 500 |
| Viewport frames | 100 |
| Protocol frames per direction | 200 |
| Partial refreshes | 50 |
| Initial full refreshes | 1 |
| Guarded physical attempts | 1 |

Fifty partial refreshes remains the binding ceiling. If a typing pattern would
exceed it, the harness stops with an explicit stop condition rather than quietly
over-running an authorised physical limit.

## Scope

The keyboard is an **EPOMAKER TH40**, `36B0:304E`, wired, no hub. Scope is
restricted to what that keyboard can safely produce while staying in USB mode.

### In scope

- first-burst display response;
- catch-up after a typing pause;
- sustained typing while the display refreshes;
- apostrophe through the TH40 compatibility mapping (`0x2E → 0x34`);
- double quote (Shift plus the same key);
- Caps Lock on and off, **if reachable without a mode switch**;
- Shift plus Caps Lock, **if reachable**;
- Backspace repeat;
- arrow-key repeat;
- printable-character repeat;
- repeat cancellation on release;
- Application key `0x65` as FINISH;
- final revision and hash reconciliation;
- `DISPLAY_CAUGHT_UP`;
- `TEST_COMPLETE`;
- no input loss, no duplication, no queue overflow, no CRC failure, no timeout.

### Explicitly out of scope, and why

**Home, End and Delete are not required on this keyboard and must not be
attempted.** Every probe attempt at the TH40's Fn layer switched the keyboard
out of USB mode entirely, producing zero reports across tens of thousands of
polls. They stay **host-verified only** and are recorded as
**physically untested** on this keyboard, because the TH40 cannot emit Home,
End or Delete without leaving USB mode. This is a keyboard-layout limitation,
not an adapter fault.

Escape `0x29` is likewise not attempted; it is behind the same Fn layer.
Application `0x65` is the usable finish control.

## Required measurements

The Fruit Jam's `LatencyRecorder` captures these automatically and reports them
in its summary. Each is anchored to the **first keypress that made the display
stale** since the previous transmission — the keystroke whose result the writer
is actually waiting on.

| Measurement | Summary field |
| --- | --- |
| keypress to frame transmission | `latency_keypress_to_send` |
| keypress to refresh start | `latency_keypress_to_refresh_start` |
| keypress to refresh completion | `latency_keypress_to_refresh_complete` |
| pause to catch-up transmission | `latency_keypress_to_send_caught_up` |
| maximum visible lag during sustained typing | `latency_keypress_to_send_sustained` → `max` |
| frame count under several short pauses | `latency_frames_after_pause`, `latency_pauses_observed` |

Each reports count, minimum, mean and maximum. The MagTag separately reports
`partial_refresh_minimum_ms`, `partial_refresh_maximum_ms`,
`partial_refresh_mean_ms` and the full `refresh_durations_ms` list, so the
panel's contribution can be separated from the Fruit Jam's.

### Comparison against the prior fixed 2.6 s behaviour

**The comparison is partly derived, and this must not be presented otherwise.**
The completed USB-keyboard run's records carry no timestamps, so it produced no
measured keypress-to-frame latency. There is no measured baseline to compare
against.

What can honestly be said:

- **Derived baseline.** Under the fixed policy, a viewport could only be sent
  once 2.6 s had elapsed since the previous send, with no pause or onset
  exception. A stale-making keypress therefore waited up to 2.6 s regardless of
  whether the writer had stopped typing, and the panel was often idle for most
  of that window.
- **Measured baseline that does exist.** The prior run's panel timings: full
  refresh 3500 ms, partial refreshes 873–1122 ms, mean ≈1050 ms, across 49
  frames and 48 partial refreshes.

So the comparison to report is: measured `latency_keypress_to_send_caught_up`
against the derived 2.6 s fixed-policy ceiling, and measured
`latency_keypress_to_send_sustained` against the same 2.6 s, which the adaptive
policy deliberately retains during sustained typing. A pass on the catch-up path
is a measured number below 2.6 s. A pass on sustained typing is a measured
number that has not regressed above it.

Frame count against the 50-refresh ceiling must also be reported, since the
catch-up path can add one frame per pause.

## Procedure

1. Confirm `main`, clean tree, synchronized with `origin/main`.
2. Confirm both `config.py` files are still fully disabled.
3. Inventory **every** existing guard on both boards by SHA-256, including the
   four completed-milestone guards, and record the inventory.
4. Confirm none of the four new guard paths exists on either board.
5. Deploy both new entry points and the `magwrite_transport` modules.
6. Arm the MagTag first, then the Fruit Jam, with the values above.
7. Do not write to either board's serial port once a harness is armed; use the
   reset button.
8. Run the scenarios below in order, once.
9. Capture both serial streams to the two new evidence files.
10. Re-verify every prior guard by SHA-256 and confirm byte-identical.
11. Record the operator's visual assessment separately from the measured
    numbers.

## Scenarios

Run once, in order, within the ceilings.

1. **First burst.** From idle, type a short sentence at a normal rate. Observe
   how quickly the first text appears.
2. **Pause and catch up.** Stop mid-sentence for several seconds. Observe
   whether the panel catches up promptly rather than after a long wait.
3. **Sustained typing.** Type continuously for a paragraph. Confirm the display
   keeps advancing rather than stalling until the end.
4. **Several short pauses.** Type in three or four bursts separated by short
   pauses, to exercise the frame-count-under-pauses measurement.
5. **Apostrophe and double quote.** Type `It's a "test" and I don't mind.`
6. **Caps Lock**, only if reachable without a mode switch: type a lowercase
   letter, Caps Lock on, two letters, Shift plus a letter, Caps Lock off, a
   letter.
7. **Repeats.** Hold a printable key, then an arrow key, then Backspace, each
   long enough to repeat, releasing each cleanly.
8. **Finish.** Press the Application key.

## Pass criteria

Every one of the following, or the run is a FAIL:

- both summaries reconcile: final transmitted revision equals final displayed
  revision equals final viewport revision, and both hashes agree;
- `TEST_COMPLETE` true and `DISPLAY_CAUGHT_UP` received;
- events processed equals events normalized; 0 rejected, 0 queue overflows,
  0 CRC failures, 0 timeouts, 0 parser rejections;
- no ceiling exceeded;
- the apostrophe and double quote appear in the final document;
- `remapped_usages` greater than 0 and `keyboard_layout` is `EPOMAKER_TH40`;
- `repeat_events` greater than 0, and no repeat continued after release;
- all six required measurements captured with a non-zero count;
- measured catch-up latency below 2.6 s;
- measured sustained latency not above 2.6 s plus one refresh;
- all four new guards written, and every prior guard byte-identical.

**Subjective observation alone is not a pass.** The operator's visual
assessment is recorded, and recorded as separate from the measured timing.
Neither substitutes for the other. If the numbers improve and the panel still
looks wrong, that is a finding, not a pass.

## On failure

Stop both state machines. Preserve both `.started` guards. Preserve every
captured record. Do not delete guards, do not retry automatically, and do not
re-arm without fresh explicit authorisation naming the exact paths.

## Results

*(To be appended after an authorised run. Empty until then.)*
