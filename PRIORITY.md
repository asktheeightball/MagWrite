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
4. Build the MagWrite Shell. **<- next**
5. Add Journal, Quick Note, Drafts, and Recent.
6. Complete the minimum standalone workflow.
7. Defer optional buttons, keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**V1.2 — Single-document persistence and recovery — PHYSICALLY VERIFIED**

Every requirement is built and covered by the host suite. See
`docs/PERSISTENCE.md` for the design and `ROADMAP.md` for the requirement map.

The acknowledged revision is the latest revision accepted by the **Fruit Jam
editor**, not the MagTag display. Display acknowledgements govern pacing; editor
acceptance governs durability.

Hardware bring-up and physical verification ran on 2026-07-30. Evidence:
`docs/FRUITJAM_SD_PROBE.jsonl` and `docs/FRUITJAM_V12_PERSISTENCE_SERIAL.jsonl`.

The pin aliases are read off the board: the card is on the dedicated SPI bus
(`SD_SCK`/`SD_MOSI`/`SD_MISO`/`SD_CS`), not the shared `board.SPI()`. The card
found in the slot had no usable filesystem and was reformatted with explicit
authorisation; FatFs chose FAT16 for a 946 MB volume, which V1.2 does not care
about.

**Exit met.** A writing session produced 12 autosaves and 3 checkpoints, Ctrl-S
manual save worked and inserted no character, the save indicator moved
`u` -> `r` -> `s`, and after the USB cable was pulled mid-session the restart
recovered revision 73, 71 characters, cursor (2, 8) — exactly the last
acknowledged edit, checked against the console's own per-keystroke record.

One defect was found and fixed during the run: a mount survives a soft reboot, so
every restart after the first raised `SD_SCK in use` and reported `NO_CARD` while
a good card was mounted. `sd_storage.already_mounted` now adopts the existing
mount.

Recorded, not chased: the recovered text shows consistent character
mis-mappings (`this` -> `tgus`). That is the deferred keyboard-mapping backlog;
whatever the editor accepted was journaled and recovered faithfully.

Next: V1.3, the MagWrite Shell.

This is not a new certification harness. The development runtime already brings
persistence up and logs the mount status, the recovery, and the save state.

## Deferred backlog

The following are explicitly non-blocking unless they prevent normal writing:

- the stale test count in `host-tests/README.md`, corrected in V1.2 but worth a
  standing check;
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
