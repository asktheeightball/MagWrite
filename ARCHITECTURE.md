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