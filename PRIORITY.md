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
6. Add Journal, Quick Note, Drafts, and Recent. **<- next**
7. Complete the minimum standalone workflow.
8. Defer optional buttons, keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**V1.4 — Journal, Quick Note, Drafts, and Recent — NOT STARTED**

The four writing modes, built on the shell and on persistence. `ROADMAP.md`
carries the requirements. Two things V1.3 handed forward, both recorded there in
full:

- the shell already carries and draws the mode, and that is the seam V1.4
  attaches per-mode policy to. Nothing new is needed to know which item was
  chosen;
- **a restored session does not restore its mode.** Only the state is derived
  from recovery, deliberately. V1.4 has to decide what a restored mode means —
  most likely by making the mode a property of the recovered document, which is
  where it belongs — and that decision cannot be deferred past this phase,
  because it is the first phase in which the mode does anything.

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

- the stale test count in `host-tests/README.md`, corrected again in V1.3 and
  still worth a standing check;
- the MagTag holds parser state after an *interrupted* Fruit Jam session and
  refuses the next handshake with `duplicate or reversed input sequence`, which
  the Fruit Jam reports as `status_hello timeout`. Restarting the MagTag first
  clears it, and `docs/DEVELOPMENT_RUNTIME.md` now says so. Cost two false starts
  in the V1.3 bench run. A session that ends abnormally arguably ought to be
  recoverable without an operator knowing this, but that is transport hardening,
  not a shell defect;
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
