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
8. Integrate USB dongle keyboard compatibility. **<- next**
9. Bring the bench to one-cable power.
10. Complete the minimum standalone workflow.
11. Defer optional buttons, keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**USB dongle keyboard compatibility — NOT STARTED.**

The wired EPOMAKER TH40 is proven on the USB host port across four physical
milestones. The next keyboard question is a wireless keyboard with a USB
receiver, which `README.md` has named as a supported input path since the
beginning and which nothing has yet tested.

Then, in order: **one-cable bench power**, and then **V1.5, the minimum
standalone workflow**.

Carry these into the dongle work, from the V1.4 run:

- the TH40 character mis-mappings (`this` → `tgus`, `is` → `us`) are still
  unexplained and still in the backlog. A second keyboard is the cheapest
  experiment that separates "this keyboard" from "our HID handling", so the
  dongle phase is the natural place to learn something about it — without
  turning into the keyboard-mapping investigation the backlog defers;
- `usb_keyboard_layout_selected` already carries an `AUTO` path keyed on vendor
  and product id, so an unrecognised receiver gets standard HID rather than a
  wrong layout. That seam is where a dongle's descriptor will land.

## Completed product task

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

- the stale test count in `host-tests/README.md`, corrected again in V1.4 and
  still worth a standing check;
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
- the MagTag holds parser state after an *interrupted* Fruit Jam session and
  refuses the next handshake with `duplicate or reversed input sequence`, which
  the Fruit Jam reports as `status_hello timeout`. Restarting the MagTag first
  clears it, and `docs/DEVELOPMENT_RUNTIME.md` now says so. Cost two false starts
  in the V1.3 bench run and **recurred once in the V1.4 run**, from restarting the
  Fruit Jam by autoreload without restarting the MagTag first. Three occurrences
  now. A session that ends abnormally arguably ought to be recoverable without an
  operator knowing this, but that is transport hardening, not a shell defect;
- `FakeKeyboardBackend.typing_interval_seconds` in the host simulator delivers a
  report every *two* intervals, not one: the interval gate is evaluated before
  the per-poll gate and consumes a slot even on the polls where the per-poll gate
  suppresses the report. Found in V1.3 while a 0.25 s script produced a key
  repeat; the product code is correct, a key held 500 ms is meant to repeat. It
  means every test that passes that option is pacing at half the rate it reads
  as. Fixing it would perturb the timing of several proven tests, so it is
  recorded rather than changed mid-phase;
- character mis-mappings seen in the V1.2 physical run (`this` typed as `tgus`,
  `is` as `us`) on the EPOMAKER TH40. Persistence stored and recovered exactly
  what the editor accepted, so this is a keyboard-mapping question, not a
  storage one;
- apostrophe and unusual keyboard mappings;
- Home, End, Delete, Caps Lock, and key-repeat refinement;
- formal responsiveness measurement;
- MagTag button controls;
- additional certification harnesses;
- display longevity testing;
- battery and enclosure work.

## Decision test

Before starting any unplanned task, answer:

> Does this prevent completion of the active roadmap phase?

If no, record it and continue with the active phase.
