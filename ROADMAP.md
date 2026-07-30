# MagWrite Roadmap

## Current product direction

MagWrite is now a two-board prototype:

```text
USB HID keyboard
        |
        v
Adafruit Fruit Jam
- authoritative editor
- viewport generation
- microSD persistence
        |
        | bidirectional UART
        v
Original Adafruit MagTag
- partial-refresh e-paper terminal
- four-button control surface
```

The Fruit Jam remains authoritative for document, cursor, viewport, storage, and workflow state. The MagTag renders supplied viewports, reports physical display status, and sends normalized button events back to the Fruit Jam.

Direct USB HID keyboard input on the Fruit Jam is the preferred keyboard path. The LOLIN32 Bluetooth bridge is deferred and should be revisited only if the intended keyboard is Bluetooth-only and cannot use a USB receiver or wired USB mode.

## V1 delivery order

This is the authoritative order for V1. The older `Priority N` headings below
are kept because the evidence documents reference them; where the two disagree,
this list wins.

| V1 | Phase | Section below | State |
| --- | --- | --- | --- |
| 1 | Responsiveness and keyboard completeness | V1.1 | Host-verified; one physical attempt FAILED, certification retired |
| 2 | microSD persistence and forced-power-loss recovery | Priority 4 | PHYSICALLY VERIFIED 2026-07-30 |
| 3 | MagWrite Shell | V1.3 | PHYSICALLY VERIFIED 2026-07-30 |
| 4 | Journal, Quick Note, Drafts, and Recent | V1.4 | PHYSICALLY VERIFIED 2026-07-30 |
| 5 | Shell UX: one-gesture exit, and MagTag buttons | V1.5 | PHYSICALLY VERIFIED 2026-07-30 |
| 6 | One-cable bench power | One-cable bench power | PHYSICALLY VERIFIED 2026-07-30 |
| 7 | Minimum standalone workflow | V1.6 | PHYSICALLY VERIFIED 2026-07-30 |
| 8 | MagTag font and button footer | V1.7 | Host-verified; physical check outstanding |
| 9 | Battery, enclosure, and hardening | Priorities 6 and 7 | Not started |

Writing must feel right before anything is stored, and storage must be
trustworthy before a shell is built on top of it.

**MagTag buttons moved back up, and stopped being optional.** They were deferred
to position 6 and marked a convenience on the reasoning that the USB keyboard
already provides every control the writing loop needs. That reasoning was about
the *loop* and it was correct about the loop; it was wrong about the product. A
writing appliance whose menu can only be answered from the keyboard is a device
with two control surfaces and no thumb affordance, and the V1.4 bench run made
that plain: every mode switch meant taking a hand off the keys to press Escape,
then Enter, then Enter. The buttons are not a convenience on top of the shell;
they are how the shell is meant to be used, which is why they land in the same
phase as the shell's UX correction rather than after it.

## Completed feasibility gates

### P0.1 MagTag identity and compatibility — COMPLETE

- Original 2.9-inch MagTag identified from the `WFT0290CZ10 LW` display-flex marking.
- UC8151D/T5-family compatibility decision: `COMPATIBLE`.
- CircuitPython and hardware evidence recorded in `docs/HARDWARE_IDENTITY_REPORT.md`.

### P0.2 Partial-refresh characterization — COMPLETE THROUGH 100 UPDATES

- 20-update physical run: PASS.
- 50-update physical run: PASS.
- 100-update physical run: PASS.
- Typical controlled partial refresh: approximately 713–720 ms.
- Full seed refresh: approximately 3.3 seconds.
- 500/1,000-update longevity, production full-refresh cadence, and long-term wear remain deferred to product hardening.

### P0.3 Local typing feasibility — COMPLETE

- 201/201 deterministic events processed exactly once and in order.
- Zero rejected events and zero queue overflows.
- Stale-frame coalescing and final display catch-up physically verified.
- One full and 36 partial refreshes completed without timeout.

### P0.4 One-way Fruit Jam → MagTag UART — COMPLETE

- 17/17 frames received and validated.
- 11 semantic viewports received; six rendered and five superseded.
- Final transmitted/displayed revision 11 and hash `2171BE7F` reconciled.
- Zero rejected frames, CRC failures, sequence gaps, or timeouts.

### P0.5 Bidirectional UART acknowledgements — COMPLETE

- Fruit Jam A0 TX → MagTag D10 RX.
- MagTag A1 TX → Fruit Jam A1 RX.
- Common ground, 115200 baud.
- Frame acceptance, refresh start, refresh completion, displayed catch-up, and `TEST_COMPLETE` physically verified.
- Final transmitted/displayed revision 6 and hash `DC12F5C9` reconciled.
- Zero rejected frames, CRC failures, sequence gaps, or timeouts.

## Priority 1 — Integrated multiline editor physical verification — VERIFIED

Physically verified on 2026-07-29 at commit `dfd71c3`, attempt 2. Evidence:
`docs/FRUITJAM_MULTILINE_EDITOR_TEST.md`.

Verified on hardware:

- Fruit Jam authoritative multiline editor;
- deterministic normalized `InputEvent` input adapter;
- Enter, Backspace, Delete, arrows, Home, and End;
- multiline viewport generation and deterministic wrapping;
- vertical scrolling with the cursor kept visible;
- five-line semantic MagTag viewport and punctuation glyphs;
- integrated editor-to-display flow end to end;
- physical stale-frame coalescing (330 states coalesced into 31 frames);
- displayed-revision confirmation (365 transmitted, 365 displayed);
- first usable writing prototype.

Observed: 362 of 362 events processed in contiguous order, zero rejected, zero
duplicates, maximum queue depth 1 of 64; all five scenario documents exact;
final hash `CFAEF7D1` reconciled on both sides; one full and 28 partial
refreshes; zero CRC failures, sequence gaps, overflows, or timeouts;
`DISPLAY_CAUGHT_UP` and `TEST_COMPLETE` received; operator approved the final
screen; both devices restored disabled.

Attempt 1 on 2026-07-28 failed on a harness defect: the MagTag charged the
operator-paced arming wait to its run budget. Fixed by `magwrite/run_clock.py`.
A second defect found in preflight — the MagTag boot gate never armed
`MAGTAG_EDITOR_DISPLAY` for the writable remount — was fixed in `dc5ac00`.
Both are covered by host tests; the suite is now 253 tests.

**Exit met:** a bounded physical multiline writing run completed with exact
event integrity, final display catch-up, and both devices restored disabled.

Not verified by this phase, and explicitly still open: USB keyboard input,
Bluetooth, LOLIN32, storage, microSD, autosave, battery integration, enclosure,
and production readiness. The MagTag's discarded-prefix/resynchronization
behaviour on the RX line remains uncharacterized, though it has never corrupted
a frame.

## Priority 2 — MagTag button controls over UART — DELIVERED IN V1.5

**Superseded.** This section is kept because the evidence documents reference the
`Priority N` headings; the requirements below are the ones the V1.5 work was
judged against, and every one of them is met. See **V1.5** for the design, the
reasoning, and the coverage.

The deferral recorded here — *V1 position 6, optional, a convenience because the
USB keyboard already supplies every control the writing loop needs* — was
withdrawn after the V1.4 bench run. It was right about the writing loop and wrong
about the product: a menu that can only be answered from the keyboard makes every
mode switch a hand off the keys.

One requirement below was answered rather than implemented. *Support press,
release, and deliberate long-press semantics*: press is the modelled event,
release is tracked only so its bounce cannot read as a press, and long press is
not implemented because no current action needs one and an unused gesture on a
four-button surface is a way to trigger something by accident.

Use the four existing MagTag front buttons as a control surface for the Fruit Jam through the proven return UART link.

Requirements:

- debounce buttons locally on the MagTag;
- send bounded, sequenced `BUTTON_EVENT` messages;
- support press, release, and deliberate long-press semantics;
- keep button interpretation and application state on the Fruit Jam;
- do not let the MagTag independently edit, scroll, save, or change documents;
- preserve display-status traffic on the same bounded return channel;
- define explicit queue-overflow and duplicate-event behavior.

Initial product mapping should prioritize:

- menu or document actions;
- page/scroll up;
- page/scroll down;
- save/status or confirm/dismiss.

Exact mappings remain configurable and should be validated against the real workflow.

**Exit:** every physical button event reaches the Fruit Jam exactly once, produces the intended Fruit Jam-owned action, and does not interfere with display acknowledgements. **Met on hardware 2026-07-30** — 9 presses, 9 frames sent, 9 accepted, 9 applied, zero duplicates and zero drops, with the display acknowledgement stream and viewport reconciliation unaffected. See **V1.5**.

## Priority 3 — Direct USB HID keyboard on Fruit Jam — PHYSICALLY VERIFIED

Implemented at commit `ab52961`. **Physically verified on 2026-07-29 at commit
`e75aa55`, on the third guarded attempt, with a wired EPOMAKER TH40
(`36B0:304E`).** Host suite raised from 253 to 472 tests, all passing.
Evidence: `docs/FRUITJAM_USB_KEYBOARD_TEST.md`.

Complete on real hardware:

- direct wired USB HID keyboard input on the Fruit Jam;
- normalized live key events — 374 reports to 168 events, 0 rejected;
- live multiline typing into the authoritative editor;
- real input accepted during display refresh, with 119 stale viewports
  coalesced and no keypress lost or duplicated;
- first interactive writing prototype: 49 viewport frames sent, 49 rendered,
  final transmitted revision 168 = final displayed revision 168, final hash
  `D462BA98`, `DISPLAY_CAUGHT_UP` and `TEST_COMPLETE` received, 0 CRC failures,
  0 timeouts, 0 queue overflows, operator visually approved.

Still open within this priority, all for keyboard-layout reasons rather than
software ones, and none blocking: apostrophe (the TH40 emits `0x2E` for it),
Home, End, Delete, Caps Lock toggling during a run, and key repeat. A
compatibility decision at commit `83ac72f` accepts Keyboard Application
(`0x65`) as a second finish control alongside Escape, because this keyboard
cannot deliver `0x29` from a standalone key.

Attempts 1 and 2 remain `FAIL` and are retained. Both used `36B0:3002`, which
the probe established is this same keyboard's own 2.4 GHz dongle; it enumerated
and claimed correctly and forwarded no key data. Neither failure was a software
defect.

Verified on real hardware during the earlier attempts:

- CircuitPython 10.2.1 USB host API surface and the absence of
  `adafruit_usb_host_descriptors`, so descriptors are parsed in-repo with no new
  dependency;
- enumeration of the real receiver `0x36B0`/`0x3002`, which exposes three HID
  interfaces;
- correct selection of interface 0 by the HID class triple, endpoint `0x81`,
  8-byte boot reports;
- `detach_kernel_driver`, `set_configuration`, `SET_PROTOCOL(boot)`, `SET_IDLE`;
- the `NO_DEVICE → ENUMERATING → READY` state machine and its diagnostics;
- boot report parsing and duplicate suppression on real reports;
- the HELLO/STATUS_HELLO handshake over the real UART;
- the two-phase run clock excluding a 79.7 s operator arming wait;
- fail-closed refusal, guard preservation, and a complete FAIL summary on the
  idle-timeout stop condition.

The blocking issue recorded here previously — the wireless keyboard delivering
no HID data through its receiver — was resolved by fitting a wired keyboard, as
that entry predicted. The receiver is not supported and remains out of scope.

Next in this area, recommended and not yet started: **MagTag button events over
the existing UART return link**, with the Fruit Jam interpreting button actions.
Storage and battery work stay out of scope for it.

Also observed by the operator during the verified run: the display updated in
bursts rather than per keystroke, because viewport sends were paced by a single
fixed 2.6 s interval. That follow-up is now **V1.1 below**, which replaced the
fixed interval with an adaptive policy.

### Original requirements

Integrate one known keyboard directly through the Fruit Jam USB host port.

Preferred order:

1. wired USB keyboard; or
2. wireless keyboard with a standard USB receiver.

Requirements:

- implement a USB HID `InputAdapter` without changing the editor core;
- support letters, punctuation, Shift, Caps Lock, Enter, Backspace, Delete, arrows, Home, and End;
- handle key press, release, hold, and deliberate repeat;
- report unsupported HID usages explicitly;
- reconnect cleanly after keyboard sleep or receiver reconnect;
- preserve bounded queues and exactly-once normalized event processing;
- validate a real paragraph editing session on hardware.

The LOLIN32 Bluetooth bridge is not part of this priority.

**Exit:** a real USB HID keyboard can type and edit a multiline document while the MagTag display trails and catches up without lost or reordered input.

## V1.1 — Responsiveness and keyboard completeness — HOST-VERIFIED

Implemented on 2026-07-29. Host suite raised from 472 to 572 tests, all
passing. **No physical run has been performed for this phase, so no claim is
made about physical latency or about any key behaving correctly on real
hardware.** Everything below is host-verified only.

### Adaptive display pacing

The fixed 2.6 s send interval was replaced by an adaptive policy in
`fruitjam/magwrite_transport/pacing.py`, which is now the single home for every
display timing constant. Three gates, applied to the newest pending viewport:

1. **busy** — never transmit while the MagTag has an unfinished refresh; at
   most one viewport is ever in flight;
2. **coalescing** — a change must be pending for 0.25 s before it may be sent,
   so a single keypress can never earn its own frame;
3. **interval**, whose floor depends on what the writer is doing:
   - onset, nothing sent yet — send as soon as coalescing allows;
   - caught up, no input for 0.6 s — floor drops to 1.3 s, just past the
     slowest measured partial refresh;
   - sustained, still typing — floor stays 2.6 s, the interval already proved
     to fit the authorised 50-partial-refresh ceiling.

The two cases a writer actually perceives — the first text of a burst, and the
last text before a pause — no longer wait out a full interval. A pause costs at
most one extra frame, because once it is caught up nothing is pending until
typing resumes.

Constants are chosen from the measured panel: full refresh 3500 ms, partial
refreshes 873–1122 ms, mean ≈1050 ms.

### Keyboard completeness

Apostrophe, double quote, Delete, Home, End, Caps Lock on and off, Shift with
Caps Lock, and repeat for Backspace, Delete and the arrows — with cancellation
on release — are all covered end to end by host tests that assert the resulting
document.

Printable characters and Enter were also repeatable when this phase shipped;
that was corrected on 2026-07-29 after the first ordinary writing session. See
*Key repeat corrected* below.

The EPOMAKER TH40's apostrophe was diagnosed before anything was changed. It
sends usage `0x2E` (`=`/`+`) **with modifier byte `0`**, so it is neither a
Shift nor an Fn/AltGr question: the keyboard sends the wrong usage. Standard HID
was therefore left alone, and a named device layout in
`fruitjam/magwrite_transport/keyboard_layout.py` remaps `0x2E → 0x34` for that
vendor and product only. Every unrecognised keyboard gets standard HID.

Escape `0x29` and Application `0x65` remain FINISH, and unsupported usages
remain explicitly and boundedly reported.

**Not resolved:** Home, End and Delete were never reachable on the TH40 — every
attempt at its Fn layer switched the keyboard out of USB mode, so no report was
ever captured. No mapping was invented for them.

### Physical verification — one attempt, FAILED, certification retired

One authorised attempt was made on 2026-07-29 and **failed without producing a
single valid frame or a single measurement.** No responsiveness result exists,
and none is claimed anywhere in this repository. The adaptive pacing policy and
the TH40 apostrophe mapping remain **host-verified only**. The full record is in
`docs/MAGWRITE_V1_RESPONSIVENESS_TEST.md`.

Guards, after the attempt:

| Device | Guard | Outcome |
| --- | --- | --- |
| Fruit Jam | `/magwrite_v1_responsiveness.started` | never created |
| MagTag | `/magwrite_v1_responsiveness_display.started` | created and consumed |

Both paths are burned: never reused, never deleted. Every one of the twenty-four
guards from earlier milestones was verified present and unchanged afterwards.

The attempt failed on the ceremony around the product rather than on the
product. The known-working path was already physically verified at `e75aa55`;
what was missing was a way to bring it up repeatably, which the one-shot guard
design made impossible by construction. So the certification machinery specific
to this phase — its two activation modes, its two entry points, its boot-gate
additions, and its evidence plumbing — was **removed**, and replaced by an
ordinary development runtime: `docs/DEVELOPMENT_RUNTIME.md`.

The adaptive pacing policy, the passive latency recorder, the TH40 layout rule,
and every host test covering them were kept; they are useful in ordinary
development and decide nothing on their own. The guarded harnesses for the
completed milestones are untouched and remain available for the next real
verification milestone.

**Exit, if this phase is ever resumed:** a fresh plan with fresh guard paths and
fresh authorisation, producing measured keypress-to-visible timings on hardware.
It is not scheduled, and nothing later in V1 is blocked on it.

### Development runtime — available

`docs/DEVELOPMENT_RUNTIME.md` describes the repeatable bench setup that replaced
the retired harness: wired USB keyboard, authoritative Fruit Jam editor,
bidirectional UART, MagTag display, adaptive pacing, final reconciliation. It
writes no guard, never remounts the filesystem away from the host, starts and
stops as often as needed, and stops cleanly on Escape `0x29` or Application
`0x65`. It performs no verification and licenses no claim.

On the EPOMAKER TH40, Escape is the control that reaches the board. The key
labelled as Application sends modifier `0x40` with **no usage byte**, so nothing
arrives as a finish request; usage `0x29` arrives cleanly and stops the runtime.
Recorded as an observation, not a defect: it is a keyboard-mapping matter and
`PRIORITY.md` defers those.

### Key repeat corrected — 2026-07-29

The first ordinary writing session ended clean but produced a shorter document
than intended. The Fruit Jam log accounted for it exactly — 121 events against
21 characters, 50 of them Backspace, 27 of those repeats, and all 27 from three
deliberate holds of 859 ms, 1234 ms and 1437 ms. The 500 ms onset and the
cancellation on release were both correct and the log proved it: no repeat ever
fired on a tap, and none ever followed a release.

The defect was the eligible set. Printable characters and Enter were repeatable,
so resting a finger on a letter duplicated it and holding Enter inserted blank
lines — quietly, because the panel trails typing by one to three seconds, so the
damage reaches the authoritative document before the writer can see it.

Repeat is now exactly the keys held on purpose to cover distance: Backspace,
Delete, and the four arrows. Delay, interval, bounded catch-up, and
newest-press ownership are unchanged. Host suite 679 tests passing.

**Ordinary writing confirmed on hardware the same day.** A session typed three
lines of prose and stopped cleanly on Escape:

| | |
| --- | --- |
| Result | `COMPLETE`, no stop reason |
| Events | 63 generated, 63 processed, 0 rejected |
| Document | 63 characters, 4 lines — one character per keystroke |
| Repeat events | **0** |
| Reports | 128 received, 0 duplicate, 0 rollover, 0 unsupported |
| Reconciliation | transmitted revision 63 = displayed revision 63, hash `CA09FBF6` both sides |
| Panel | 9 refreshes, 1 full and 8 partial, 0 CRC failures |
| Boards | no guard written, filesystem never remounted, both restartable |

This confirms normal writing works. It is not a responsiveness measurement and
licenses no timing claim.

## Priority 4 — Single-document persistence and recovery — V1.2 — PHYSICALLY VERIFIED

microSD-backed storage on the Fruit Jam. Implemented; `docs/PERSISTENCE.md`
carries the design, the recovery argument, and the policy values.

Requirements, all implemented and host-verified:

| Requirement | Where |
| --- | --- |
| card present and mountable at boot | `sd_storage.mount`, six named statuses |
| one active plain-text or Markdown document | `/sd/magwrite/documents/active.md` |
| create a new draft or open the latest | `config.DOCUMENT_OPEN_MODE` |
| crash-safe autosave | `persistence.PersistenceController` |
| append-only recovery journal | `recovery/active.log`, full snapshots |
| atomic or recoverable checkpoints | three-step sequence, every window survivable |
| tolerate a truncated final record | three independent defences |
| manual save and visible save state | Ctrl-S; one-character status indicator |
| restore the last acknowledged edit | `LiveTypingSession.restore` |

The acknowledged revision is defined as the latest revision accepted by the
**Fruit Jam editor**, not the MagTag display. Display acknowledgements govern
pacing; editor acceptance governs durability. The two are deliberately decoupled
so a stalled panel can never stall a save.

Scope held deliberately narrow, as instructed: one document, no document
browser, no shell, no new certification framework.

**Exit met on 2026-07-30:** a writing session survived forced power loss with
the final acknowledged edit recovered exactly. The host suite proves the logic,
including a sweep that cuts power at every byte offset of a journal append; the
physical run below proves the claim.

### Hardware bring-up — 2026-07-30

Probed with `tools/fruitjam_sd_probe.py` on CircuitPython 10.2.1,
`adafruit_fruit_jam`, UID `FFDBA7B15146C218`. Evidence:
`docs/FRUITJAM_SD_PROBE.jsonl`.

Confirmed on the board:

- pin aliases read off the board — `SD_CS`, `SD_SCK`, `SD_MOSI`, `SD_MISO`,
  `SD_CARD_DETECT`, plus a separate `SDIO_*` interface;
- the card sits on the **dedicated** SPI bus, so `config.py` now names those
  four aliases explicitly instead of using the unproven shared `board.SPI()`.
  This was the one configuration change the hardware required;
- `SD_CARD_DETECT` is claimed by the firmware before user code runs, so the
  optional card-detect path stays disabled and presence is inferred;
- `sdcardio`, `os.sync`, and `os.statvfs` are all present;
- the shipped `sd_storage.mount` correctly reported `UNMOUNTABLE` with
  `[Errno 19] No such device` for the card described below.

The card originally in the slot carried no usable filesystem — a valid MBR whose
one partition entry claimed more sectors than the card physically had, with no
FAT volume boot record at that offset or twelve others. It was reformatted with
explicit authorisation. FatFs sizes the FAT width from the volume, so a 946 MB
card came out **FAT16, not FAT32**; nothing in V1.2 depends on the width.

### Physical verification — PASSED, 2026-07-30

Evidence: `docs/FRUITJAM_V12_PERSISTENCE_SERIAL.jsonl`.

Writing session: 12 autosave journal appends and 3 checkpoints, one automatic and
two manual. Ctrl-S arrived as modifier `0x01` usage `0x16`, produced a manual
checkpoint, and **inserted no character**. Three presses collapsed into two
checkpoints. The save indicator moved `u` → `r` → `s` on the panel.

Forced power loss: USB pulled mid-session with no clean stop. On restart the
shipped store recovered

```json
{"recovered":true,"revision":73,"source":"JOURNAL","truncated_final_record":false,
 "rejected_records":0,"cursor_row":2,"cursor_column":8,"characters":71}
```

and the session restored revision 73, 3 lines, 71 characters, cursor at (2, 8).
Checked against the console's own per-keystroke record: the last checkpoint
before the cut was revision 65 at 63 characters, eight more characters were
typed, and recovery returned exactly those. **Every acknowledged edit survived.**

One defect was found and fixed during the run: a mount survives a soft reboot, so
the second start raised `SD_SCK in use` and reported `NO_CARD` while a good card
was mounted. `sd_storage.already_mounted` now adopts an existing mount. On the
development runtime, where saving a file restarts it, this had affected every
restart.

**Exit met.**

## V1.3 — MagWrite Shell — PHYSICALLY VERIFIED

The application shell the writing modes live in. It comes after persistence
because a shell that cannot reliably open and save a document is a menu, not a
product. `docs/SHELL.md` carries the design and the reasoning.

Requirements, all implemented and host-verified:

| Requirement | Where |
| --- | --- |
| one owner of application state, distinct from the editor | `shell.Shell`, no editor, store, clock, or transport |
| explicit states with entry, exit, back, and failure behaviour | `MAIN_MENU`, `EDITOR`, `SAVE_STATUS`, `ERROR`, `EXIT` |
| Journal, Quick Note, Drafts, and Recent on the main menu | `shell.MENU_ITEMS`, all routing into the one document |
| a viewport reusing the proven renderer and pacing | `shell_viewport`, same `encode_viewport`, scenario 7 |
| keyboard-driven navigation, no MagTag buttons | Up, Down, Enter, and the existing finish gesture |
| the document preserved across every transition | one `MultilineEditor` for the session; the shell never touches it |
| no recoverable work lost leaving or re-entering the editor | every exit passes through `SAVE_STATUS`, which checkpoints |
| the correct state restored after restart or power loss | `Shell.restore`, derived from what recovery returned |
| bounded, fail-closed transitions | one `_transition` door; anything unknown becomes `ERROR` |

Three decisions worth recording, each argued in full in `docs/SHELL.md`:

- **the shell adds no keymap entry.** Up, Down, and Enter are already normalized
  editor events, and the finish gesture already existed with physical evidence
  behind it. Under the shell it means *back* — leave the current state toward its
  parent — and at the root it is still the clean stop;
- **Save/Status is a guard, not an information screen.** Leaving the editor goes
  through it and entering it forces a checkpoint, because leaving is when the
  writer is most likely to walk away and unsaved work is most exposed;
- **the opening state is derived, not stored.** Persisting it would mean a second
  file that must stay in step with the journal through a power cut, which is the
  two-file atomicity problem the storage design already refused once. A recovered
  document means the writer was writing, so the shell opens where the words are.

One real behaviour changed: reaching the document bound used to raise and end the
session. The refused edit changes nothing, so the document is intact; it is now
shown on a recoverable error screen. With `ENABLE_SHELL = False` the pre-shell
behaviour, and every viewport payload the physical runs measured, is reproduced
exactly.

Scope held where the phase set it: no document browser, no per-mode storage
format, no MagTag button work, no keyboard-mapping detours, no new certification
framework.

**Exit:** the writer can move between the shell and a document repeatedly
without losing state or stalling the display. The host suite proves the logic —
`host-tests/test_shell.py` drives the whole path with scripted USB reports
through the real editor, storage, transport, and MagTag renderer — and the bench
run below proves it on the boards.

### Physical verification — 2026-07-30, commit `19afaa9`

Run on the bench with the ordinary development runtime per `docs/SHELL.md`. No
guard was claimed, no filesystem was remounted, and both boards stayed
host-writable throughout — the deploy, three restarts, and this write-up all went
over USB while the runtime was live. Evidence:
`docs/FRUITJAM_V13_SHELL_SERIAL.jsonl` and `docs/MAGTAG_V13_SHELL_SERIAL.jsonl`,
with the `.timestamped.jsonl` companions for correlating the two consoles.

Fruit Jam `FFDBA7B15146C218` on CircuitPython 10.2.1, MagTag `C7FD1A005DEA` on
9.1.1, EPOMAKER TH40 on the USB host port, layout `EPOMAKER_TH40`, card mounted
at `/sd`. Three sessions: two ended `result: COMPLETE` from the main menu, and
the middle one was ended by pulling the USB cable, which was the point of it.

All twelve exit criteria observed:

| # | Criterion | Observation |
| --- | --- | --- |
| 1 | main menu renders | `MAGWRITE MENU`, four items, `>` on the selection, status `MENU 1/4`; confirmed on the panel by the operator |
| 2 | Up/Down navigation | `shell_selection_moved` across the full range 0–3, clamped at both ends, never wrapped |
| 3 | Enter opens the item | `shell_mode_entered` for `JOURNAL`, `QUICK_NOTE`, `DRAFTS`, and `RECENT`, each followed by `shell_transition` `reason: "menu selection"` → `EDITOR` |
| 4 | writing still works | `live_event_processed` per keystroke, revisions 74→83 and 84→127, pacing and catch-up unchanged from V1.2 |
| 5 | Esc leaves through Save/Status | 8 × `shell_left_editor`; no path out of the editor bypassed it |
| 6 | Save/Status forces a checkpoint | `document_checkpointed` with `manual: true` on every one |
| 7 | Enter returns to the menu | `shell_transition` `from: SAVE_STATUS` `reason: "confirmed"` |
| 8 | Esc resumes without losing text | 5 × `reason: "resumed writing"`; character count and cursor identical across each round trip |
| 9 | restart and power loss restore | clean restart recovered `source: CHECKPOINT` revision 83; the **cable pull** recovered `source: JOURNAL` revision 127, 125 chars, 32 lines, cursor row 31 col 12, `truncated_final_record: false`, `rejected_records: 0` — and `shell_restored` `state: EDITOR` put the writer back in the words, not the menu |
| 10 | bounded failure is recoverable | 4 × `live_event_rejected` `"document line capacity reached"` → `shell_fault` → `ERROR` → `MAIN_MENU`, session alive and document intact each time. No `LiveSessionError`, no stop |
| 11 | Esc from the main menu stops cleanly | `reason: "stopped from the main menu"` → `EXIT`, `dev_runtime_session_summary` then `dev_runtime_stopped`, `result: COMPLETE` |
| 12 | boards host-writable, no guards | every summary `guard_written: false`, `filesystem_remounted: false`, `restartable: true` |

Transport was clean across the run: 23 viewport frames sent and 23 accepted,
final transmitted and displayed revision both 27, `crc_failures: 0`,
`parser_rejections: 0`, `resynchronization_events: 0`, `status_sequence_gaps: 0`,
`queue_overflows: 0`, `stale_renders: 0`, `viewport_frames_superseded: 0`. The
panel did 1 full and 22 partial refreshes, mean 946 ms, maximum 1046 ms — the
shell's screens go out through the document's pacing and cost the panel nothing
new, which is what sharing the renderer was for.

`shell_ignored_events: 12` is the quiet result worth naming: a dozen keystrokes
aimed at a shell screen were discarded rather than reaching the draft. The
requirement that no transition loses work has an unstated twin — no transition
may *invent* work — and that counter is the evidence for it.

Two observations recorded rather than fixed, neither blocking:

- **the mode is not restored across a restart.** `shell_restored` reports
  `mode: JOURNAL` after a session that ended in `DRAFTS` or `RECENT`. Only the
  *state* is derived from recovery, deliberately, and in V1.3 all four items
  route into the one document, so it is cosmetic here. It stops being cosmetic in
  V1.4, where a mode carries its own policy, and belongs to that phase;
- **the MagTag must be restarted after an interrupted session, not only after a
  completed one.** Twice it held parser state from a session that never finished
  — once from the V1.2 run, once from the cable pull — and rejected the next
  Fruit Jam's handshake with `duplicate or reversed input sequence`, which the
  Fruit Jam then reported as `status_hello timeout`. Restarting the MagTag first
  cleared it both times. `docs/DEVELOPMENT_RUNTIME.md` overstated this and has
  been corrected. It is a bring-up ordering fact, not a shell defect: no shell
  frame was involved and no document was affected.

## V1.4 — Journal, Quick Note, Drafts, and Recent — PHYSICALLY VERIFIED

The four writing modes, built on the shell and on persistence.

- **Journal** — dated, append-oriented entries;
- **Quick Note** — fastest possible capture into a new document;
- **Drafts** — the working set of documents;
- **Recent** — return to what was open last.

Requirements:

- each mode is a thin policy over the one proven editor and storage layer;
- no mode owns its own document format or its own recovery rules;
- Recent survives forced power loss.

**Exit:** a real writing session that starts in the shell, captures in two
different modes, and recovers correctly after a forced power loss.

**Met on 2026-07-30**, by a deliberately minimal bench run — with the exception
of the forced power loss, which the operator scoped out and which is recorded as
unverified below. Two modes were captured in one session and a clean restart
restored both the document and its mode.

### Implementation — host-verified

`docs/MODES.md` carries the design and the reasoning. Two changes ship together
and the order was deliberate: **the document bound was raised first**, because a
mode that opens a document you cannot write a page into is not worth building.

#### The document bound

| Bound | V1.3 | V1.4 |
| --- | --- | --- |
| `MAX_DOCUMENT_CHARS` | 512 | **8192**, roughly 1,400 words |
| `MAX_LINE_CHARS` | 96 | **1024** |
| `MAX_DOCUMENT_LINES` | 32 | **512** |

The binding bound was not the document limit and not the line count — it was
`MAX_LINE_CHARS`. The editor word-wraps, so **a paragraph is one logical line**,
and 96 characters is about a sentence and a half. That is the same fact recorded
above as "bounded failure is recoverable": the four `document line capacity
reached` faults in the V1.3 bench session were the device refusing the fifth
sentence of a paragraph, recovering correctly from a refusal it should not have
been making.

No architectural change was needed to support it, which is the answer to the "do
not introduce file-backed editing unless the design truly cannot" constraint:

- `journal.MAX_RECORD_BYTES` is now *derived* from `MAX_DOCUMENT_CHARS` rather
  than written down beside it. The two drifting apart would mean a document the
  editor accepts and the journal refuses to encode;
- `Layout.locate` is linear in the characters *before the cursor* and runs per
  keystroke; `Layout.rows` is linear in the document but runs only per viewport
  build, which pacing already holds to roughly one a second;
- what crosses the UART is unchanged. A five-row window is the same size whatever
  is behind it;
- `RESERVE_BYTES` went 32 KB → 128 KB so "refuse before exhaustion" does not
  degrade into "refuse during exhaustion" when the document is at its largest.

Another order of magnitude *would* need a different architecture. That is the
line and it has not been crossed.

#### The four modes

Each mode is a *choice of document* and nothing else. Every one resolves to
recording the open in an append-only catalogue and pointing the proven store at a
document id. One editor, one storage format, one recovery system, one shell, one
renderer, one UART, one pacing path.

- **Journal** continues the newest entry with the cursor at the end of the
  writer's last words, and rolls over to the next numbered entry when fewer than
  512 characters remain;
- **Quick Note** always creates a new empty document and opens it immediately;
- **Drafts** lists the working set, newest first, five rows with the window
  following the selection;
- **Recent** opens the document with the highest open ordinal.

**Dating is deferred and stated as such.** The prototype has no RTC and no
network, so entries are numbered rather than dated. The alternative was a date
derived from `time.monotonic`, which is a fabricated date printed next to a
writer's own words. `PRODUCT.md` asks for dated journal entries and this does not
yet deliver them.

#### Metadata, and the V1.3 hand-forward

The catalogue is `/sd/magwrite/index.log`, `MWX1` records with the same three
corruption defences the recovery journal has. It persists document identity,
kind, title, and a monotonic open ordinal. **The highest ordinal is the active
document**, so there is no separate pointer file to disagree with the catalogue
after a power cut — the two-file atomicity problem this design already refused
once.

That closes the item V1.3 recorded: a restored session now restores its mode,
because the mode is a property of the document. A document's kind is `JOURNAL`,
`NOTE`, or `DRAFT`; Drafts and Recent are ways of *reaching* a document, and a
note opened through Drafts is still a note.

#### Migration

A card written by V1.2 or V1.3 is adopted by appending **one catalogue record**.
`active` is a legal document id and is the one those builds already used, so
`documents/active.md` and `recovery/active.log` are already correct under the
per-document naming and are not touched. `recovery/checkpoint.log` is read at its
old name whenever `active.ckpt.log` does not exist, and is never renamed: a
rename is a write, and writing to somebody's only copy in order to upgrade it is
how upgrades lose documents. A host test asserts every pre-existing file is
byte-identical afterwards and that the only new file is `index.log`.

#### Switching documents

V1.3's invariant was "one editor, never closed". V1.4 keeps it and makes it
precise. A switch is a handover, ordered: checkpoint the outgoing document, then
select, then load into the same editor, then tell the shell. Step one is
unconditional — a threshold that has not been reached is not a reason to hand a
document over with work only in RAM. `document_revision` stays session-monotonic
across the switch, because the acknowledgement tracker and the save state both
assume it never goes backwards; per-document recency still holds, because a
stored revision is the highest ever written to that document.

#### Coverage

1,056 host tests pass, up from 929. `test_document_bounds.py` (42) covers
documents far longer than 32 lines, scrolling at the beginning, middle, and end,
editing at the very edge of the bound, and clean refusal at the real limit with
the text, cursor, both revisions, and the recovered document asserted unchanged.
`test_library.py` (82) covers the record format, the catalogue, the four modes,
migration file-by-file, and two full sessions — two modes captured in one run,
and a forced power loss that recovers the words, the identity, and the mode.

No test uses a literal bound; every size is derived from the editor's constants,
so they keep testing the property the next time the bounds move. That is a
correction of a real defect found in the existing suite: a test asserting that
5,000 characters were refused stopped testing anything the moment the bound moved
past it.

#### Recorded, not chased

- an 8 KB document journaled every twelve revisions writes appreciably more per
  session than a 512-byte one did. The per-append SPI cost has not been measured
  on hardware and belongs to the physical run;
- `PRODUCT.md`'s "dated journal entry creation" is not delivered; see above;
- there is no way to delete or rename a document from the device. The catalogue
  is bounded at 64 and refuses cleanly past it. Renaming and archiving are V1.5
  scope and the record format already supports both as one append.

### Physical verification — 2026-07-30, commit `bdfe47c`

A deliberately minimal bench run: the smallest set of physical checks that
confirms V1.4 works on hardware, scoped by the operator to exclude a
certification campaign, a forced-power-loss test, a maximum-size test, and a
keyboard-mapping investigation. **What it proves is exactly what it ran**, and
the gaps are named at the end of this section rather than implied to be covered.

Evidence: `docs/FRUITJAM_V14_BENCH_SERIAL.jsonl` and
`docs/MAGTAG_V14_BENCH_SERIAL.jsonl`, with `.timestamped.jsonl` companions;
`docs/FRUITJAM_V14_PREFLIGHT_RECOVERY.jsonl` and
`docs/V14_PREFLIGHT_DOCUMENT_BACKUP.md` for the pre-migration state of the card.

Fruit Jam `FFDBA7B15146C218` on CircuitPython 10.2.1, MagTag `C7FD1A005DEA` on
9.1.1, EPOMAKER TH40 on the USB host port, layout `EPOMAKER_TH40` selected
automatically, card mounted at `/sd`. Three Fruit Jam boots. 1,056 host tests
passed on the same commit beforehand.

#### Pre-flight — the writer's document, before anything was written

The shipped read-only `tools/fruitjam_recovery_check.py` was run on the board
against the un-migrated card, and its result recorded to a host-side backup
*before* V1.4 was allowed to touch anything: `source: CHECKPOINT`, revision 127,
125 characters over 32 lines, cursor row 31 column 12, `rejected_records: 0`,
`truncated_final_record: false`, `mirror_stale: false`, and an empty catalogue —
the exact shape of a card written by V1.2 or V1.3.

Doing this first was the operator's instruction and it was the right order. A
migration that runs before the document has been read back is a migration whose
correctness cannot be checked afterwards.

#### The six checks

| # | Check | Observation |
| --- | --- | --- |
| 1 | the existing document opens intact | `document_recovery` revision 127, 125 chars, `source: CHECKPOINT` → `document_migrated` → `shell_restored` `state: EDITOR` → `live_document_restored` 125 chars, 32 lines, cursor 31/12. Confirmed on the panel by the operator |
| 2 | one new document is created | Quick Note produced `n0001`, title `NOTE 1`, `kind: NOTE`, opening at `characters: 0` |
| 3 | switching loses no text | four `shell_document_opened` across two documents; `active` reopened at 259 chars and `n0001` at 68, both exactly as left |
| 4 | restart restores document *and* mode | `document_active` `n0001` `opened: 3` `kind: NOTE` → `shell_restored` `mode: QUICK_NOTE` → `live_document_restored` 68 chars, 41 lines, cursor 40/14 |
| 5 | a paragraph past the old 96-char limit | the draft went 125 → 259 characters on one logical line; recovery reports `cursor_column: 133`. No refusal of any kind |
| 6 | line breaks past the old 32-line limit | `n0001` finished at `final_document_lines: 41`, 68 characters — `quick note one`, forty newlines, `line forty one` |

**Zero faults across the run:** `shell_faults: 0`, `save_failures: 0`,
`document_open_failures: 0`, `library_refusals: 0`, `index_rejected_records: 0`,
`events_rejected: 0`. Not one `capacity reached` event — the four that V1.3's
bench session produced in ordinary prose did not recur, which was the entire
point of raising the bound.

Two V1.4 design claims were observed directly rather than inferred:

- **the handover is ordered.** Every one of the four document switches emitted
  `document_checkpointed` `manual: true` `save_state: SAVED` for the *outgoing*
  document before `shell_document_opened` fired for the incoming one. Step 1 is
  unconditional and behaved that way;
- **the mode arrives with the document.** `active` came back as `kind: DRAFT` /
  `mode: DRAFTS` even when reached *through* the Drafts list, and the restart
  restored `QUICK_NOTE` from the catalogue with no menu involved. That closes the
  one gap V1.3 recorded and handed forward.

Migration cost exactly one append, as designed: `index_appends: 1` on the first
boot, `documents: 1`, and `index_appends: 0` on both later boots. Nothing the
writer owned was moved, renamed, or rewritten.

Transport on the final clean session: handshake accepted, viewport sent and
accepted, one full refresh of 3,484 ms, `displayed_revision: 3`, viewport hash
reconciled, `crc_failures: 0`.

#### What this run did not cover

Stated plainly, because the nine exit criteria in `docs/MODES.md` are *not* all
met by it:

- **Journal and Recent were never opened.** Only `QUICK_NOTE` and `DRAFTS` appear
  in the console. Criteria 3 and 5, and the part of criterion 1 that covers those
  two items, are unverified on hardware;
- **Drafts scrolling was not exercised** — two documents do not fill a five-row
  panel, so criterion 4 is only half observed;
- **no forced power loss was performed.** Criterion 8 is unverified on hardware.
  Every restart here was clean and checkpointed first;
- **the per-append SPI cost of an 8 KB journal record was still not measured.**
  Nothing in the run felt slow, but an impression is not a measurement and this
  stays in the backlog where V1.4's implementation notes put it.

#### Recorded, not fixed

- **CircuitPython 10.2.1 exposes the microSD to the USB host as a third mass
  storage LUN**, alongside CIRCUITPY and CPSAVES, and auto-mounts it at `/sd`
  before user code runs. This is new information: the card is reachable from the
  host after all. The shipped `sd_storage.mount()` handles it without a change,
  adopting the existing mount and reporting `sd_already_mounted` with
  `storage_detail: "adopted a filesystem already mounted at /sd"` — a path added
  for restartability that turned out to cover this too;
- **Windows cannot read the card's files while the board owns it.** Every
  non-empty file reports "The file or directory is corrupted and unreadable" from
  the host while the board reads all of them cleanly. The host's cached view of a
  volume the device writes underneath it is stale, not damaged. It does mean the
  "plain text, readable on any computer" promise in `docs/MODES.md` is not
  currently true *while a session is live*, and it means the host holding the
  volume read-write is a second writer on the writer's only copy. Worth a
  deliberate decision in a later phase — likely a `boot.py` that keeps the card
  off the USB bus;
- **the MagTag restart ordering bit again, and the fault was procedural.**
  Restarting the Fruit Jam by autoreload without restarting the MagTag first
  produced `duplicate or reversed input sequence` and `status_hello timeout`,
  exactly as `docs/DEVELOPMENT_RUNTIME.md` warns. The restore had already
  completed before the handshake, so no evidence was lost; the run was repeated
  in the documented order and completed cleanly. This is the third occurrence and
  it remains transport hardening rather than a mode defect;
- the character mis-mappings in the recovered text (`tgus` for `this`, `us` for
  `is`) are the known TH40 keyboard-mapping item, untouched by this phase.

## V1.5 — Shell UX: one-gesture exit and MagTag buttons — PHYSICALLY VERIFIED

The V1.4 bench run produced a working device that was tiring to use. Two things
stood between the writer and the product, and both were in the shell rather than
in the editor, the storage, or the transport — which is why this phase touches
none of those.

Scope was fixed deliberately narrow. No new certification framework, no change to
any persistence format, no revisiting of keyboard mappings, and no dongle
compatibility work, which is paused and resumes immediately after this.

### 1. The Save/Status interruption is removed

The defect, as observed:

- Escape from the editor opened a Save/Status screen;
- the main menu was drawn underneath it;
- a second Enter was needed to reach the menu the device had already drawn.

`STATE_SAVE_STATUS` and `shell_viewport.save_payload` are gone. Escape now
checkpoints the document and lands on the main menu in one gesture.

**The checkpoint is unchanged and still unconditional.** It moved, it did not
weaken: it runs inside the gesture, silently, and *before* the transition, so the
destination depends on the result. A checkpoint that succeeded — or a bench with
no card at all — goes to the menu. A checkpoint that actually **failed** goes to
the recoverable error screen the shell already had, carrying the store's own
reason, and that is the only save outcome that interrupts anything.

The argument the V1.3 design made for the screen was that a screen every exit
passes through makes the checkpoint unconditional. That was true of the
checkpoint and it remains true — but it was never an argument for the screen. The
checkpoint is unconditional because the code performs it unconditionally, not
because a frame was drawn afterwards. What the screen actually did was report a
result the writer had no decision to make about, and charge them a keypress for
reading it, at the exact moment they had already said *take me out of this
document*. The menu being drawn underneath made that unmistakable: the device
knew where they were going and stopped them anyway.

The save state the screen used to name in words is preserved where a fact nobody
has to act on belongs: the **one-character indicator in the status field of every
ordinary frame**, unchanged since V1.2, including on the menu the writer now
lands on.

A card-less bench is deliberately not an error. It is the reported degraded mode
the panel draws as `x`, and an error screen in front of every exit would have
recreated the interruption this phase removed.

### 2. The four MagTag buttons are the primary shell controls

Over the existing return UART link, as `BUTTON_EVENT`, message type 13 — the same
version-1 frame, the same CRC-32, and the same sequence numbering as every
display acknowledgement. No second transport and no second channel: that reuse is
what gives buttons gap detection and duplicate rejection without inventing
either.

| Button | Action | Meaning |
| --- | --- | --- |
| A | `MENU` | open/back to the main menu |
| B | `UP` | move the selection up |
| C | `DOWN` | move the selection down |
| D | `SELECT` | select/confirm |

**The Fruit Jam remains the sole owner of shell and document state.** The MagTag
sends normalized actions and stops: `UP`, not `B`, and never "next journal
entry". A raw button identity would force the Fruit Jam to know the panel's
physical layout; a semantic one would be the display board deciding product
behaviour. *The writer asked to move down* is the narrowest honest thing that
board knows.

Debouncing is **stability, not a press lockout**: a reading must hold for 25 ms
before it is believed, on both edges. A lockout only covers the press edge, and
the release bounce then arrives after it expired and reads as a second press —
precisely the duplicate this phase was asked to prevent. On top of that the same
action is refused twice inside 250 ms, which is close to one panel refresh, so a
selection can never move twice for one visible frame. A held button does not
repeat: on a four-item menu that takes about a second to redraw, auto-repeat can
only overshoot something the writer cannot see yet.

Duplicate suppression is layered, and each layer catches a different failure:
contact chatter at the pad; the transport's own sequence numbering at the frame;
and a monotonic press ordinal at the `ButtonInbox`, which refuses any ordinal at
or below the highest already accepted — the case a resynchronisation after line
noise can still produce. The inbox is bounded and drops the **oldest**, because a
backlog is stale intention and the newest press is what the writer still means.

Two rules the buttons do not share with the keyboard:

- **no button reaches the document.** In the editor everything except A is
  counted and discarded, including Up and Down, which could plausibly have moved
  the cursor. A control surface that can alter a draft is one that can alter it
  from inside a bag;
- **A at the main menu does nothing.** It is a *go to the menu* control, not a
  back control, so it cannot walk off the root and end a writing session. Escape
  still can, because a writer who pressed Escape twice at the root meant it.

The keyboard keeps every shell key it had, as a fallback. The requirement was
that the intended product flow work from the buttons, not that the keyboard stop
working, and Escape from the editor is deliberately the same one-gesture exit
that button A performs.

Buttons and keys meet at one handler: `Shell.button` maps its three movement
actions onto the editor event kinds the keyboard already produces and calls the
identical per-state code. There is one definition of what Down means in the
Drafts list and it cannot drift.

Button frames share the MagTag's bounded status outbox with acknowledgements,
with headroom reserved for the acknowledgements an in-flight refresh is about to
need. A press that would eat into that headroom is dropped and counted rather
than allowed to stall the panel — display acknowledgements are preserved, which
was a constraint of the phase.

`ENABLE_MAGTAG_BUTTONS` ships **enabled**, unlike every harness in this
repository, for the same reason persistence and the shell do: it is the product's
control surface, not a hardware experiment. It claims no guard, remounts nothing,
writes nothing, and reads four GPIOs. A pin the board does not expose is a
reported degraded mode — the panel runs, the keyboard still drives the shell —
never a refusal to start.

### Coverage

`host-tests/test_buttons.py` is new and drives four layers: the pad against a
simulated contact that actually bounces on both edges; the two boards' action
tables and the wire payload for parity, because the boards share no import;
`Shell.button` directly, including every state where a button must do nothing;
and the whole path end to end through the real pad, encoder, frame, parser,
acknowledgement tracker, shell, and editor — a session navigated entirely by
button, with the keyboard used only to type, asserting that the text is exactly
what was typed and that the acknowledgement path was unaffected.

`test_shell.py` asserts the absence of the save state and screen rather than only
the new destination, because a leftover state is what a future change would
quietly route back into, and asserts that leaving the editor costs exactly one
visible change — which is what the writer experiences.

The suite is 1,103 tests, up from 1,056, and green. `compileall`,
`tools/validate_uart_harness.py`, and the CircuitPython compatibility sweep pass;
the deterministic harness CRC-32s are unchanged, because nothing in the proven
transport moved.

### Physical bench check — the smallest one that settles it

Not a certification harness. The ordinary development runtime, per
`docs/DEVELOPMENT_RUNTIME.md`, MagTag first.

1. type in the editor;
2. press Escape: it saves and returns directly to the menu, with no screen in
   between and no second keypress;
3. move through the menu with the MagTag buttons;
4. open a mode with a MagTag button;
5. return to the menu with a MagTag button;
6. confirm no text is lost.

Record the outcome here and in `PRIORITY.md` whichever way it goes.

### Physical verification — 2026-07-30, commit `b176e5d` — PASSED

Ran on the bench from the deployed build, which was byte-compared against the
repository first: `dev_runtime.py`, `code.py`, `magwrite_transport/`,
`dev_display_runtime.py`, and `magtag/magwrite/` all matched, and the two
`config.py` files differed only in the enable flags each board is meant to carry.

Evidence: `docs/FRUITJAM_V15_BENCH_SERIAL.jsonl` and
`docs/MAGTAG_V15_BENCH_SERIAL.jsonl`, both captured read-only from before the
first reset. Both boards needed the **reset button**, as predicted; the MagTag
went first.

Bring-up:

```json
{"event":"dev_display_buttons_ready","actions":["MENU","UP","DOWN","SELECT"],"aliases":["BUTTON_A","BUTTON_B","BUTTON_C","BUTTON_D"]}
{"event":"dev_display_ready","buttons":true,"button_detail":null}
{"event":"dev_runtime_ready","storage_status":"MOUNTED","shell_state":"EDITOR","buttons":"MAGTAG_MENU_UP_DOWN_SELECT","stop_from":"MAIN_MENU"}
```

The V1.4 Quick Note was recovered and the shell opened straight into it —
`live_document_restored`, 68 characters, 41 lines, revision 332 — so the run
began on a real document with real prior work in it, which is the harder case.

All six checks passed, with **zero faults**:

1. **Typed.** 17 characters accepted, `events_processed: 17`, autosaved at
   `document_journaled` revision 349, 85 characters.
2. **Escape saved silently and landed on the menu in one gesture.** One
   checkpoint, one transition, and nothing in between:

   ```json
   {"event":"document_checkpointed","revision":349,"characters":85,"save_state":"SAVED"}
   {"event":"shell_left_editor","save_action":"CHECKPOINTED","save_state":"SAVED"}
   {"event":"shell_transition","from":"EDITOR","to":"MAIN_MENU","reason":"left the editor"}
   ```

   No `SAVE_STATUS` state, no save screen on the panel, and no second keypress.
   `save_failures: 0` and `editor_exit_save_failures: 0` for the session.
3. **The buttons moved the menu.** Up to `JOURNAL`, down to `QUICK NOTE`, then
   down twice to `DRAFTS` and `RECENT`, one `shell_selection_moved` per press.
4. **A button opened a mode.** `SELECT` entered `RECENT` and reopened `NOTE 1`.
5. **A button returned to the menu**, checkpointing on the way out at 85
   characters — again silently.
6. **No text was lost.** `final_document_text` ends `line forty onev 12 button
   check`, the typed line intact at the cursor it was typed at, after leaving the
   editor and reopening it.

The button path was exact end to end. The MagTag counted 9 presses and sent 9
frames with `button_bounces_rejected: 0`, `button_repeats_suppressed: 0`, and
`button_frames_dropped: 0`; the Fruit Jam received 9, accepted 9, and applied 9,
with `button_events_duplicate: 0`, `_dropped: 0`, and `_unknown: 0`. Not one
duplicate at any of the three suppression points.

**No button reached the document.** The three presses made inside the editor were
applied `from: EDITOR` `to: EDITOR`, counted as `shell_buttons_ignored: 3`, and
produced no editor event: `events_processed` stayed at the 17 typed characters
and the character count never moved. Button A at the main menu did not end the
session; the session ended on Escape, `result: COMPLETE`.

Neither board was remounted and **no guard was created**: every `.started` file
on both volumes still carries its original pre-run date, and both CIRCUITPY
volumes were confirmed host-writable after the run.

Recorded, not chased:

- the keyboard delivered `v15` to the editor as `v 12` — the `1` and `5` arriving
  as ` 1 2`. This is a further instance of the known **TH40 character
  mis-mapping** already in the backlog (`this` → `tgus`), not a shell defect: the
  editor, the checkpoint, and the recovery all stored and returned exactly what
  the keyboard delivered. The dongle phase is the natural place to learn whether
  it is the keyboard or our HID handling.

## USB dongle keyboard compatibility — STARTED 2026-07-30, BLOCKED ON HARDWARE

`README.md` has named "wireless keyboard with a USB receiver" as a supported
input path since the beginning. This phase set out to test it. It did not get
far, and the reason is worth recording precisely, because the useful result is a
narrow one.

### The receiver that was available was the wrong one

The only 2.4 GHz receiver on the bench is the **EPOMAKER TH40's own dongle**,
`36B0:3002`. That is not a fresh test: attempts 1 and 2 under Priority 3 already
recorded it as enumerating correctly and forwarding no key data, and that section
already concluded "the receiver is not supported and remains out of scope."
`PRIORITY.md` claimed the dongle path was untested; that was wrong, and it is
corrected here.

Attempt 3 was run anyway, because the earlier attempts pre-date the shell, the
adaptive pacing, the layout seam, and the current diagnostics, and because a
failure worth trusting should be reproducible on demand.

### Attempt 3 — 2026-07-30 — FAIL, and the same failure

Evidence: `docs/FRUITJAM_DONGLE_PROBE_SERIAL.jsonl` and
`docs/MAGTAG_DONGLE_SERIAL.jsonl`. Nothing was changed to run it: both
boards kept the V1.5 configuration and the V1.5 build, no guard was claimed, and
no file was written to either board.

Across **three boots**, every one of them identical:

```json
{"event":"usb_keyboard_state","from":"ENUMERATING","to":"READY","open_attempts":1}
{"event":"usb_keyboard_connected","product":"Wireless 2.4G Dongle","vendor_id":"36B0","product_id":"3002","protocol":"boot_keyboard","interface":0,"endpoint":129,"hid_interfaces":3,"serial_number":"19971217"}
{"event":"usb_keyboard_layout_selected","selection":"AUTO","layout":"STANDARD"}
```

- it **enumerates**, on the first open attempt, every time;
- it **stays connected** — no disconnect, no re-enumeration, no flapping for the
  life of a session;
- it sends **zero HID reports**, across four deliberate typing windows inside
  live sessions, one of them typed while the session was confirmed live to the
  second;
- nothing reached the serial console either, so CircuitPython's built-in host
  keyboard driver is not quietly taking the keystrokes to stdin.

The `AUTO` layout seam behaved exactly as designed: `36B0:3002` is not the wired
TH40's `36B0:304E`, so it received `STANDARD` HID rather than a remap built for a
different device.

**Two controls make the negative narrow.**

1. *The keyboard and receiver are fine.* Moved to the host PC, the same pair
   types normally. So this is not pairing, not the keyboard's mode switch, and
   not a flat battery.
2. *The Fruit Jam is fine.* With the **wired** TH40 cable in the same host port,
   the same build, and the same session: `hid_report_received: 22`,
   `live_event_processed: 11`, characters into the document, and the V1.5 note
   recovered intact at 85 characters and revision 350. So the host port delivers
   HID, our adapter reads it, and nothing about the V1.5 build regressed.

**Recorded as: the TH40 receiver is incompatible with the Fruit Jam host port.**
Per the operator's instruction, no further time goes to this receiver.

### What is still unknown, and deliberately so

**Whether USB power is the cause was not settled.** The powered-hub test — the
experiment that would separate "the port cannot run a 2.4 GHz radio" from "this
receiver is simply incompatible" — was proposed and **declined** on practical
grounds, so `HARDWARE.md`'s current-supply question stays open exactly as it was.
The wired control does *not* answer it: a wired keyboard and a receiver's radio
are not comparable loads.

That matters for sequencing rather than for this phase. If power is the cause,
the phase that fixes it is **one-cable bench power**, which is already next in
the order, and the dongle question is worth re-asking after it rather than before.

### Blocked, and on what

**No second wireless keyboard or receiver is available on the bench.** The next
step this phase needs is one *ordinary* wireless keyboard receiver — any vendor,
not this keyboard's own — to answer the only question that still matters: whether
the wireless path works at all, or is specific to this dongle. Nothing in the
repository can answer that, and no amount of further work on `36B0:3002` will.

Until then the phase is **blocked on hardware**, not on software. Nothing here
asks for a code change: the adapter, the `AUTO` seam, the state machine, and the
diagnostics all did their jobs, and the one thing they could not do was invent a
device that sends reports.

## One-cable bench power — PHYSICALLY VERIFIED 2026-07-30

**One USB-C cable was connected and the complete device started by itself.** That
was the phase's whole goal stated as a sentence, and it is now a thing that
happened twice, on hardware, with no reset pressed and no start order used.
Evidence `docs/BENCH_ONECABLE_FRUITJAM_SERIAL.jsonl`; the check and its full
result are `docs/BENCH_POWER_CHECK.md`.

Both cold boots produced the same numbers: **four handshake attempts, a 9.05 s
wait**, the document recovered, the keyboard claimed, and a full refresh
completed — 3586 ms and 3525 ms, the largest current step of a run, taken twice
with no brownout. The second boot recovered exactly the 107 characters a MagTag
button had checkpointed before power was pulled, so the loop closes: written,
made durable by a button press, power removed, recovered by a rig that was told
nothing.

Across both sessions: 26 viewports sent and 26 displayed; 24 partial refreshes at
845–966 ms, mean 924 ms, in line with every previous bench run; 23 button presses
and 23 applied. Zero handshake restarts, `ERROR` results, `duplicate or reversed
input sequence`, display errors, rejected events, queue overflows, keyboard
disconnects, CRC failures, resynchronisation events, or storage faults. Nothing
warm to the touch and the panel clean, both reported by the operator, because a
log cannot say either.

The wait is the number worth reading twice. **The first three handshakes of each
boot went to a board that was not listening** — at 3.00 s, 6.01 s, and 9.01 s,
each logging the document it was holding — and the fourth was answered. On the
code this replaced, both boots would have ended in `status_hello timeout` and
`result: ERROR` at five seconds.

Not measured, and not claimed: a single current figure. There is still no USB
power meter on the bench, so "no brownout with two boards, a hub, a keyboard, and
a panel through one connector" is an observation, not an amperage, and
`HARDWARE.md`'s measurement item stays open.

### The audit that came first — direct 5 V feed refused

The goal was one USB-C connection powering both boards with the wired UART and
normal operation preserved. The audit came first and is in
[docs/BENCH_POWER.md](docs/BENCH_POWER.md), with Adafruit's documentation cited
inline. It changed the shape of the phase before a single wire was cut.

### The direct 5 V arrangement does not exist on this hardware

The phase was framed as a question of *direction* — which board takes USB-C and
which is fed from the other's 5 V rail. That question has no answer here, and the
reason is not a margin or a preference:

- the **MagTag has no 5 V input**. Its pinout states its power inputs
  exhaustively as the USB-C connector or a 3.7/4.2 V LiPo on the JST 2-PH port.
  The only 5 V node it exposes is VCC on the two 3-pin STEMMA connectors —
  documented as an **output**, rated 200 mA for the connector;
- the **Fruit Jam's 5V header pin is a regulator output**, ~500 mA peak. Feeding
  a regulator output is not a supply path either.

So both boards have exactly one documented 5 V input each, and on both boards it
is the USB-C connector. There was no direction left to choose.

Driving the MagTag's STEMMA VCC anyway would push current backwards into its
USB-C VBUS pin and its charger input, through a connector rated as a 200 mA
output, and would tie the two boards' 5 V rails into one node with no documented
OR-ing between the sources that could then meet there. Refused, and documented
rather than improvised around, exactly as the phase instructions required.

### What the audit found that was worth finding anyway

**Both boards' 3-pin JST connectors carry 5 V on the red conductor by default.**
The UART link runs between two of those connectors. A stock, unmodified 3-wire
STEMMA cable between Fruit Jam `A0` and MagTag `D10` therefore connects the two
5 V rails on its own — no intent, no extra part, no warning. The standing "leave
red disconnected and insulated" rule has been correct since the first UART test;
until now it did not say *why*, and the why is a specific cable that would look
right and be wrong. `HARDWARE.md` now carries the reason next to the rule.

### The arrangement that is supported

**Corrected the same day, and the correction is smaller than what it replaced.**
The audit recommended a powered hub with one USB-C cable into each board. The
arrangement actually adopted is one supply into the **Fruit Jam's USB-C**, with
the MagTag fed from a **Fruit Jam USB-A host port** through an ordinary
USB-A-to-USB-C cable, and the keyboard on the other host port.

That is still a documented output into a documented input — a USB host powering
a USB device, which is the one thing USB power is unambiguously for — so nothing
in the refusal above is softened by it. The refused arrangement was a wire from a
**5 V header pin** into a node documented as an output. This is a port doing its
job. Each board keeps its documented USB-C input, switch, protection, and
regulator; **both boards are sinks**; the UART is untouched; ground was already
common through it.

It costs the MagTag's console and its host-visible `CIRCUITPY` while the rig is
wired this way, which is a real loss and is not worked around: to deploy to the
MagTag, move its cable to the PC and move it back. Moving the one cable between
the PC and a wall charger is the entire difference between the development and
standalone configurations. No file on either board changes.

The hub arrangement remains valid and is the fallback when both consoles are
needed at once.

### The consequence that had to be answered in software

**The Fruit Jam's USB-A ports carry no 5 V while the Fruit Jam is held in
reset.** So the MagTag, which is now powered from one of them, cannot be booted
first — and "restart the MagTag first, wait for `dev_display_ready`, then the
Fruit Jam" became an instruction the hardware cannot obey. Both boards
necessarily cold boot together, and the Fruit Jam wins that race almost every
time: it has no e-paper panel to initialise, and the MagTag spends seconds inside
`display.initialize()` before it reads a byte.

Until now a HELLO that went unanswered for five seconds ended the session with
`status_hello timeout` and `result: ERROR`. Under one cable that is a device that
does not switch on. So the handshake waits instead:

- **it retries indefinitely**, every `DISPLAY_HANDSHAKE_RETRY_SECONDS` (3.0),
  logging `live_waiting_for_display` with the attempt, the elapsed wait, and the
  number of characters of document it is holding. `live_typing_started` then
  reports `hello_attempts` and `display_wait_seconds`;
- **the frame sequence never restarts.** Each attempt takes the next number, so a
  MagTag that boots halfway through hears a monotonic stream. Restarting the
  count per attempt is precisely what would produce `duplicate or reversed input
  sequence` on the far board;
- **the status channel is re-baselined each attempt**, so a MagTag that boots
  late and numbers its first reply 1 is heard rather than counted stale and
  dropped — which would have made the wait futile however long it ran;
- **a fault during the handshake restarts the handshake** with a fresh parser
  rather than ending the session, logged as `live_display_handshake_restarted`
  and counted as `display_handshake_restarts`;
- **the MagTag lets a `HELLO` re-baseline its input numbering**, but only while it
  has displayed nothing — nothing accepted, pending, in flight, or about to
  start. Once the writer's words are moving, sequence discipline is absolute
  again;
- **nothing touches the document.** A restored document is loaded before the
  session runs and is not read, re-derived, or re-saved by any of this. The
  session and idle clocks start when the panel answers, so a slow display does
  not spend the writing session's budget.

This also retires a backlog item recorded three times — after the V1.3, V1.4, and
dongle bench runs — as transport hardening worth doing later. It stopped being
deferrable the moment the hardware stopped allowing its workaround.

Host-verified in `host-tests/test_display_wait.py`: the Fruit Jam starts first,
the first attempts go nowhere, the panel arrives well after the old timeout would
have fired, the handshake completes, the restored document comes through the wait
byte-for-byte, and no sequence failure is latched on either board. Both boards'
rules are asserted from their own code, not from a model of it.

Estimated combined budget: ~450 mA typical, ~900 mA worst case. With everything
drawing through the Fruit Jam's one USB-C connector, **≥1.5 A** is the figure to
supply rather than the optimistic one. **No figure was measured on this bench.** The MagTag's
~50 mA active figure is Adafruit's; the Fruit Jam's is an estimate, because none
is published. The measurement checklist item stays open and a USB power meter on
the upstream cable is what closes it.

### What this phase deliberately does not claim

It does not answer the receiver question. A supply with more headroom than a
laptop port makes `36B0:3002` worth re-asking about, which is why the phases were
ordered this way — but the receiver hangs off the Fruit Jam's **own host port**,
behind `USB_HOST_5V_POWER` and the CH334F hub, and that path's limit is unchanged
by anything upstream of the board. The dongle phase remains blocked on an
ordinary second receiver.

It introduces no boost converter. The MT3608 belongs to Priority 6.

It makes no thermal claim. "Nothing warm to the touch" is a hand, not a
thermocouple, and it is recorded as exactly that.

It is not a soak test. Two cold boots and a few minutes of writing each is what
this check is; long-duration behaviour belongs to Priority 7.

## V1.6 — Minimum standalone workflow — PHYSICALLY VERIFIED

The design is [docs/STANDALONE.md](docs/STANDALONE.md) and the physical check is
[docs/STANDALONE_CHECK.md](docs/STANDALONE_CHECK.md), which **passed on
2026-07-30, every step, with no faults observed**.

### Original requirements

- new document;
- open recent document;
- save;
- rename or archive;
- word count;
- storage, keyboard, display, and save indicators;
- keyboard shortcuts plus MagTag button actions;
- predictable startup, sleep, wake, and shutdown behavior.

**Exit:** complete a 30-minute writing session without a connected development computer.

### What the phase turned out to be about

Almost everything on that list already existed. New document, open recent, save,
word count, the save and storage indicators, the keyboard shortcuts, and the
button actions were all delivered by V1.2 through V1.5 and all physically
verified. Read literally, V1.6 was a short phase.

Read as its exit criterion — *without a connected development computer* — it was
not, because **every one of those features had been verified on a bench rig with
two consoles attached**, and several of them depended on that in ways nobody had
had reason to notice. The phase's real content was finding those dependencies.
Each was a device that does not work, and none of them was a failing test.

1. **Neither board started.** Both configs shipped with everything disabled, on
   the fail-closed rule that anything which can drive hardware must be armed by
   name. Correct for a harness and wrong for a finished device: the shipped
   configuration was a board that refuses to run. It is now the appliance, and
   the fail-closed property is kept where it still means something — every
   guarded harness still ships disabled, still needs its own mode string, and
   still wins over the default when armed.
2. **A board switched on before its keyboard was plugged in never saw that
   keyboard.** `UsbDeviceState` allowed thirty open attempts at one per second
   and then latched `ERROR`, permanently, for the life of the session. On a bench
   the keyboard is always already there. On an appliance, the writer connects
   power and then goes looking for the cable, and thirty seconds later the device
   has decided there is no keyboard and will never look again. The attempt
   *count* is removed for the standalone profile. The rate bound is untouched, so
   this is not the unbounded reconnect loop the harnesses refuse — it is one
   bounded USB enumeration per second on a board that has nothing else to do.
3. **The idle timeout ended the session after half an hour.** Thirty minutes of
   a writer thinking, or reading, or being interrupted, and the session raised
   `live session idle timeout`, drained, and stopped — leaving a panel that
   nothing but the reset button could move. The exit criterion for this very
   phase asks for a 30-minute session, which the shipped bound made a coin flip.

   This one is not an argument from reading the code. **It is in the one-cable
   evidence file.** `docs/BENCH_ONECABLE_FRUITJAM_SERIAL.jsonl` gained three
   further lines after that check was written up, captured at 16:52:41 on
   2026-07-30 while the rig was still connected and nobody was typing at it:

   ```json
   {"event":"dev_runtime_session_summary","result":"ERROR","stop_reason":"live session idle timeout","timeouts":1,"save_state":"SAVED","final_document_characters":107}
   {"event":"dev_runtime_stopped","result":"ERROR","detail":"live session idle timeout"}
   ```

   The verified device switched itself off, on its own, while left alone — and
   ended `result: ERROR` for doing what a writing appliance is supposed to do
   between sentences. The document was `SAVED` and all 107 characters survived,
   so nothing was lost; what was lost was the device. Both run-length bounds, the
   keyboard event bound, and both frame bounds are removed for the appliance.
   Every bound that protects *memory* is unchanged and still enforced.
4. **Escape at the main menu switched the device off.** It had always been the
   clean stop, and on a bench it is exactly right. On a device with one power
   cable it is one keystroke that ends the session and no keystroke that starts
   it again. The MagTag's menu button has never been able to do this — V1.5 made
   it idempotent at the root deliberately, reasoning that a thumb on a bezel did
   not mean it. That reasoning was always about the *device*, not about the
   bezel; V1.6 finishes it, and the keyboard now agrees. Power is the stop.
5. **A stored document the editor refused took the whole runtime down**, during
   construction, before a single line was logged that anybody could read. The
   panel stayed blank and the console said one thing to nobody. Worse is what
   would have happened had it not: the empty editor left behind sits at revision
   0 while the store still holds the writer's real document, and the first
   checkpoint due on age would have written the empty one over it. Startup
   trouble must never cost somebody their work, so writes are now **held** for
   the session, the card is not touched at all, and the shell opens at the menu
   with the reason on the recoverable error screen. Opening any document from
   Drafts releases the hold.
6. **Typing into a device that was still booting ended the session.** Keystrokes
   are polled during the display wait but not drained — there is nowhere to show
   them — so the 64-event queue holds about 32 and the next one overflowed it,
   fatally. V1.1 recorded this as a limitation and it was one; one-cable power
   made it likely, because the writer now connects a cable and waits nine seconds
   at a blank panel, and some of them will start typing. The overflow is dropped
   and counted rather than fatal, and everything already queued is still applied
   the moment the panel answers.

### The panel had nothing to say, and now says it

A device with no console can only speak on its screen, and for the first several
seconds of a standalone start the screen belongs to the board that is not
talking yet. The MagTag therefore draws two screens of its own — `STARTING` as
soon as the panel is initialised, and `WAITING FOR THE WRITER BOARD` if nothing
has arrived after 15 s.

This is the narrowest exception the architecture allows and it is worth stating
exactly. Those screens carry no document, no cursor, no revision, and no state
the Fruit Jam owns; their revision is 0, which the protocol already reads as
"nothing has been displayed"; they are never acknowledged to anybody; and they
are never drawn again once a viewport has arrived. The MagTag is still
display-only. It is simply allowed to say that it is alive.

Fifteen seconds because the one-cable check measured a 9.05 s cold boot, twice.
An ordinary start never draws the second screen, which is what makes seeing it
informative rather than routine.

The display is now constructed **before** the UART, and that reordering is the
whole of why a wiring fault is visible: a bad pin alias used to be one JSON line
on a console that, in this configuration, does not exist. It now reaches the
panel, with `DISCONNECT POWER, RETRY` under it.

On the Fruit Jam, an absent keyboard puts `NO KEYBOARD - PLUG ONE IN` on the
main menu's spare fifth row — the four items are never displaced — and a `k` in
the status field of every frame, beside the save indicator and on identical
terms: one character, lowercase, present in the proven 3x5 glyph table, and drawn
only when the fact is bad.

### The two profiles

One block in `fruitjam/dev_runtime.py` decides six values, and nothing else in
either runtime knows which profile it is in. The appliance is not a reduced build
of the bench rig; it is the same editor, shell, storage, transport, and buttons.

| | Development | Standalone |
| --- | --- | --- |
| Idle / session timeout | 1800 s / 7200 s | none |
| Keyboard event bound | 100,000 | none |
| Viewport / protocol frames | 100,000 / 200,000 | none |
| Back at the main menu | the clean stop | nothing |

The entry points keep their names and their diagnostics. `dev_runtime_ready`,
`dev_display_ready`, and the rest are the vocabulary every physical evidence file
in this repository is written in, and renaming them would make the record harder
to read in exchange for a tidier filename. Each now carries `"profile"`.

### Coverage

1,185 host tests, 49 of them new in `host-tests/test_standalone.py`, written
against the six failures above rather than against the code that fixes them: a
keyboard plugged in after 120 s of looking; the same adapter with the old bounded
budget, asserted to miss it; a clock jumped a day forward with no timeout firing;
five Escapes at the menu leaving the session running and the words intact; a
refused restore asserted **byte-for-byte** against the card, with the empty
editor's checkpoint and manual save both refused; a paragraph typed into a device
whose panel is not powered for nine seconds. The MagTag's startup screens are
encoded, decoded, and drawn through the real renderer, including a fault screen
built from an exception message containing characters the panel has no glyph for.

### What is not delivered, and is named rather than hidden

- **rename and archive**, from the original list. A storage feature rather than a
  standalone one; the append-only catalogue supports both as a single append
  whenever a phase wants them;
- **dated journal entries**, unchanged from V1.4: there is no RTC and no network,
  and a date derived from `time.monotonic` is a fabricated date printed next to
  somebody's own words;
- **sleep, wake, and shutdown.** There is no sleep state and no shutdown
  sequence. The device is on while it has power and off when it is not, and every
  editor exit checkpoints, so removing power is safe at any moment. Predictable
  startup was the part of that item this phase owed; power management belongs to
  V1.8, where there is something to manage;
- **the 30-minute *writing* session.** The physical run sat idle past the 1800 s
  bound V1.6 removed and was still live afterwards, so the device is confirmed
  not to stop itself. That is not thirty minutes of sustained writing, and
  nothing here claims it is.

### Physical verification — 2026-07-30 — PASSED

`docs/STANDALONE_CHECK.md` was run on the shipped configuration of both boards,
from one USB-C cable into a charger, with neither board connected to the PC. All
steps passed and no faults were observed.

The two failures the phase was really about were both confirmed fixed on
hardware: **a keyboard connected after startup became usable with no reboot**,
and **the device left idle past the removed timeout did not switch itself off**.
Both boards started automatically from one cable with no reset and no start
order, the previous document and mode recovered, the buttons drove the menu,
Escape saved silently and returned straight to it, and a power cycle brought the
same document back.

Before the run both boards were still carrying V1.5 and were still **hand-armed
for their development runtimes**; each was deployed to V1.6 and verified
file-by-file (42 and 40 `.py` files, zero hash mismatches) with the harness
arming cleared to the shipped defaults.

**This result carries no evidence file, and the reason is the check's design.**
Every phase from V1.2 to V1.5 is backed by a `.jsonl` serial capture. This check
removes both consoles, because a console attached to either board would mean the
configuration under test was not the shipped one — so the panel is the only
instrument and the operator's observation is the only record. No timing, refresh
count, or character total is claimed, because nothing measured any. That is a
weaker form of evidence than the earlier phases carry and the correct form for
this one.

## V1.7 — MagTag font and button footer — HOST-VERIFIED, PHYSICAL CHECK OUTSTANDING

Two changes to what the writer looks at, and none to what the device does. The
editor, shell, persistence, UART, keyboard, and standalone behaviour are all
unchanged; every one of their host tests passes untouched except where a test
asserted a panel dimension as a literal.

### 1. The panel draws with CircuitPython's built-in font

`terminalio.FONT` — Terminus, a 6×12 monospace cell — at **native scale 1**,
everywhere: editor text, menus, titles, the startup and waiting screens, status,
error text, and the footer. One path, `magtag/magwrite/font.py`.

It replaced a 3×5 bitmap table maintained by hand in
`magtag/magwrite/test_pattern.py`. That table worked. It also meant that every
apostrophe, semicolon, and the whole lowercase alphabet arrived as a separate act
of type design; that a character with no entry raised `KeyError` on the first
frame that carried it, which is a fault that reaches the writer as a dead panel;
and that the sanitizers on **both** boards existed largely to prevent that. The
built-in font ships with the firmware, covers printable ASCII and beyond, and
costs no flash and no maintenance.

**Scale 1 is not a compromise.** The built-in font's 6 px advance is exactly what
the old table drew at scale 2, so the apparent size is the size the bench already
read comfortably — two pixels taller, with real letterforms instead of a 3×5
approximation of them. No larger integer scale fits a usable number of rows on a
128 px panel. Non-integer scaling and simulated bold are both refused: this is a
1-bit panel with no antialiasing, and both produce mush.

**The alphabet widened, and that is a visible change.** `SAFE_CHARACTERS` on both
boards is now printable ASCII rather than a hand-written subset, so `@ # $ % ^ &
* _ + = [ ] { } \ | ~` and the backtick are drawn instead of being replaced with
a space. A wider alphabet is not a complete one — an accented letter in an
exception message still has no glyph, is still replaced, and the renderer still
**refuses** a character it cannot draw rather than leaving a hole in a word.

**The 3×5 table is kept, not deleted.** The one-shot hardware harnesses that
produced this project's physical evidence still draw with it. Re-rendering a
proven harness to match a later font would change what those runs measured.
Nothing the writer sees comes from it any more.

### The layout is derived, not declared

The brief asked for the arbitrary five-row layout to be recomputed from the real
font metrics rather than preserved, and that is literally what the code does:
`viewport_renderer.geometry()` asks the font for its own bounding box and derives
the row pitch, the row count, and the column count from it. Nothing in the layout
is a written-down number. With the 6×12 built-in font:

| Band | y | Height |
| --- | --- | --- |
| Title and right-aligned status | 2 | 12 |
| Header rule | 16 | 1 |
| Body rows 0–5, 14 px pitch | 19 | 6 × 12 |
| Cursor underline | row + 12 | 2 |
| Footer rule | 112 | 1 |
| Button footer | 115 | 12 |

**48 columns by 6 rows**, against 28 by 5 — roughly double the visible text at
the same apparent size, because the panel's width is finally used. The cursor
underline lives in the 2 px leading between rows, so it costs no height and
cannot overlap the row below. The last body row ends at y=102, ten pixels clear
of the footer rule; a host test asserts that one more row, and one more column,
would not fit.

That capacity is the one number the two boards must agree on, and they share no
import by design. The Fruit Jam wraps to `editor_layout.VIEWPORT_COLUMNS` and
`VIEWPORT_ROWS`; the MagTag derives it; a host test asserts those constants, the
viewport message bounds, and the shell screen bounds all against the derivation.
It is the same argument the button action tables get, for the same reason.

**The protocol bound moved, and only widened.** Six rows of 48 is a 340-byte
worst-case viewport, so `MAX_PAYLOAD_SIZE` went 192 → 384 and the parser
accumulator 512 → 1024, with the MagTag's UART receive buffer 256 → 512 to stay
above one whole frame. The frame format, CRC, sequence discipline, and framing
rules are untouched, and a widened bound accepts every frame the narrower one
did — so nothing already proven on the wire is invalidated.

### 2. A persistent button footer

A strip directly above the four bezel buttons, on **every** screen — editor,
menu, drafts, startup, waiting, status, and error — reading `MENU`, ▲, ▼,
`SELECT`, each centred on the quarter-centre of the panel its button sits under.
The mapping is unchanged (A `MENU`, B `UP`, C `DOWN`, D `SELECT`) and so is every
button's behaviour. What changed is that the panel now says what they are; until
V1.7 the only place that mapping was written down was a table in `HARDWARE.md`,
which is no use to someone who has just picked the device up.

**It knows nothing**, and that is deliberate. Four fixed labels for the four
fixed normalized actions this board already sends. It does not know the shell
state, whether an action is available, or what it will do — the Fruit Jam owns
all of that — so the footer can never disagree with the shell. It is drawn
locally rather than sent as viewport lines: a label the Fruit Jam transmitted on
every frame would be payload spent repeating itself forever, and a second place
for the two boards to disagree about the bezel.

Because it carries no state it is **identical on every screen**, which is what
lets a partial refresh leave it alone; a host test asserts that identity pixel
for pixel across seven screens, including one filled to the last row and column.

**The arrows are drawn, not set.** Filled triangles from display primitives, nine
pixels across. The built-in font has no arrow glyph in the printable-ASCII range
both boards restrict themselves to, and `^` and `v` are a caret and a letter —
readable as arrows only by someone who has already been told they are arrows.

### Coverage

1,226 host tests pass, 41 of them new in `host-tests/test_panel_layout.py`, plus
`compileall`, the UART validator, the CircuitPython compatibility sweep, and
`git diff --check`. The new tests cover the font resolution rule, the derived
geometry including the two "one more would not fit" bounds, the cross-board
capacity agreement, the bounded glyph cache, and the footer on every screen.

The renderer's cost was measured on the host before and after, because a panel
that is 2.4× more text is 2.4× more pixel work on an ESP32-S2: the naive glyph
blit was 4.3× the old table's, and caching each glyph's rows as integer bitmasks
brought the worst case back to 2× for twice the characters. The cache is bounded
by the alphabet, because every character outside it raises before it is cached.

### What is not claimed

Everything physical. Whether scale 1 is comfortable to read at arm's length,
whether the labels sit over the right buttons, whether the arrows read as arrows
on e-paper, and whether a partial refresh leaves the footer clean are all
questions only the device answers. The panel's left-to-right order being the
bezel's is the one that has a cheap fix if it is wrong:
`button_footer.FOOTER_ACTIONS` is a single line to reverse.

Battery work is paused until this is verified on hardware.

## Priority 6 — Unified single-battery power — V1.8

Replace separate bench USB power with one internal battery and one charging input.

Requirements:

- one protected single-cell battery;
- one charger with power-path/load-sharing support;
- one system power switch;
- regulated supply appropriate to the Fruit Jam and MagTag;
- no parallel charger circuits on one battery;
- measured peak, active, idle, sleep, and refresh current;
- brownout margin;
- battery-level reporting and low-battery behavior;
- safe charging while the device is operating.

**Exit:** both boards, keyboard receiver where applicable, storage, and display run reliably from one rechargeable battery through one external charging port.

## Priority 7 — Enclosure and product hardening — V1.9

- enclosure and internal mounting;
- cable strain relief and serviceability;
- readable font/layout refinement;
- long-duration editor, storage, UART, and keyboard soak tests;
- 500/1,000 partial-refresh and wear characterization;
- production full-refresh cadence;
- recovery from resets and corrupted final writes;
- storage-space safeguards;
- low-battery shutdown;
- recent-document browser refinement;
- optional export or backup over Wi-Fi.

## Deferred fallback — LOLIN32 Bluetooth keyboard bridge

Revisit the LOLIN32 Lite only when a required keyboard is Bluetooth-only and direct USB HID is not viable.

Possible scope if activated later:

- BLE and/or Bluetooth Classic HID host;
- pairing, bonding, reconnect, and bond reset;
- normalized key-event transport into the existing Fruit Jam `InputAdapter`;
- bounded buffering and overflow reporting.

The LOLIN32 must not own document state and must not require changes to the editor, viewport, storage, or MagTag display architecture.

## Future options

- larger monochrome partial-refresh display;
- integrated keyboard or clamshell enclosure;
- consolidated custom PCB;
- optional BYOK-style capture commands such as `::note` and `::task`;
- Bluetooth-only keyboard support if product requirements justify the additional bridge.