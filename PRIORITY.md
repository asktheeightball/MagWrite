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
5. Run one physical shell session on the bench. **<- next**
6. Add Journal, Quick Note, Drafts, and Recent.
7. Complete the minimum standalone workflow.
8. Defer optional buttons, keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**V1.3 — MagWrite Shell — IMPLEMENTED, HOST-VERIFIED**

Every requirement is built and covered by the host suite. See `docs/SHELL.md`
for the design and `ROADMAP.md` for the requirement map.

Four states — Main Menu, Editor, Save/Status, Error — plus the terminal Exit the
session reads to stop. The main menu exposes Journal, Quick Note, Drafts, and
Recent; for this phase all four route into the one proven document, which is the
scope the phase was given.

The shell owns application state and nothing else. It holds no editor, no
document, no store, no clock, and no transport, and there is exactly one
`MultilineEditor` for the life of the session — which is why no transition can
lose unsaved work: nothing is ever closed. Every exit from the editor passes
through Save/Status, which forces a checkpoint on the way out.

Navigation adds no keymap entry. Up, Down, and Enter are already normalized
editor events; the finish gesture already existed with physical evidence behind
it, and under the shell it means **back**, with the root still being the clean
stop. Ctrl-S is unchanged.

`ENABLE_SHELL = False` reproduces the V1.2 behaviour, and every viewport payload
the physical runs measured, exactly.

**Next: one physical bench session.** Not a new certification harness — the
development runtime brings the shell up and logs every transition. What it has to
show is the exit criterion: moving between the shell and a document repeatedly
without losing state or stalling the display, and a restart landing back in the
editor on the recovered document.

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
