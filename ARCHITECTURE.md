# MagWrite Architecture

## System overview

```text
USB HID keyboard
        |
        v
Adafruit Fruit Jam
        +-- authoritative multiline editor
        +-- cursor, wrapping, and viewport state
        +-- future microSD document and recovery storage
        +-- keyboard input normalization
        +-- MagTag button-event interpretation
        |
        | bidirectional 3.3 V UART
        v
Original Adafruit MagTag
        +-- e-paper rendering and refresh scheduling
        +-- frame acceptance and display acknowledgements
        +-- four-button event capture
```

The Fruit Jam is the authoritative application controller. The MagTag is a display terminal and input surface, not a second editor.

Direct USB HID on the Fruit Jam is the preferred keyboard path. The LOLIN32 Bluetooth bridge is deferred and remains an optional adapter only for a Bluetooth-only keyboard that cannot use USB or a receiver.

## Proven transport boundary

The Fruit Jam and MagTag communicate through a versioned, bounded, CRC-protected binary protocol over UART.

```text
Fruit Jam board.A0 TX  ---> MagTag board.D10 RX
Fruit Jam board.A1 RX  <--- MagTag board.A1 TX
Fruit Jam GND          <--> MagTag GND
```

The physical bidirectional gate passed on 2026-07-28 at 115200 baud. The system has physically verified:

- complete semantic viewport transmission;
- bounded parsing and reset-noise resynchronization;
- frame acceptance acknowledgement;
- physical refresh-start acknowledgement;
- physical refresh-completion acknowledgement;
- displayed-revision catch-up;
- final revision and viewport-hash reconciliation;
- stale viewport coalescing without falsely reporting skipped revisions as displayed.

## Current editor boundary

```text
USB HID or deterministic input source
        |
        v
device layout (per-keyboard usage compatibility, standard HID by default)
        |
        v
InputAdapter boundary (normalized InputEvent)
        |
        v
bounded event queue, explicit overflow
        |
        v
Fruit Jam authoritative multiline editor
        +-- document text and line structure
        +-- cursor row/column and preferred visual column
        +-- document_revision
        |
        v
layout and viewport builder
        +-- wrapping and hard wrapping
        +-- vertical scrolling
        +-- viewport_revision
        |
        v
adaptive send pacing (when to transmit; never what)
        |
        v
bidirectional UART transport
        |
        v
MagTag display-only terminal
        +-- frame acceptance
        +-- refresh state
        +-- displayed revision
        +-- bounded errors
```

The MagTag performs no editing, wrapping, scrolling, persistence, or document interpretation. It validates bounded viewport payloads and renders them.

### Keyboard layout compatibility

`hid_keymap` implements HID Usage Page 0x07 as specified and does not bend for
any particular keyboard. Devices that do not follow the specification are
accommodated separately, in `keyboard_layout`, as a named and bounded usage
remap selected from the USB descriptor the backend already reports.

The rules are deliberately narrow:

- an unrecognised keyboard always gets `STANDARD`, which remaps nothing, so the
  default path is unchanged and fail-safe;
- a device only gets a remap if its vendor and product identifiers match a
  recorded entry, and every entry carries the measured evidence behind it;
- remapping applies at translation only. Held keys, press and release tracking,
  and repeat ownership all keep the raw usage the keyboard sent, so a remap can
  never desynchronise a release from its press;
- no layout may redefine a FINISH usage, Caps Lock, or an editing key;
- a misspelled layout name fails closed at construction, not mid-run.

## Responsibility boundaries

### Fruit Jam application

The Fruit Jam owns:

- USB HID keyboard discovery and input normalization;
- normalized semantic input events;
- bounded input-event buffering;
- authoritative document text and line structure;
- editor commands and cursor position;
- wrapping, scrolling, and viewport construction;
- document and viewport revisions;
- acknowledgement tracking and timeout policy;
- future microSD autosave, checkpoints, and recovery;
- document metadata and application workflow;
- interpretation of MagTag button events;
- battery, keyboard, storage, and save-state indicators.

The Fruit Jam does not treat the physical display as authoritative.

### MagTag display terminal

The MagTag owns:

- viewport frame validation;
- latest-frame coalescing;
- framebuffer rendering;
- full and partial refresh scheduling;
- physical busy-state observation;
- displayed revision and display errors;
- local button scanning and debounce;
- normalized button-event transmission.

The MagTag does not independently:

- edit document text;
- move the authoritative cursor;
- decide wrapping or scrolling;
- save or open documents;
- interpret button meaning;
- own application menus or workflow state.

### Optional future Bluetooth adapter

A LOLIN32 bridge may be added later only for Bluetooth-only keyboards.

If used, it owns:

- BLE or Bluetooth Classic keyboard discovery, pairing, and reconnect;
- HID report parsing;
- modifier and repeat state;
- normalized key-event delivery into the existing Fruit Jam `InputAdapter`.

It never owns the document, viewport, storage, or display state.

## MagTag button-event path

```text
MagTag physical button
        |
        v
local debounce and event sequencing
        |
        v
BUTTON_EVENT over return UART
        |
        v
Fruit Jam application mapping
        |
        +-- menu/document action
        +-- page or scroll navigation
        +-- save/status
        +-- confirm/dismiss
        |
        v
new authoritative state and viewport
```

The protocol should support bounded press, release, and deliberate long-press events. Button queue overflow, duplicates, and stale events must be explicit. Display acknowledgements and button events share the return transport without blocking each other.

## Runtime model

### Fruit Jam cooperative loop

1. Drain all currently available keyboard or synthetic input events within a bounded budget.
2. Apply them to the authoritative editor.
3. Drain available MagTag UART status and button-event bytes.
4. Parse complete return frames within a bounded budget.
5. Apply valid button events to Fruit Jam-owned workflow state.
6. Update acknowledgement state.
7. Run autosave/checkpoint work when due.
8. Build only the newest required semantic viewport.
9. Coalesce obsolete unsent viewport states.
10. Send at most one newest pending viewport according to the bounded policy.
11. Check timeouts and emit bounded diagnostics.
12. Yield cooperatively.

### MagTag cooperative loop

1. Drain available Fruit Jam UART bytes.
2. Parse complete viewport frames within a bounded budget.
3. Coalesce pending viewports to the newest valid revision.
4. Poll display busy state.
5. Mark completed physical refreshes and emit acknowledgements.
6. Scan and debounce physical buttons.
7. Queue bounded button events.
8. Start at most one new display refresh.
9. Transmit bounded status and button frames without blocking receive or display polling.
10. Yield cooperatively.

## Display strategy

The experimental UC8151D driver provides one-bit differential no-flash refresh but not true rectangular windowing. The entire framebuffer is transmitted, while unchanged pixels receive no visible drive.

Initial policy:

- first frame: full refresh;
- active typing: coalesced partial refreshes;
- refresh when the display is idle and the visible revision is stale;
- no blinking cursor;
- periodic full refresh according to measured ghosting and wear;
- full refresh on document open and explicit user command;
- preserve OLD/NEW differential state by avoiding panel power-off during an active writing session.

The production full-refresh interval remains configurable and must be based on later wear testing.

### Adaptive send pacing

*When* the Fruit Jam transmits a viewport is decided in one place,
`fruitjam/magwrite_transport/pacing.py`. It is the single home for every display
timing constant, so no two code paths can disagree about a send interval. It
decides only *when*; coalescing to the newest state, revision numbering,
hashing, acknowledgement, and the fail-closed ceilings stay where they are.

Three gates apply to the newest pending viewport, in order:

1. **busy** — never transmit while the MagTag has an unfinished refresh. At
   most one viewport is in flight, so a refresh is never started while the panel
   is working, and what goes out next is the newest state at the moment the
   panel came free rather than something queued while it was busy;
2. **coalescing** — a pending change must have existed for a short window
   before it may be sent, so a single keypress can never earn its own frame;
3. **interval** — the floor depends on what the writer is doing. Onset sends as
   soon as coalescing allows; a writer who has paused gets a short floor of
   roughly one partial refresh; a writer still typing gets the longer sustained
   floor that fits the authorised refresh budget.

The values are derived from measured panel behaviour, recorded in the module
alongside the constants they justify.

## Storage model

Use one open document first.

Suggested files:

```text
/documents/YYYY-MM-DD.txt
/recovery/active.log
/config/settings.json
/config/active.json
```

Storage rules:

- apply edits in RAM immediately;
- append compact recovery records periodically;
- checkpoint the full document atomically where practical;
- preserve the last known-good checkpoint;
- tolerate a truncated final recovery record;
- compact the recovery log after a successful checkpoint;
- reserve free space and fail safely before exhaustion.

## Power model

Bench development may continue with separate USB power where required for safe diagnostics. The finished prototype must use one protected battery, one power-path charger, one charging input, and a measured regulated distribution path for Fruit Jam, MagTag, storage, and any USB receiver.

Do not connect two independent charger circuits to one shared battery.

## Portability

The editor, input normalization, protocol, buttons, and storage layers must remain host-testable and must not import display hardware modules. The display adapter must remain replaceable so the writing engine can later run on another partial-refresh panel or controller.