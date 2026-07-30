# MagWrite Current Priority

This file is the operational companion to `ROADMAP.md`.

## Execution rule

Only stop the current roadmap step for a defect that blocks that step.

Everything else must be recorded for later and must not interrupt delivery.

Do not create new certification harnesses, evidence packages, compatibility investigations, keyboard-polish tasks, or unrelated refactors unless they are required to complete the active roadmap phase.

## Current path

1. ~~Finish the current ordinary writing session.~~ Done.
2. ~~Move directly to V1.2: microSD persistence.~~ Implemented, host-verified.
3. ~~Confirm the microSD pin aliases and run one physical forced-power-loss test.~~ Done 2026-07-30.
4. ~~Build the MagWrite Shell.~~ Implemented, host-verified.
5. ~~Run one physical shell session on the bench.~~ Done 2026-07-30.
6. ~~Add Journal, Quick Note, Drafts, and Recent.~~ Implemented, host-verified.
7. ~~Run one physical two-mode session on the bench.~~ Done 2026-07-30.
8. ~~Fix the shell UX: remove the Save/Status interruption and make the MagTag
   buttons the primary shell controls.~~ Implemented, host-verified.
9. ~~Run the smallest physical bench check of the shell UX.~~ Done 2026-07-30,
   passed with zero faults.
10. ~~Integrate USB dongle keyboard compatibility.~~ Started 2026-07-30 and
    **blocked on hardware**: the only receiver on the bench is incompatible and
    closed, and no other exists here.
11. Bring the bench to one-cable power. **<- current.** Audited 2026-07-30: the
    direct 5 V feed is refused because neither board has a 5 V input. The
    arrangement is now one supply into the Fruit Jam's USB-C with the MagTag fed
    from a Fruit Jam USB-A host port, which removed the board start order
    outright — those ports are dead while the Fruit Jam is in reset. The Fruit
    Jam waits for the display instead of failing; host-verified, awaiting the
    physical check.
12. Complete the minimum standalone workflow.
13. Defer keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**One-cable bench power — AUDITED 2026-07-30. The direct 5 V feed is refused;
the physical check is pending.** The audit is `docs/BENCH_POWER.md`; the account
is in `ROADMAP.md`.

The phase asked which board should take USB-C and which should be fed from the
other's 5 V rail. **Neither, and not because of a margin.** The MagTag's pinout
lists its power inputs exhaustively — the USB-C connector or a 3.7/4.2 V LiPo —
and it has **no 5 V input pin, pad, or header at all**; the only 5 V it exposes
is a 200 mA-rated *output* on its two 3-pin STEMMA connectors. The Fruit Jam's 5V
header pin is likewise a regulator *output*. There was no direction left to
choose, so the direct arrangement is documented as blocked rather than
improvised around.

What is supported, and is the smaller change: **one 5 V source, one upstream
USB-C cable, a powered hub with per-port limiting, one short cable into each
board's own USB-C port.** Both boards stay sinks, both keep their own protection
and regulator, the UART is untouched, and swapping the upstream cable between the
PC and a wall charger is the whole difference between the development and
standalone configurations.

**Corrected the same day, and the correction is the phase's real result.** The
recommended hub is gone: the MagTag is powered from a **Fruit Jam USB-A host
port**, a documented 5 V output feeding a documented USB-C input, so the rig is
genuinely one cable. That arrangement has one consequence that had to be answered
in software rather than in procedure — **the Fruit Jam's USB-A ports carry no 5 V
while it is held in reset**, so the MagTag cannot be started first and both boards
necessarily cold boot together. "Restart the MagTag first" became an instruction
the hardware cannot obey.

So the handshake waits. The Fruit Jam retries every 3 s until the panel answers
rather than failing after one `status_hello timeout`, keeps its frame numbering
monotonic across attempts, re-baselines the status channel each time, and rebuilds
its parser after a failed attempt; the MagTag lets a `HELLO` re-baseline its input
numbering while it has displayed nothing. A restored document is untouched
throughout. Host-verified in `host-tests/test_display_wait.py`; this also retires
the three-time-recurring `duplicate or reversed input sequence` backlog item
below.

Found along the way and worth more than the phase itself: **both boards' 3-pin
JST connectors carry 5 V on the red conductor by default**, so a stock 3-wire
STEMMA cable between `A0` and `D10` would tie the two 5 V rails together with no
intent and no extra part. The "leave red insulated" rule was already right;
`HARDWARE.md` now says why.

Not claimed: any answer to the receiver question. The receiver hangs off the
Fruit Jam's own host port behind `USB_HOST_5V_POWER` and the CH334F, and that
limit is unchanged by anything upstream.

**Not measured:** a single current figure on this bench. A USB power meter on the
upstream cable is what closes the standing checklist item.

## Previous product task

**USB dongle keyboard compatibility — STARTED AND BLOCKED ON HARDWARE
2026-07-30.** Evidence `docs/FRUITJAM_DONGLE_PROBE_SERIAL.jsonl`; the account is
in `ROADMAP.md`.

The only receiver on the bench is the **TH40's own dongle**, `36B0:3002`, which
Priority 3 had already recorded as unsupported. Three further boots reproduced
that exactly: it enumerates on the first attempt, holds the connection, and sends
**zero HID reports** — while the **wired** TH40 in the same port and the same
session delivered 22 reports and typed into the document. The keyboard and
receiver type normally on a host PC. So the failure is the receiver, not the
port, not the adapter, and not the V1.5 build.

**Recorded as incompatible, and closed.** No further time goes to this receiver.

**What unblocks this:** one *ordinary* wireless keyboard with a USB receiver, any
vendor. Nothing in the repository can substitute for it, and no further work on
`36B0:3002` will answer whether the wireless path works at all.

**What was deliberately not settled:** whether USB power is the cause. The
powered-hub test was declined on practical grounds, so `HARDWARE.md`'s
current-supply question stays open. If power is the answer, **one-cable bench
power** — already the next phase — is what changes it, so the dongle question is
worth re-asking after that rather than before.

Carry forward, from V1.4 and V1.5:

- the TH40 character mis-mappings are still unexplained and still in the backlog.
  V1.4 saw `this` → `tgus` and `is` → `us`; V1.5 saw `v15` arrive as `v 12`. A
  second keyboard remains the cheapest experiment that separates "this keyboard"
  from "our HID handling", and is now blocked on the same missing hardware;
- `usb_keyboard_layout_selected` carries an `AUTO` path keyed on vendor and
  product id, and it behaved correctly under test: `36B0:3002` got `STANDARD` HID
  rather than the wired TH40's remap. That seam needs no change for a dongle.

## Next product task

**V1.6, the minimum standalone workflow**, once the one-cable bench check has
run. Bench power moved ahead of the dongle work by necessity rather than by
preference: the dongle phase cannot proceed without hardware that is not here.
The hope that power might change the dongle result has since been narrowed by the
audit — the receiver's supply comes from the Fruit Jam's own host port, not from
upstream — so it is worth re-asking, not worth expecting.

## Completed product tasks

**V1.5 — shell UX and MagTag buttons — PHYSICALLY VERIFIED 2026-07-30.**
Evidence: `docs/FRUITJAM_V15_BENCH_SERIAL.jsonl` and
`docs/MAGTAG_V15_BENCH_SERIAL.jsonl`; the full account is in `ROADMAP.md` and
`docs/SHELL.md`.

The smallest check that settles it, run on a document **recovered from the V1.4
session** rather than a fresh one. All six steps passed with zero faults:

1. Escape produced one silent checkpoint and one transition straight to the main
   menu — no save screen, no second keypress, `save_failures: 0`;
2. the buttons moved the selection up and down, one item per press;
3. `SELECT` opened a mode; `MENU` returned, checkpointing silently on the way;
4. 9 presses → 9 frames → 9 accepted → 9 applied, with zero duplicates, drops,
   bounces, suppressed repeats, or unknown actions;
5. the three presses made inside the editor were ignored by the document —
   `shell_buttons_ignored: 3`, no editor event, character count unmoved;
6. the typed line survived leaving and reopening the editor exactly.

Neither board was remounted, both CIRCUITPY volumes were host-writable after the
run, and **no guard file was created**.

What it fixed — two defects, both in the shell and neither in the editor,
storage, or transport.

1. **The Save/Status interruption is removed.** Escape from the editor
   checkpointed the document *and* then drew a screen the writer had no decision
   to make about, with the menu visible underneath it and a second Enter needed
   to reach it. The checkpoint is unchanged and still unconditional; it now runs
   silently inside the gesture and *before* the transition, so a save that
   actually failed reaches the error screen and everything else goes straight to
   the menu. A missing card is not a failure — it is the degraded mode the
   indicator has shown since V1.2. The save state itself is preserved as the
   one-character indicator in the status field of every ordinary frame.
2. **The four MagTag buttons are the primary shell controls**, over the existing
   return UART as `BUTTON_EVENT`: menu, up, down, select. The MagTag sends
   normalized actions only; the Fruit Jam stays the sole owner of shell and
   document state. Debounce is stability on both edges rather than a press
   lockout, and duplicates are suppressed three times over — at the contact, at
   the frame sequence, and at a monotonic press ordinal. No button reaches the
   document, and the menu button cannot end a session.

The keyboard keeps every shell key as a fallback, persistence formats are
untouched, keyboard mappings were not revisited, and no certification framework
was created.

Both boards needed the **reset button**, exactly as the deployment note
predicted, and the MagTag went first.

**V1.4 — Journal, Quick Note, Drafts, and Recent — PHYSICALLY VERIFIED
2026-07-30.** Evidence: `docs/FRUITJAM_V14_BENCH_SERIAL.jsonl`,
`docs/MAGTAG_V14_BENCH_SERIAL.jsonl`, and the pre-migration
`docs/V14_PREFLIGHT_DOCUMENT_BACKUP.md`; the full account is in `ROADMAP.md`.

A deliberately minimal run, scoped to the smallest set of checks that confirms
V1.4 works on hardware. All six passed with **zero faults** and no capacity
refusal of any kind — the four that V1.3 hit in ordinary prose did not recur:

1. the recovered document opened intact — revision 127, 125 chars, 32 lines;
2. Quick Note produced a new empty document, `n0001` / `NOTE 1`, `kind: NOTE`;
3. switching between the two lost nothing — 259 and 68 characters, both exact;
4. a clean restart restored the right document **and its mode**, `QUICK_NOTE`;
5. 134 characters onto one logical line, where V1.3 refused past 96;
6. 41 lines, where V1.3 refused past 32.

Every switch checkpointed the outgoing document to `SAVED` before binding the
incoming one, and migration cost exactly one catalogue append.

**Three exit criteria in `docs/MODES.md` were deliberately not run and are not
claimed:** Journal, Recent as a menu item, and a forced power loss.

**V1.3 — MagWrite Shell — PHYSICALLY VERIFIED 2026-07-30.** Evidence:
`docs/FRUITJAM_V13_SHELL_SERIAL.jsonl` and
`docs/MAGTAG_V13_SHELL_SERIAL.jsonl`; the full account is in `ROADMAP.md`. All
twelve exit criteria met across three bench sessions, including a real cable pull
that recovered from the journal into the editor, and four bounded failures that
each reached the recoverable error state with the document intact. See
`docs/SHELL.md` for the design and `ROADMAP.md` for the requirement map.

The shell owns application state and nothing else, and there is exactly one
`MultilineEditor` for the life of the session — which is why no transition can
lose unsaved work: nothing is ever closed. `ENABLE_SHELL = False` reproduces the
V1.2 behaviour, and every viewport payload the physical runs measured, exactly.

**V1.2 — Single-document persistence and recovery — PHYSICALLY VERIFIED
2026-07-30.** Evidence: `docs/FRUITJAM_SD_PROBE.jsonl` and
`docs/FRUITJAM_V12_PERSISTENCE_SERIAL.jsonl`; the full account is in `ROADMAP.md`.
The acknowledged revision is the latest revision accepted by the **Fruit Jam
editor**, not the MagTag display: display acknowledgements govern pacing, editor
acceptance governs durability.

## Deferred backlog

The following are explicitly non-blocking unless they prevent normal writing:

- the stale test count in `host-tests/README.md`, corrected again in V1.5 and
  still worth a standing check;
- **`ButtonPad` press ordinals are not reset between MagTag sessions.** Harmless
  as built — a fresh Fruit Jam inbox starts at zero, so a continuing ordinal is
  always accepted — but it is a property that holds by coincidence of restart
  ordering rather than by design, and a future MagTag that outlives two Fruit Jam
  sessions without restarting would depend on it. Recorded rather than changed
  mid-phase;
- **the microSD is exposed to the USB host as a third mass storage volume.**
  CircuitPython 10.2.1 auto-mounts the card at `/sd` before user code runs and
  publishes it alongside CIRCUITPY and CPSAVES. The shipped `sd_storage.mount()`
  adopts the existing mount and needs no change, but two consequences are worth a
  deliberate decision in a later phase: the host's cached view of the card goes
  stale while the board writes it, so every non-empty file reads as corrupt from
  Windows mid-session; and the host holds the writer's only copy read-write,
  which is a second writer on it. A `boot.py` that keeps the card off the USB bus
  is the obvious answer. Found in the V1.4 physical run;
- **the per-append SPI cost of an 8 KB journal record has still not been
  measured.** A snapshot is the whole document, so raising the bound eightfold
  raised what one autosave writes by the same factor. Nothing in the V1.4 bench
  run felt slow, and that is an impression rather than a measurement, so this
  stays open;
- **dated journal entries are not delivered.** The prototype has no RTC and no
  network, so entries are numbered. `PRODUCT.md` asks for dating; the alternative
  was a date derived from `time.monotonic`, which is a fabricated date printed
  next to a writer's own words. `library._journal_title` is the one function that
  changes when a time source exists;
- **no way to delete or rename a document from the device.** The catalogue is
  bounded at 64 and refuses creation past it, cleanly and by name. Renaming and
  archiving are V1.5 scope, and the append-only record format already supports
  both as a single append;
- ~~the MagTag holds parser state after an *interrupted* Fruit Jam session and
  refuses the next handshake with `duplicate or reversed input sequence`, which
  the Fruit Jam reports as `status_hello timeout`.~~ **Fixed 2026-07-30**, after
  three occurrences, because one-cable power made the documented workaround
  — restart the MagTag first — physically impossible to perform. The MagTag lets
  a handshake re-baseline its input numbering while it has displayed nothing, and
  the Fruit Jam retries rather than failing. It was recorded here as transport
  hardening and it was; it stopped being deferrable when the hardware stopped
  allowing the workaround;
- `FakeKeyboardBackend.typing_interval_seconds` in the host simulator delivers a
  report every *two* intervals, not one: the interval gate is evaluated before
  the per-poll gate and consumes a slot even on the polls where the per-poll gate
  suppresses the report. Found in V1.3 while a 0.25 s script produced a key
  repeat; the product code is correct, a key held 500 ms is meant to repeat. It
  means every test that passes that option is pacing at half the rate it reads
  as. Fixing it would perturb the timing of several proven tests, so it is
  recorded rather than changed mid-phase;
- character mis-mappings on the EPOMAKER TH40, seen in the V1.2 physical run
  (`this` typed as `tgus`, `is` as `us`) and again in V1.5, where `v15` reached
  the editor as `v 12`. Persistence stored and recovered exactly what the editor
  accepted, and the shell passed it through untouched, so this is a
  keyboard-mapping question rather than a storage or shell one. The dongle phase
  is where a second keyboard will say whether it is this keyboard or our HID
  handling;
- apostrophe and unusual keyboard mappings;
- Home, End, Delete, Caps Lock, and key-repeat refinement;
- formal responsiveness measurement;
- additional certification harnesses;
- display longevity testing;
- battery and enclosure work.

## Decision test

Before starting any unplanned task, answer:

> Does this prevent completion of the active roadmap phase?

If no, record it and continue with the active phase.
