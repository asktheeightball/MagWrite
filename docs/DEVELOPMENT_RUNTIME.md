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

### The card appears on the host too, and you should leave it alone

On CircuitPython 10.2.1 the Fruit Jam **auto-mounts the microSD at `/sd` before
user code runs and publishes it to the host as a third USB drive**, alongside
CIRCUITPY and CPSAVES. All three are LUNs of the same device. Expect a third
drive letter whenever a card is seated.

Nothing needs configuring for this: `sd_storage.mount()` finds `/sd` already
mounted, adopts it, and logs

```json
{"event":"sd_already_mounted","mount_point":"/sd"}
```

with `storage_detail: "adopted a filesystem already mounted at /sd"`. The
adoption path was written for restartability and covers this unchanged. A bare
`busio.SPI(board.SD_SCK, ...)` will raise `ValueError: SD_SCK in use`, which is
the firmware holding the bus, not a wiring fault.

**Do not open, browse, write to, or eject that drive while a session is live.**
The board owns the volume and writes it underneath the host, so the host's cached
view goes stale within seconds: every non-empty file then reports "The file or
directory is corrupted and unreadable" from Windows while the board reads all of
them perfectly. The card is fine. Reading it from the host mid-session tells you
nothing, and writing to it puts a second writer on the only copy of somebody's
document.

To read the card back honestly, stop the session and run
`tools/fruitjam_recovery_check.py` on the board — it reports what recovery would
actually return, through the real store, and writes nothing.

## Wiring

Unchanged from the verified milestone, and physically confirmed:

- Fruit Jam `A0` TX → MagTag `D10` RX;
- MagTag `A1` TX → Fruit Jam `A1` RX;
- common ground;
- 115200 baud;
- the wired keyboard in the Fruit Jam USB host port.

## Power

Two USB-C cables from the PC still works and is what every verified run so far
used. The tidier arrangement is **one upstream USB-C cable into a powered hub,
and one short cable from the hub into each board's own USB-C port** — same
consoles, same host-writable volumes, one cable to the bench. Move the upstream
end to a wall charger and the same rig runs standalone with nothing else changed.

**Never feed one board's 5 V into the other**, and never let the red conductor of
a 3-pin JST cable connect the two: on both boards that pin is 5 V by default.
Neither board has a 5 V input, and the reasoning is in
[BENCH_POWER.md](BENCH_POWER.md).

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

   Wait for `dev_display_ready` on its console. From V1.5 it carries
   `"buttons": true` when the four front buttons were claimed, and
   `"buttons": false` with a `button_detail` reason when they were not —
   `ENABLE_MAGTAG_BUTTONS` ships **enabled**, unlike every harness, because the
   buttons are the product's control surface rather than a hardware experiment.
   A board that cannot claim them still runs; the keyboard still drives the
   shell.
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
   If a document was recovered the runtime skips the menu and opens straight into
   the editor on it, in the mode that document belongs to.
5. Navigate with the **four MagTag buttons**, which are the primary controls from
   V1.5:

   | Button | Action |
   | --- | --- |
   | A | go to the main menu; from a document, checkpoint and go there |
   | B | move the selection up |
   | C | move the selection down |
   | D | open the selected item; dismiss the error screen |

   Button A at the main menu does nothing — it cannot end the session. No button
   reaches the document: in the editor everything except A is ignored and
   counted.

   The keyboard keeps the same controls as a fallback: **Up**, **Down**,
   **Enter**, **Escape**.
6. Type. The MagTag trails and catches up. **Ctrl-S** saves immediately.
   **Escape** (or button A) checkpoints the document and returns straight to the
   menu — silently, with no save screen and no confirmation keypress. Only a save
   that actually *failed* shows a screen. See `docs/SHELL.md`.

### What each menu item does, from V1.4

See `docs/MODES.md` for the design.

| Item | What it opens |
| --- | --- |
| Journal | the newest journal entry, cursor at the end of it; a new numbered entry when the last one is nearly full |
| Quick Note | a new, empty document, immediately |
| Drafts | a list of every document, newest first — Up/Down, Enter to open, Escape to go back |
| Recent | the document that was open last |

Leaving one document for another **checkpoints the first one first**, always, so
a mode switch never hands a document over with work only in RAM.

### Deploying V1.4 onto a card that already has a draft

Nothing to do, and deliberately nothing to undo. The V1.2/V1.3 files are already
correct under the per-document naming, so the first V1.4 start adopts the
existing document by appending one catalogue record and opening it. Watch for:

```json
{"event":"document_migrated","document_id":"active","kind":"DRAFT"}
{"event":"document_catalogue","documents":1,"active_document":"active"}
```

The existing draft appears in **Drafts** as `DRAFT`. No file is moved, renamed,
or rewritten, and `recovery/checkpoint.log` is left exactly where it is.

Two new files appear over the first session: `/sd/magwrite/index.log`, and a
`recovery/active.ckpt.log` at the first checkpoint.

To read the card back without starting a session, `tools/fruitjam_recovery_check.py`
now reports the catalogue, every entry, and the active document before the text.

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
  at the main menu.** Inside a document it checkpoints and returns to the menu
  instead, so reaching the stop from the editor is: Escape, Escape.
  `dev_runtime_ready`
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
`shell_selection_moved`, `shell_left_editor` — which carries `save_action` and
`save_state`, so a silent checkpoint stays auditable now that it draws no
screen — and `shell_fault`. A wrong pin alias reports the `SD`-prefixed names the
board actually exposes, so it is one line to read rather than a hunt.

Buttons add `dev_display_buttons_ready` or `dev_display_buttons_unavailable` and
`dev_display_button_pressed` on the MagTag, and `button_event_received` plus
`shell_button_applied` on the Fruit Jam. A press can therefore be followed from
the contact to the transition it caused: if a button does nothing, whichever of
those four lines is missing says where it stopped.

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
