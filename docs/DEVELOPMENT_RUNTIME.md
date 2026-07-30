# MagWrite Development Runtime

The everyday way to bring MagWrite up on the bench. Not a test, not a harness,
and it produces no evidence.

**From V1.6 this is the profile you opt into.** The shipped configuration is the
standalone writing appliance — see [STANDALONE.md](STANDALONE.md) — and the two
run the same code from the same files. This profile differs in exactly four
bounds and one gesture:

| | Standalone (shipped) | Development (this page) |
| --- | --- | --- |
| Idle / session timeout | none | 1800 s / 7200 s |
| Keyboard event bound | none | 100,000 |
| Viewport / protocol frames | none | 100,000 / 200,000 |
| Escape at the main menu | nothing | the clean stop |

Everything else on this page applies to both. The ready line, the session
summary, and the stopped record each carry `"profile"`, so a console says which
one is running before anything else happens.

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

Both activation *pairs* ship **disabled**, so this profile has to be asked for.
The files themselves are not disabled and have not been since V1.6: the same two
modules run the standalone appliance, selected by `ENABLE_STANDALONE` /
`STANDALONE_MODE` on the Fruit Jam and `ENABLE_STANDALONE` /
`STANDALONE_DISPLAY_MODE` on the MagTag, both of which ship **enabled**. A board
armed for this profile wins, because the entry points check it first.

The names are kept deliberately. `dev_runtime_ready`, `dev_display_ready`, and
the rest are the vocabulary every physical evidence file in this repository is
written in; renaming them would make the record harder to read in exchange for a
tidier filename. `"profile"` is how the two are told apart.

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
used, and it is the arrangement this profile wants: two consoles and two
host-writable volumes. One upstream cable into a powered hub, and one short cable
from the hub into each board's own USB-C port, gives the same thing over one
cable to the bench.

The **standalone** arrangement — one cable into the Fruit Jam, the MagTag off one
of its USB-A host ports — is what `docs/BENCH_POWER.md` verified and what
`docs/STANDALONE.md` describes. It has no MagTag console and no host-visible
MagTag `CIRCUITPY`, which is why the MagTag must be deployed *first*.

**Never feed one board's 5 V into the other**, and never let the red conductor of
a 3-pin JST cable connect the two: on both boards that pin is 5 V by default.
Neither board has a 5 V input, and the reasoning is in
[BENCH_POWER.md](BENCH_POWER.md).

## Bringing it up

1. Copy the repository files for each board onto its CIRCUITPY volume as usual,
   including `dev_runtime.py` / `dev_display_runtime.py`.
2. On the **MagTag**, set in `config.py` — only `PHYSICAL_TEST_MODE` and
   `DEV_DISPLAY_RUNTIME_MODE` differ from the shipped values:

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
   the editor on it, in the mode that document belongs to. Before either, the
   MagTag draws `MAGWRITE / STARTING` of its own accord, and
   `WAITING FOR THE WRITER BOARD` if the Fruit Jam has said nothing for 15 s.
   A menu row reading `NO KEYBOARD - PLUG ONE IN`, and a `k` beside the save
   indicator, mean no keyboard is claimed yet; the device keeps looking, so
   plugging one in is enough and no reset is needed.
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

**Start order: there isn't one any more.** Under one-cable bench power the MagTag
is fed from a Fruit Jam USB-A host port, and those ports carry no 5 V while the
Fruit Jam is held in reset — so "start the MagTag first" is not a sequence the
hardware can perform. Both boards cold boot together, the Fruit Jam wins the race
because it has no e-paper panel to initialise, and its first HELLO does indeed go
nowhere. That is now the ordinary case rather than a fault:

- the Fruit Jam re-sends the handshake every
  `DISPLAY_HANDSHAKE_RETRY_SECONDS` (3.0) until the panel answers, indefinitely,
  logging `live_waiting_for_display` with the attempt number, how long it has
  been waiting, and how many characters of document it is holding;
- `live_typing_started` then carries `hello_attempts` and `display_wait_seconds`,
  so a session says in one line how long its panel took;
- a restored document is loaded before any of this and is not read, re-derived,
  or re-saved while the wait runs. The words simply wait;
- the session and idle clocks start when the panel answers, so a slow display
  does not spend the writing session's budget.

On the powered-hub arrangement, where both boards have their own USB-C cable,
starting the MagTag first still works and simply makes the wait zero.

Keystrokes are polled during the wait but not applied, because there is no panel
to show them on. They queue, and the bounded input queue holds 64 events — about
32 keystrokes, which are all applied the moment the panel answers.

**Fixed in V1.6:** overflowing that queue used to *end the session*. It was
recorded here as a limitation and it was one; one-cable power made it likely,
because the writer now connects a cable and waits nine seconds at a blank panel,
and some of them will start typing. The overflow is now dropped and counted, and
named once as `live_input_dropped_waiting_for_display` with the queue capacity in
it. Losing the tail of a sentence typed at a blank panel is a small cost; a device
that switches itself off because somebody was keen is not.

`tools/capture_serial.py` will record either console read-only if you want a
log. It never writes to the port.

## Stopping and restarting

**There is no clean stop in the standalone profile.** Escape at the main menu
does nothing there, `dev_runtime_ready` reports `"stop_from": "NOWHERE"`, and the
way to stop the device is to remove power — which is safe at any moment, because
every editor exit checkpoints. Everything below is the development profile.

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

  **After an interrupted session it no longer does either.** A Fruit Jam that
  vanished mid-frame — a pulled cable, a reset, a timeout — used to leave the
  MagTag holding parser state from a session that never ended, so the next Fruit
  Jam's handshake arrived looking like a duplicate. The MagTag stopped with
  `duplicate or reversed input sequence` and `sessions_served: 0`, and the Fruit
  Jam reported `status_hello timeout` and ended `result: ERROR`. Neither message
  named the real cause; both boards were fine; the fix was to restart the MagTag
  first. It cost false starts in the V1.3, V1.4, and dongle bench runs.

  Retired with one-cable power, which made the old fix impossible to perform:

  - **the MagTag lets a `HELLO` re-baseline its input numbering**, but only while
    it has displayed nothing — nothing accepted, pending, in flight, or about to
    start. A handshake is the beginning of a count, not a continuation of one.
    Once the writer's words are moving through the link, sequence discipline is
    absolute again and a repeat or a gap is still a fault;
  - **the Fruit Jam keeps its frame numbering monotonic across attempts** — a
    retry that restarted the count is exactly what would produce the duplicate —
    and re-baselines the *status* channel each attempt, so a MagTag that boots
    late and numbers its first reply 1 is heard rather than dismissed as stale;
  - a fault during the handshake — a stale reply, a fragment clocked in while the
    far board was powering up — restarts the handshake with a fresh parser
    instead of ending the session, logging `live_display_handshake_restarted`
    with its cause. The session summary counts them as
    `display_handshake_restarts`.

If construction fails — no keyboard, a bad pin alias, a driver hash mismatch —
the board logs `dev_runtime_construction_failed` or
`dev_display_construction_failed` with the detail and stops. Because nothing was
ever remounted, the filesystem is still yours: fix the file, save it, go again.

## Diagnostics

Ordinary bounded JSON lines on each console. Nothing accumulates in memory: the
Fruit Jam's latency figures are running aggregates, and the MagTag drains its
refresh completions into a running aggregate every pass rather than keeping a
list.

Fruit Jam: `dev_runtime_ready`, `live_waiting_for_display`,
`live_display_handshake_restarted`, `live_typing_started`,
`live_event_processed`, `live_viewport_sent`
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

V1.6 adds `live_keyboard_state` when a keyboard is claimed or lost,
`usb_keyboard_open_failed` and `usb_keyboard_read_failed` with `"fatal": false`
when something on the port could not be driven, `live_input_dropped_waiting_for_display`,
`live_document_restore_refused`, `document_writes_held` / `document_writes_released`,
and `display_startup_screen` on the MagTag for each of its two local screens.

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
- Idle and session timeouts are generous but present **in this profile**, so a
  bench board left typing into a UART nobody is watching eventually gives up.
  They start when the display answers, not when the board boots: a panel that
  took a minute to arrive is not a session that ran long. The standalone profile
  removes both, along with the keyboard event and frame bounds — see
  [STANDALONE.md](STANDALONE.md) for the argument, which is that each of them
  exists to end a *run* and an appliance has no run to end.
- **The wait for the display is deliberately unbounded**, and it is the one bound
  removed rather than raised. A writer who connects one cable is owed a session
  that starts when the panel is ready; a Fruit Jam that gave up four seconds
  early would be a device that does not switch on. It is not a silent wait — every
  attempt logs — and it costs nothing, because nothing has begun.
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
