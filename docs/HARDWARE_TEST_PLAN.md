# Physical MagTag Partial-Refresh Test Plan

Status: **20-update run passed; 50- and 100-update runs not yet run**.
Host simulation cannot satisfy physical criteria.

## Record before testing

- board photographs and silkscreen:
- purchase source/date:
- `boot_out.txt`:
- CircuitPython build: `9.1.1`
- panel/controller evidence:
- power source:
- ambient temperature:
- driver repository, commit, and licence notices:
- harness commit:
- configured full-refresh interval:

Stop if the controller is not positively identified as UC8151D/IL0373
compatible. Do not run the research driver on an SSD1680 panel.

## Setup

1. Install and copy files exactly as described in `docs/HARDWARE_SETUP.md`.
2. Install the approved display adapter only after the revision and GPL gates
   are complete.
3. Open the USB serial console and capture all JSON-lines logs to a timestamped
   file.
4. Photograph the clean initial screen under fixed lighting.
5. Run the deterministic 80 WPM text stream. Keep the event queue capacity,
   full-refresh interval, text, and refresh policy unchanged between runs.

## First controlled 20-update run

This is the only physical run authorized for the initial integration task.
The initial seed is one full refresh and is separate from the 20 controlled
partial updates.

1. Back up every existing file and directory from `CIRCUITPY`, preserving the
   backup outside the repository.
2. Use stable USB power or a sufficiently charged battery.
3. Confirm `docs/HARDWARE_IDENTITY_REPORT.md` says `COMPATIBLE`, controller
   `UC8151D`.
4. Copy the exact files listed in `docs/PHYSICAL_REFRESH_TEST_20.md`, including
   `hardware_test_boot.py` as `/boot.py` and `hardware_refresh_test.py` as
   `/code.py`.
5. Confirm this safe configuration:

   ```python
   ENABLE_PHYSICAL_DISPLAY = False
   PHYSICAL_TEST_MODE = "DISABLED"
   ```

6. Boot once, open serial, and confirm `physical_test_refused`. There must be no
   pin, SPI, or display activity.
7. Deliberately change only:

   ```python
   ENABLE_PHYSICAL_DISPLAY = True
   PHYSICAL_TEST_MODE = "UC8151_20_UPDATE"
   ```

8. Reset once. The gated `/boot.py` remounts the filesystem writable to
   CircuitPython so the persistent guard can be created. The test disables
   autoreload before panel initialization.
9. Capture JSON-lines serial output. Observe one full-screen seed refresh,
   followed by exactly 20 no-flash differential updates.
10. Photograph the screen after the full seed and after partial updates 5, 10,
    and 20.
11. Stop immediately on unexpected full-screen flashing, timeout, incomplete
    erasure, growing pixel defects, border artefacts, or other panel distress.
12. Do not remove `/magwrite_refresh_test_20.started`; it prevents automatic
    reruns. Successful completion also creates
    `/magwrite_refresh_test_20.complete`. The harness then remounts the
    filesystem read-only to CircuitPython so USB can regain write access.
13. Restore:

    ```python
    ENABLE_PHYSICAL_DISPLAY = False
    PHYSICAL_TEST_MODE = "DISABLED"
    ```

14. Preserve the guards, serial output, timings, and photograph filenames in
    `docs/PHYSICAL_REFRESH_TEST_20.md`.
15. The later 50/100 characterization task may proceed only under the guarded
    checkpoint procedure below.

## Controlled 50- and 100-update characterization

Use `hardware_characterization_test.py` as `/code.py`. Test A uses
`REFRESH_50`; Test B uses `REFRESH_100` and is refused unless the reviewed
50-update pass signal exists. Each test begins with a new full seed.

At every `checkpoint_wait`, photograph and inspect the display before typing
`CONTINUE`. Type `STOP` for any visual, electrical, timing, power, or safety
concern. Checkpoints are 0/10/20/30/40/50 for Test A and
0/20/40/60/80/100 for Test B.

The harness stops before another refresh on a timeout, an unexpected full
refresh, a partial duration over 1,500 ms, three consecutive durations over
1,000 ms, persistent timing drift, or a rejected visual checkpoint. Do not
automatically retry a stopped run.

Successful runs create independent `.complete` guards; `.started` remains even
when stopped. To rerun deliberately, first preserve logs and photographs,
disable activation, document why the prior run is invalid, and manually delete
only that run's `.started` and `.complete` guards. Never delete the 20-update
guards. The 50 `.pass` signal is created only after human review and is not a
completion guard.

After every run restore `ENABLE_PHYSICAL_DISPLAY = False` and
`PHYSICAL_TEST_MODE = "DISABLED"`.

## Controlled single-line typing run

This is one bounded run of `hardware_single_line_typing_test.py`; it must not
be repeated without explicit authorization.

1. Back up the complete `CIRCUITPY` volume outside the repository.
2. Confirm stable USB or battery power and inspect the battery/cable.
3. Confirm all existing 20/50/100 guards remain unchanged.
4. Copy only the files listed in
   `docs/PHYSICAL_SINGLE_LINE_TYPING_TEST.md`.
5. Boot with activation disabled and capture `typing_test_refused`; no display
   activity is permitted.
6. Connect serial capture before arming.
7. Set `ENABLE_PHYSICAL_DISPLAY = True` and
   `PHYSICAL_TEST_MODE = "SINGLE_LINE_TYPING"`.
8. Reset once. Confirm one initial full seed and inspect the static layout.
9. At each checkpoint, inspect and photograph where practical, then type
   `CONTINUE` or `STOP`.
10. Observe ordinary 40 WPM insertion, 80 WPM input while partial refresh is
    busy, the explicit correction sequence, and horizontal viewport motion.
11. Confirm characters appear in coalesced groups and each scenario catches up
    before its checkpoint.
12. Stop on any input, display, runtime, power, timing, or guard failure listed
    in the typing-test report. Never automatically retry.
13. Preserve raw JSONL before reset.
14. Restore activation false and mode `DISABLED`, with an explicit filesystem
    flush before reset.
15. Confirm `/magwrite_single_line_typing.complete` exists only after a PASS.

Hard ceilings are 250 editing events and 100 physical partial refreshes.
The provisional full-refresh interval remains 50 refresh commands. Record any
periodic full refresh; do not use this run to establish production cadence.

Do not power off the panel between the full seed and the 20 partial updates.
The controller's NEW-to-OLD differential state is lost on power-off; a later
refresh must then be a full reseed.

## Test matrix

Run fresh sequences ending at each cumulative update count:

| Updates | First full refresh | Partial/no-flash count | Avg/min/max ms | Accepted/lost/reordered | Ghosting/pixels | Photo/log |
|---:|---|---:|---|---|---|---|
| 20 | confirmed, 3,324 ms | 20 no-flash updates observed | partial 718/716/720 ms mean/min/max | 20 completed, zero loss/reorder indicated by harness, zero timeouts | no obvious final-frame ghosting or pixel defect | final photo and serial saved; intermediate photos not captured |
| 50 | confirmed, 3,324 ms | 50 no-flash updates visually approved | partial 717.5/716/719 ms mean/min/max | 50 completed, zero timeouts | user approved every checkpoint; only initial photo supplied | initial photo and complete serial log saved |
| 100 | confirmed, 3,323 ms | 100 no-flash updates visually approved | partial 717.4/713/720 ms mean/min/max | 100 completed, zero timeouts | user approved every checkpoint; no photos supplied | complete serial log saved |
| 500 | pending | pending | pending | pending | pending | pending |
| 1,000 | pending | pending | pending | pending | pending | pending |

At every interval:

1. Confirm the first update was a full refresh.
2. Observe whether later updates avoid the full-screen black/white flash.
3. Compare produced sequence numbers with accepted sequence numbers.
4. Confirm `document_revision == event_count` for the insert-only stream.
5. Confirm events continue to be accepted between `refresh_start` and
   `refresh_end`.
6. Pause input and confirm `displayed_revision == document_revision`.
7. Record partial-refresh duration statistics from logs.
8. Photograph the same test pattern and inspect retained strokes, missing
   pixels, background tint, edge artifacts, and cursor condition.
9. Record each periodic full refresh and whether it clears ghosting.

## Pass/fail rules

- Fail immediately on silent loss, reorder, blocking input, unexpected
  full-screen flashes, gate bypass, or panel distress.
- Queue overflow is a valid stress-test outcome only when explicitly logged; it
  is not a pass for the nominal 80 WPM run.
- Do not mark a row passed without its serial log and visual record.
- After 1,000 updates, choose a tentative full-refresh interval from measured
  ghosting. Record it as provisional pending longer wear testing.
# One-way Fruit Jam UART viewport gate

The dedicated, repeatable, single-run procedure is
`docs/FRUITJAM_MAGTAG_UART_TEST.md`. It requires separate USB power, only TX,
RX input, and common ground, physically confirmed `dir(board)` aliases, two
serial captures connected before reset, independent persistent guards, and
restoration of disabled configuration. Its controlled attempt 3 status is
**PASS**; evidence and retained compatibility failures are in the dedicated
report.
