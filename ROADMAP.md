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
- future microSD persistence
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
| 1 | Responsiveness and keyboard completeness | V1.1 | Host-verified; physical run pending |
| 2 | microSD persistence and forced-power-loss recovery | Priority 4 | Not started |
| 3 | MagWrite Shell | V1.3 | Not started |
| 4 | Journal, Quick Note, Drafts, and Recent | V1.4 | Not started |
| 5 | Standalone workflow | Priority 5 | Not started |
| 6 | Optional MagTag buttons | Priority 2 | Not started, optional |
| 7 | Battery, enclosure, and hardening | Priorities 6 and 7 | Not started |

Writing must feel right before anything is stored, and storage must be
trustworthy before a shell is built on top of it. MagTag buttons moved down and
became optional because the USB keyboard already provides every control the
writing loop needs; they are a convenience, not a dependency.

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

## Priority 2 — MagTag button controls over UART — V1.6, OPTIONAL

Deferred to **V1 position 6 and marked optional.** The USB keyboard already
supplies every control the writing loop needs, so buttons are a convenience.
Nothing later in V1 depends on them.

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

**Exit:** every physical button event reaches the Fruit Jam exactly once, produces the intended Fruit Jam-owned action, and does not interfere with display acknowledgements.

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
Caps Lock, and repeat for Backspace, Delete, arrows and printable characters —
with cancellation on release — are all covered end to end by host tests that
assert the resulting document.

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

**Exit:** a physical run on the two boards confirming the display keeps up with
live typing and that each listed key behaves as the host tests predict.

## Priority 4 — Single-document persistence and recovery — V1.2

Add microSD-backed storage on the Fruit Jam.

Requirements:

- one active plain-text or Markdown document;
- create/open the latest draft;
- crash-safe autosave;
- append-only recovery journal;
- atomic or recoverable checkpoints;
- tolerate a truncated final recovery record;
- manual save and visible save state;
- restore the last valid document after forced power loss.

Do not begin with a full document browser. Prove one document and reliable recovery first.

**Exit:** a writing session survives forced power loss with the final acknowledged edit recovered.

## V1.3 — MagWrite Shell

The application shell the writing modes live in. It comes after persistence
because a shell that cannot reliably open and save a document is a menu, not a
product.

Requirements:

- one owner of application state on the Fruit Jam, distinct from the editor;
- explicit modes with defined entry, exit, and back behaviour;
- a viewport the shell can draw that reuses the proven renderer and pacing;
- keyboard-driven navigation with no dependency on MagTag buttons;
- bounded, fail-closed transitions with no unsaved-work loss on any path.

**Exit:** the writer can move between the shell and a document repeatedly
without losing state or stalling the display.

## V1.4 — Journal, Quick Note, Drafts, and Recent

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

## Priority 5 — Minimum standalone workflow — V1.5

Add the smallest complete on-device workflow:

- new document;
- open recent document;
- save;
- rename or archive;
- word count;
- storage, keyboard, display, and save indicators;
- keyboard shortcuts plus MagTag button actions;
- predictable startup, sleep, wake, and shutdown behavior.

**Exit:** complete a 30-minute writing session without a connected development computer.

## Priority 6 — Unified single-battery power — V1.7

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

## Priority 7 — Enclosure and product hardening — V1.7

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