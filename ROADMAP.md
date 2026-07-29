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

## Priority 2 — MagTag button controls over UART

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

## Priority 3 — Direct USB HID keyboard on Fruit Jam — IMPLEMENTED, PHYSICALLY UNVERIFIED

Implemented at commit `ab52961`. Host suite raised from 253 to 456 tests, all
passing. **Two guarded physical attempts on 2026-07-29 both failed, neither on a
software defect.** Evidence: `docs/FRUITJAM_USB_KEYBOARD_TEST.md`.

Verified on real hardware:

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

**Not verified, because zero keystrokes were ever captured:** normalized real-key
events, Shift, Caps Lock, punctuation, repeat, live multiline typing, input
during refresh, viewport coalescing from real input, final revision/hash
reconciliation, and lowercase glyph legibility.

Blocking issue: the wireless keyboard stopped delivering any HID data to its
receiver while that receiver was in the Fruit Jam host port, despite the same
keyboard and receiver having delivered real usages to that same port earlier the
same day, and typing correctly on a PC afterwards. Three independent checks
confirmed no data reached either the adapter or CircuitPython's own console.
Candidate causes — marginal host-port supply to the receiver's radio, or a lost
pairing session — remain open and untested. A different keyboard, preferably a
wired one, is the cheapest next diagnostic.

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

## Priority 4 — Single-document persistence and recovery

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

## Priority 5 — Minimum standalone workflow

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

## Priority 6 — Unified single-battery power

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

## Priority 7 — Enclosure and product hardening

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