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
7. Run one physical two-mode session on the bench. **<- next**
8. Complete the minimum standalone workflow.
9. Defer optional buttons, keyboard edge cases, battery, enclosure, and hardening until their roadmap phase.

## Active product task

**V1.4 — Journal, Quick Note, Drafts, and Recent — IMPLEMENTED AND
HOST-VERIFIED. Physical run not yet performed.**

See `docs/MODES.md` for the design and `ROADMAP.md` for the full account. 1,056
host tests pass, up from 929.

Two changes ship together, in this order:

- **the document bound was raised first**, from 512 characters over 32 lines of
  96 to 8192 over 512 lines of 1024. The binding bound was `MAX_LINE_CHARS`: the
  editor word-wraps, so a paragraph is one logical line, and 96 characters is
  about a sentence and a half. That is what the four `document line capacity
  reached` faults in the V1.3 bench session actually were. No architectural
  change was needed — the journal record bound is now derived from the character
  bound, and what crosses the UART is a five-row window either way;
- **the four modes**, each a choice of document and nothing else, over an
  append-only catalogue that persists identity, kind, title, and a monotonic open
  ordinal. The highest ordinal *is* the active document, so no second pointer
  file exists to disagree with the catalogue after a power cut.

Both things V1.3 handed forward are closed:

- the shell's mode seam carried the per-mode policy, as predicted;
- **a restored session now restores its mode**, by the route V1.3 named as most
  likely: the mode became a property of the document. It needed no extra
  persisted state, because the catalogue already had to exist for Drafts and
  Recent.

A card written by V1.2 or V1.3 is migrated by appending one catalogue record.
Nothing the writer owns is moved, renamed, or rewritten, and a host test asserts
every pre-existing file is byte-identical afterwards.

**Next: the physical two-mode session.** The nine bench criteria are at the end
of `docs/MODES.md`. Restart the MagTag first.

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
- **the per-append SPI cost of an 8 KB journal record has not been measured.** A
  snapshot is the whole document, so raising the bound eightfold raised what one
  autosave writes by the same factor. It is bounded and it is a few megabytes
  across a long session, which is nothing to a 946 MB card, but whether a
  ~4 KB append plus `os.sync()` is perceptible between keystrokes is a question
  only the bench can answer. Recorded for the V1.4 physical run;
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
