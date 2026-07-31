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
11. ~~Bring the bench to one-cable power.~~ **PHYSICALLY VERIFIED 2026-07-30.**
    One USB-C cable into the Fruit Jam, the MagTag on a Fruit Jam USB-A host
    port, and the complete device starts by itself.
12. ~~Complete the minimum standalone workflow.~~ **PHYSICALLY VERIFIED
    2026-07-30.** The device is a standalone writing machine: one cable, both
    boards start by themselves, the document comes back, and it neither loses a
    late keyboard nor switches itself off.
13. ~~Draw the MagTag UI in the built-in font and label the four buttons on the
    panel — V1.7.~~ **PHYSICALLY VERIFIED 2026-07-31.**
14. Integrate one rechargeable battery and one charging port — V1.8. **<- current.**
15. Defer keyboard edge cases, enclosure, and hardening until their roadmap phase.

## Active product task

**V1.8, battery and charging.** See `ROADMAP.md` Priority 6. The USB power meter
that phase needs is what finally answers the current question left open by the
bench power audit, and no figure from this bench may be assumed until one is
measured. The V1.7 UI milestone that was blocking it is verified, below.

## Previous product task

**V1.7, the MagTag font and button footer — PHYSICALLY VERIFIED 2026-07-31.**
Evidence `docs/FRUITJAM_V17_UI_SERIAL.jsonl`; the check is
`docs/PANEL_UI_CHECK.md` and the full account is in `ROADMAP.md`.

**The final configuration is `terminalio.FONT`, native scale 1, a 6×12 cell, 48
columns by 6 content rows.**

All seven check items passed and the standalone cold boot recovered the
document. The operator confirmed the four things only a person can confirm — the
text is comfortable at normal writing distance, the editor and menus fit the
48×6 layout cleanly, `MENU`/▲/▼/`SELECT` sit over A/B/C/D, and the arrows read
clearly without overlapping content. The panel's left-to-right order **is** the
bezel's, so `button_footer.FOOTER_ACTIONS` needed no change.

The first pass ran with the upstream cable in the PC rather than the charger, so
unlike V1.6 the mechanical half has a record: 4 button presses and 4 applied with
zero duplicates, drops, or unknown actions, all four actions exercised including
`MENU` at the main menu doing nothing; 46 HID reports → 23 events → 23 applied
with none lost; the document grown 30 → 53 characters across 3 checkpoints and 4
journal appends; a silent `CHECKPOINTED` / `SAVED` straight to the menu; 8
viewports all displayed and hash-reconciled; and no fault of any kind.

**The wider panel cost no refresh time** — 898 ms mean over seven partial
refreshes against V1.6's 924 ms over 24, on roughly double the text.

**The check found one blocker, and it was not in the UI.** The Fruit Jam was not
running at all: `dev_runtime.py` re-asserts the protocol constants as a literal
and still demanded the old 192-byte payload maximum, so it raised and dropped to
the REPL in nine seconds while the MagTag correctly waited for a board that would
never speak. Every host check had passed and none could reach it — the file
imports `board`. Fixed with the static assertion that closes the gap, then
re-checked in the same session.

Printable ASCII support caused no visible rendering or editor defect and was
accepted without a separate investigation, as instructed.

**Two consequences worth carrying forward:** the guarded harnesses
`hardware_editor_test.py` and `hardware_usb_keyboard_test.py` are pinned at the
192-byte wire format they were verified against and will now refuse to start —
deliberately, and asserted by a test, but they cannot be re-run without a
decision about what they would be proving. And the frozen 3×5 glyph table in
`magtag/magwrite/test_pattern.py` is still deployed and still used by those
harnesses.

Two changes, both to what the writer looks at and neither to what the device
does.

1. **The panel draws with CircuitPython's built-in `terminalio.FONT`**, at native
   scale 1, everywhere: editor text, menus, titles, the startup and waiting
   screens, status, error text, and the footer. It replaces a 3×5 bitmap table
   maintained by hand, in which every apostrophe and the whole lowercase alphabet
   had been an act of type design and a character with no entry raised `KeyError`
   on the first frame that carried it. The panel's alphabet is now printable
   ASCII rather than an explicit subset, so the punctuation a writer types is
   drawn instead of being replaced with a space.
2. **A persistent footer above the four bezel buttons** — `MENU`, an up arrow, a
   down arrow, `SELECT` — on every screen. The mapping and every button's
   behaviour are unchanged; the panel now says what they are. The arrows are
   filled triangles from display primitives, because `^` and `v` are a caret and
   a letter.

**The layout is derived, not declared.** `viewport_renderer.geometry()` asks the
font for its own bounding box and computes the row pitch, row count, and column
count from it — so the five-row layout was not preserved and was not replaced by
another arbitrary number. With the 6×12 built-in font the panel comes out at
**48 columns by 6 rows**, against 28 by 5, which is roughly double the visible
text at the same apparent size: the built-in font's 6 px advance is exactly what
the old table drew at scale 2.

That capacity is the one number the two boards must agree on and they share no
import, so a host test asserts the Fruit Jam's `editor_layout` constants, the
viewport message bounds, and the shell screen bounds all against the MagTag's
derivation. Six rows of 48 is a 340-byte worst-case viewport, which raised the
protocol payload maximum from 192 to 384 bytes and the parser accumulator from
512 to 1024. Widening a bound accepts every frame the narrower one did, so
nothing already proven on the wire is invalidated.

**Host-verified, 1,226 tests, 41 of them new.** `compileall`, the UART
validator, the CircuitPython compatibility sweep, and `git diff --check` all
pass. Physical verification is the outstanding step and nothing here is claimed
without it — in particular whether scale 1 is comfortable to read at arm's
length, and whether the panel's left-to-right order is the bezel's. The second is
one line, `button_footer.FOOTER_ACTIONS`, if it is wrong.

**Deliberately not done:** the hand-drawn 3×5 table is kept rather than deleted.
The one-shot hardware harnesses that produced this project's physical evidence
draw with it, and re-rendering a proven harness would change what those runs
measured. Nothing the writer sees comes from it any more.

## Previous product task

**V1.6, the minimum standalone workflow — PHYSICALLY VERIFIED 2026-07-30.** The
design is `docs/STANDALONE.md`, the check is `docs/STANDALONE_CHECK.md`, and the
account is in `ROADMAP.md`.

**All steps passed with no faults observed.** One USB-C cable into a charger,
neither board on the PC: both started automatically with no reset and no start
order, the panel showed startup progress and reached the recovered document, the
previous document and mode came back, the buttons opened the menu and selected a
document, a paragraph typed, Escape saved silently and returned straight to the
menu, the reopened text was intact, a power cycle recovered the same document,
**a keyboard connected after startup became usable without a reboot**, and **the
device left idle past the removed 1800 s bound did not shut itself down**. The
last two are the defects the phase existed to fix.

Both boards were still carrying V1.5 and still hand-armed for their development
runtimes; each was deployed to V1.6 and verified file-by-file — 42 and 40 `.py`
files, zero hash mismatches — with the arming cleared to the shipped defaults.

**This result has no evidence file and cannot have one.** The check removes both
consoles by design, so the panel is the only instrument and the operator's
observation is the only record. Nothing measured a timing, a refresh count, or a
character total, and nothing claims one. Every phase from V1.2 to V1.5 carries a
`.jsonl` capture; this one deliberately does not.

**The shipped configuration is now the writing appliance.** Both boards start
into the product path with no flag set, no console attached, no volume mounted on
a PC, and no start order. `fruitjam/code.py` and `magtag/code.py` fall through to
it after every armed harness, so arming a harness is still how a board is put on
the bench, and every harness still ships disabled and still needs its own mode
string. The MagTag's `ENABLE_PHYSICAL_DISPLAY` is now `True`, which is the one
default that looks like a weakening and is not: the compatibility gate is
unchanged and still checked first, and `MAGTAG_STANDALONE` is deliberately absent
from the boot remount tuple, so no filesystem is taken from the host.

**Five things that would have made the device not work, found by asking what
happens with nobody watching:**

1. **A board switched on before its keyboard was plugged in never saw that
   keyboard.** The connection state machine allowed thirty open attempts at one
   per second and then latched `ERROR` permanently. Thirty seconds is not a
   deadline anybody agreed to, and the cure was a reset the writer has no reason
   to know about. The attempt *count* is removed for the standalone profile; the
   one-per-second rate bound is untouched, so this is not the unbounded reconnect
   loop the harnesses refuse.
2. **The idle bound ended the session after half an hour of a writer thinking**,
   and the session ending left a panel nothing but the reset button could move.
   **This one is recorded on hardware, not argued from the code**: the one-cable
   evidence file `docs/BENCH_ONECABLE_FRUITJAM_SERIAL.jsonl` gained three lines
   after that check was written up, and they are the verified device switching
   itself off while left alone — `result: ERROR`, `stop_reason: live session idle
   timeout`, with the document `SAVED` and all 107 characters intact. Nothing was
   lost except the device. Both run-length bounds, the keyboard event bound, and
   both frame bounds are removed for the appliance. Every bound that protects
   *memory* is unchanged.
3. **Escape at the main menu switched the device off** — drained, drew `STOPPED`,
   and stopped. One keystroke that ends the device and no keystroke that starts
   it. The MagTag's menu button has never been able to do this, deliberately;
   the keyboard now agrees with the bezel. Power is the stop.
4. **A stored document the editor refused took the whole runtime down during
   construction**, leaving a blank panel and one line on a console nobody was
   connected to. Worse, had it not, the empty editor left behind would have been
   checkpointed over the writer's real document by the next threshold. Writes are
   now *held* for the session, the card is not touched, and the writer lands on
   the recoverable error screen with a way back to the menu.
5. **Typing into a device that was still booting ended the session.** Keystrokes
   are polled during the display wait but not drained, so a fast writer filled
   the 64-event queue and overflowed it. The overflow is now dropped and counted
   rather than fatal; what was already queued is still applied.

**The panel now says what is happening.** The MagTag draws two screens of its own
before the link is up — `STARTING`, and `WAITING FOR THE WRITER BOARD` after 15 s,
which is above the 9.05 s a measured cold boot took, so an ordinary start never
draws the second one. Those are the only things it ever draws that the Fruit Jam
did not send, they carry no state the Fruit Jam owns, and they are never drawn
again once a viewport arrives. A construction failure it *can* draw — a bad UART
pin — now reaches the panel too, which is why the display is constructed before
the UART. The Fruit Jam adds `NO KEYBOARD - PLUG ONE IN` on the spare menu row
and a `k` in the status field of every frame.

**Settled on hardware 2026-07-30.** 1,185 host tests pass, 49 of them new and
written for exactly the five failures above, and `docs/STANDALONE_CHECK.md` has
now been run on the physical device: every step passed with no faults observed.
Failures 1 and 2 — the late keyboard and the idle shutdown — were confirmed fixed
on the bench rather than only in the suite.

**Not delivered, and named rather than hidden:** rename and archive, dated
journal entries, and sleep/wake/shutdown. The roadmap's V1.6 list included the
first two; they are storage and clock questions rather than standalone ones, and
neither blocks a writer using the device from one cable. There is no sleep state
and no shutdown sequence at all — the device is on while it has power, and every
editor exit checkpoints, so removing power is safe at any moment. Power
management belongs to the battery phase, where there is something to manage.

## Previous product task

**One-cable bench power — PHYSICALLY VERIFIED 2026-07-30.** Evidence
`docs/BENCH_ONECABLE_FRUITJAM_SERIAL.jsonl`; the check is
`docs/BENCH_POWER_CHECK.md`, the audit is `docs/BENCH_POWER.md`, and the account
is in `ROADMAP.md`. Superseded as the active task by V1.6 above; the full account
is retained below.

### One-cable bench power, in full

**One USB-C cable was connected and the complete device started by itself,
twice**, with no reset and no start order. Both cold boots: four handshake
attempts, a 9.05 s wait, the document recovered, the keyboard claimed, a full
refresh completed. The second boot recovered exactly the 107 characters a MagTag
button had checkpointed before power was pulled. 26 viewports all displayed, 24
partial refreshes averaging 924 ms, 23 button presses all applied, and zero
faults of any kind. Nothing warm to the touch; panel clean. No current was
measured — there is still no meter on the bench.

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

## The active phase in detail

**V1.8 — one rechargeable battery and one charging port.** Unblocked
2026-07-31, when the V1.7 UI milestone it was paused behind was physically
verified. `ROADMAP.md` Priority 6 carries the requirements: one protected single cell, one charger with
power-path/load-sharing, one system power switch, regulated supply for both
boards, no parallel charger circuits, brownout margin, and **measured** peak,
active, idle, and refresh current.

That last item is the standing debt. **A USB power meter on the upstream cable is
the one purchase that unblocks this phase**, and no current figure has ever been
taken on this bench — the one-cable phase closed without one and said so. Nothing
about the battery design can be sized honestly until it exists.

The device is a usable standalone writing machine as of V1.6, so V1.8 is about
making it portable rather than making it work.

The dongle phase stays blocked on hardware that is not here. The hope that power
might change its result was narrowed by the audit — the receiver's supply comes
from the Fruit Jam's own host port, not from upstream — so it is worth re-asking
if an ordinary wireless keyboard ever arrives, and not worth expecting.

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

- the stale test count in `host-tests/README.md`, corrected again in V1.6 and
  still worth a standing check;
- **a session-ending fault leaves a stale panel until power is removed.** V1.6
  took away every bound that could end a standalone session on its own, but a
  genuine `LiveSessionError` — a transport integrity failure, say — still ends the
  loop, and the Fruit Jam then sits in `code.py`'s sleep with whatever was last
  drawn still on the panel. The recovery is a power cycle, which is the gesture
  the device already asks for, and the writer loses at most the couple of seconds
  since the last journal append. Making the Fruit Jam force one final error
  viewport before it stops is the obvious answer and is new behaviour on the path
  a physical run has not yet exercised, so it is recorded rather than added in the
  same phase. The MagTag has no watchdog for a writer board that stops talking,
  for the same reason;
- **the standalone runtime logs the keyboard retry once a second forever when no
  keyboard is attached.** Harmless on a device with no console — the bytes go
  nowhere — and bounded in rate, but it is output produced for nobody. Worth a
  quieter cadence if a later phase touches that path;
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
  bounded at 64 and refuses creation past it, cleanly and by name. The
  append-only record format already supports both as a single append. Named in
  the roadmap's V1.6 list and deliberately not delivered there: it is a storage
  feature rather than a standalone one, and nothing about writing from one cable
  needs it;
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
