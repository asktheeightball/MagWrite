# MagWrite Development Runtime

The everyday way to bring MagWrite up on the bench. Not a test, not a harness,
and it produces no evidence.

```text
wired USB keyboard -> Fruit Jam (authoritative editor) -> UART -> MagTag (display)
```

Everything that runs is the code the milestone at commit `e75aa55` physically
verified: the same `LiveTypingSession`, editor, layout, viewport builder,
protocol, and acknowledgement tracker, plus the adaptive pacing and TH40
keyboard work from `fbed96f`. The Fruit Jam stays authoritative for the
document, the cursor, and both revisions. The MagTag stays display-only.

## Why this exists separately from the harnesses

Every guarded harness in this repository exists to produce evidence **once**,
and pays for that with:

- a one-shot `.started` guard it claims and never releases;
- a refusal to run a second time;
- a filesystem remounted away from the USB host so the guard can be persisted;
- `supervisor.runtime.autoreload` disabled;
- certification ceilings on frames, viewports, and partial refreshes;
- a PASS/FAIL verdict and an evidence file.

That is correct for certification and wrong for development, where the whole
point is to start it, watch it, change something, and start it again. The
V1 responsiveness attempt recorded in `MAGWRITE_V1_RESPONSIVENESS_TEST.md`
failed on exactly that friction, having consumed a guard family without
producing a measurement.

So the development runtime has none of it:

| | Guarded harness | Development runtime |
| --- | --- | --- |
| One-shot guard | claims one | **none, ever** |
| Second start | refused | allowed, any number of times |
| Filesystem | remounted away from the host | left with the host |
| Autoreload | disabled | left on — saving a file restarts it |
| Ceilings | authorised certification limits | raised, but still bounded |
| Verdict | PASS or FAIL | none; it just reports what happened |
| Recovery after failure | guard consumed, often needs safe mode | reset and go again |

The harnesses are untouched and stay available for the next real verification
milestone. Nothing here reads, writes, or requires the absence of any guard.

## Files

| Board | Entry point | Activation |
| --- | --- | --- |
| Fruit Jam | `fruitjam/dev_runtime.py` | `ENABLE_DEV_RUNTIME` + `DEV_RUNTIME_MODE = "FRUITJAM_DEV_RUNTIME"` |
| MagTag | `magtag/dev_display_runtime.py` | `PHYSICAL_TEST_MODE` + `DEV_DISPLAY_RUNTIME_MODE = "MAGTAG_DEV_DISPLAY"` |

Both ship **disabled**, like everything else that can drive hardware.

`MAGTAG_DEV_DISPLAY` is deliberately absent from the boot remount gate in
`magtag/hardware_test_boot.py`, and there is no Fruit Jam boot branch for
`FRUITJAM_DEV_RUNTIME`. That absence is the mechanism, not an oversight: with no
remount, CIRCUITPY stays writable by the host on both boards, which is what
makes the loop repeatable.

V1.2 persistence does not change any of that. The microSD card is a **separate
filesystem** from CIRCUITPY, so mounting it needs no `storage.remount`: the host
keeps the drive, autoreload stays on, and saving a file still restarts the board.
A missing or unmountable card is a reported degraded mode, never a refusal to
start — the editor runs and the panel shows `x`.

## Wiring

Unchanged from the verified milestone, and physically confirmed:

- Fruit Jam `A0` TX → MagTag `D10` RX;
- MagTag `A1` TX → Fruit Jam `A1` RX;
- common ground;
- 115200 baud;
- the wired keyboard in the Fruit Jam USB host port.

## Bringing it up

1. Copy the repository files for each board onto its CIRCUITPY volume as usual,
   including `dev_runtime.py` / `dev_display_runtime.py`.
2. On the **MagTag**, set in `config.py`:

   ```python
   ENABLE_PHYSICAL_DISPLAY = True
   PHYSICAL_TEST_MODE = "MAGTAG_DEV_DISPLAY"
   ENABLE_UART_RECEIVER = True
   ENABLE_UART_STATUS_TX = True
   DEV_DISPLAY_RUNTIME_MODE = "MAGTAG_DEV_DISPLAY"
   ```

   Wait for `dev_display_ready` on its console.
3. On the **Fruit Jam**, set in `config.py`:

   ```python
   ENABLE_DEV_RUNTIME = True
   DEV_RUNTIME_MODE = "FRUITJAM_DEV_RUNTIME"
   ```

   It logs `dev_runtime_ready` — which now carries `storage_status`,
   `mount_point`, and `save_state` — waits `STARTUP_DELAY_SECONDS`, then
   handshakes. If a document was recovered from the card, `document_recovery` and
   `live_document_restored` appear too, and the editor opens on that document
   with its cursor where it was.
4. The panel opens on the **main menu**: Journal, Quick Note, Drafts, Recent.
   Move with **Up** and **Down**, open with **Enter**. If a document was
   recovered the runtime skips the menu and opens straight into the editor on it.
5. Type. The MagTag trails and catches up. **Ctrl-S** saves immediately.
   **Escape** leaves the editor to the save screen, which checkpoints on the way
   through; from there **Enter** goes to the menu and **Escape** goes back into
   the document. See `docs/SHELL.md`.

To run the pre-shell V1.2 behaviour instead, set `ENABLE_SHELL = False` on the
Fruit Jam. Everything below then behaves exactly as it did before V1.3.

Start the MagTag first. It is the side that answers the handshake, and starting
it second just means the Fruit Jam's first HELLO goes nowhere.

`tools/capture_serial.py` will record either console read-only if you want a
log. It never writes to the port.

## Stopping and restarting

- **Clean stop:** press **Escape**, HID usage `0x29`, or the **Application
  (menu) key**, `0x65`. Either drains the session, forces out and reconciles the
  final viewport, and logs `dev_runtime_session_summary` followed by
  `dev_runtime_stopped`.

  **With the shell on, that gesture means *back*, and the stop is the one taken
  at the main menu.** Inside a document it goes to the save screen instead, so
  reaching the stop from the editor is: Escape, Enter, Escape. `dev_runtime_ready`
  reports `"stop_from": "MAIN_MENU"` when the shell is active and
  `"stop_from": "ANYWHERE"` when it is not. Watch `shell_transition` on the
  console to see where each press landed.

  On the **EPOMAKER TH40**, Escape is the one that works, and two sessions on
  2026-07-29 confirm it: usage `0x29` arrives cleanly and stops the runtime. The
  key labelled Application sends modifier `0x40` with **no usage byte**, so
  nothing reaches the board as a finish request and the session stays live until
  the idle bound. Watch for `usb_keyboard_finish_requested` on the console; if a
  keypress meant to stop the run produced only a `hid_report_received` with a
  modifier and no keys, that key is on an Fn layer and did not stop anything.
- **Restart:** press reset, press Ctrl-D at the REPL, or simply save any file
  over USB — autoreload is on. No guard to clear, no file to delete, no safe
  mode.
- **Ctrl-C** at either console is treated as a legitimate stop, not a fault.
- The MagTag does not need restarting between **completed** Fruit Jam sessions.
  When a session completes it logs `dev_display_session_summary`, rebuilds its
  parser and scheduler, logs `dev_display_awaiting_next_session`, and is ready
  for the next start.

  **After an interrupted session it does.** A Fruit Jam that vanished mid-frame —
  a pulled cable, a reset, a timeout — leaves the MagTag holding parser state
  from a session that never ended, and the next Fruit Jam's handshake arrives
  looking like a duplicate. The MagTag stops with `duplicate or reversed input
  sequence` and `sessions_served: 0`, and the Fruit Jam reports `status_hello
  timeout` and ends `result: ERROR`. Neither message names the real cause. Both
  boards are fine; restart the MagTag first, wait for `dev_display_ready`, then
  restart the Fruit Jam. This cost two false starts during the V1.3 bench run.

If construction fails — no keyboard, a bad pin alias, a driver hash mismatch —
the board logs `dev_runtime_construction_failed` or
`dev_display_construction_failed` with the detail and stops. Because nothing was
ever remounted, the filesystem is still yours: fix the file, save it, go again.

## Diagnostics

Ordinary bounded JSON lines on each console. Nothing accumulates in memory: the
Fruit Jam's latency figures are running aggregates, and the MagTag drains its
refresh completions into a running aggregate every pass rather than keeping a
list.

Fruit Jam: `dev_runtime_ready`, `live_event_processed`, `live_viewport_sent`
(with the pacing reason that released it), `live_status_received`,
`live_viewport_superseded`, `live_typing_finished`, `live_test_complete`,
`dev_runtime_session_summary`, `dev_runtime_stopped`.

Persistence adds `sd_mounted` or one of `sd_absent` / `sd_unmountable` /
`sd_not_configured` / `sd_spi_failed` / `sd_init_failed`, then
`document_recovery`, `live_document_restored`, `document_journaled`,
`document_checkpointed`, `usb_keyboard_save_requested`, and
`document_save_failed`.

The shell adds `shell_restored`, `shell_transition`, `shell_mode_entered`,
`shell_selection_moved`, `shell_left_editor`, and `shell_fault`. A wrong pin alias reports the `SD`-prefixed names the
board actually exposes, so it is one line to read rather than a hunt.

MagTag: `dev_display_ready`, `dev_display_status_sent`,
`dev_display_session_summary`, `dev_display_awaiting_next_session`,
`dev_display_stopped`.

The session summary carries the full transport and editor picture — events
processed and rejected, queue depth, viewport frames built, sent, superseded and
accepted, final transmitted and displayed revision, final hash, CRC failures,
resynchronisation events, the pacing regime counts, and the passive latency
aggregates. It reports; it does not judge. There is no PASS and no FAIL.

## Bounds that remain, and why

Absence of ceilings is not the goal; absence of *certification* ceilings is. An
unbounded counter on a microcontroller is still a bug.

- Transport frame budgets are raised far above the authorised ceilings
  (`DEV_MAX_VIEWPORT_FRAMES`, `DEV_MAX_PROTOCOL_FRAMES`) rather than removed.
  The guarded harnesses pass neither and therefore keep the exact values they
  were verified with — a host test asserts that.
- Idle and session timeouts are generous but present, so a board left typing
  into a UART nobody is watching eventually gives up.
- The MagTag keeps its display busy timeout. That one is a fault detector, not a
  budget: a panel that never reports itself idle is broken at any hour.
- Queue capacities, the USB poll budget, and the status frame budget are
  unchanged from the verified configuration.

## What this runtime does not do

It performs no verification and licenses no claim. A session that looks good is
an impression, not a measurement, and the summary's latency aggregates are
development instrumentation rather than evidence. Any future claim about
responsiveness needs its own plan, its own fresh guard paths, and its own
authorisation.

It also does not change the panel's refresh policy: the first viewport of each
session is a full refresh and the rest are partial, exactly as in the verified
code. Long unattended development sessions accumulate partial refreshes without
the periodic full refresh a production cadence would want. That is a known gap
belonging to product hardening, not to this runtime.
