# MagWrite Current Priority

This file is the operational companion to `ROADMAP.md`.

## Execution rule

Only stop the current roadmap step for a defect that blocks that step.

Everything else must be recorded for later and must not interrupt delivery.

Do not create new certification harnesses, evidence packages, compatibility investigations, keyboard-polish tasks, or unrelated refactors unless they are required to complete the active roadmap phase.

## Current path

1. ~~Finish the current ordinary writing session.~~ Done.
2. ~~Move directly to V1.2: microSD persistence.~~ Implemented, host-verified.
3. Confirm the microSD pin aliases and run one physical forced-power-loss test.
4. Build the MagWrite Shell.
5. Add Journal, Quick Note, Drafts, and Recent.
6. Complete the minimum standalone workflow.
7. Defer optional buttons, keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**V1.2 — Single-document persistence and recovery — implemented, host-verified**

Every requirement is built and covered by the host suite. See
`docs/PERSISTENCE.md` for the design and `ROADMAP.md` for the requirement map.

The acknowledged revision is the latest revision accepted by the **Fruit Jam
editor**, not the MagTag display. Display acknowledgements govern pacing; editor
acceptance governs durability.

Hardware bring-up ran on 2026-07-30. The pin aliases are now **read off the
board** and set in `config.py`: the card is on the dedicated SPI bus
(`SD_SCK`/`SD_MOSI`/`SD_MISO`/`SD_CS`), not the shared `board.SPI()`. The
shipped mount path was exercised on real hardware and reported correctly.

**One item blocks the V1.2 exit, and it is not a software defect:**

- the microSD card currently in the Fruit Jam **carries no usable filesystem**.
  946 MB, reads reliably, valid MBR signature, but its single partition entry is
  FAT16 claiming more sectors than the card has, and no FAT volume boot record
  exists at that offset or twelve others. `storage.mount` fails with `ENODEV`,
  correctly, and the runtime reports `UNMOUNTABLE`.

Until a card with a FAT filesystem is in the slot there is no autosave to
observe, no Ctrl-S to confirm, and no forced-power-loss recovery to perform.
Reformatting destroys whatever the card holds, so it awaits an explicit
decision.

This is not a new certification harness. The development runtime already brings
persistence up and logs the mount status, the recovery, and the save state.

## Deferred backlog

The following are explicitly non-blocking unless they prevent normal writing:

- the stale test count in `host-tests/README.md`, corrected in V1.2 but worth a
  standing check;
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
