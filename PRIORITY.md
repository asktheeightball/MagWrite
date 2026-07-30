# MagWrite Current Priority

This file is the operational companion to `ROADMAP.md`.

## Execution rule

Only stop the current roadmap step for a defect that blocks that step.

Everything else must be recorded for later and must not interrupt delivery.

Do not create new certification harnesses, evidence packages, compatibility investigations, keyboard-polish tasks, or unrelated refactors unless they are required to complete the active roadmap phase.

## Current path

1. Finish the current ordinary writing session.
2. Move directly to V1.2: microSD persistence.
3. Add crash-safe autosave and forced-power-loss recovery.
4. Build the MagWrite Shell.
5. Add Journal, Quick Note, Drafts, and Recent.
6. Complete the minimum standalone workflow.
7. Defer optional buttons, keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**V1.2 — Single-document persistence and recovery**

The next implementation work should prove one reliable document before adding a document browser or additional writing modes:

- microSD-backed plain-text or Markdown storage;
- create or open the latest draft;
- crash-safe autosave;
- append-only recovery journal;
- atomic or recoverable checkpoints;
- tolerance for a truncated final recovery record;
- manual save and visible save state;
- recovery of the last acknowledged edit after forced power loss.

## Deferred backlog

The following are explicitly non-blocking unless they prevent normal writing:

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
