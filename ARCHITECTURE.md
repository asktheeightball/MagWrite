# MagWrite Architecture

## System overview

```text
Bluetooth keyboard
        |
        | BLE HID or Bluetooth Classic HID
        v
LOLIN32 Lite / original ESP32
        |
        | ordered, acknowledged key events over TCP
        v
Original Adafruit MagTag
        |
        +-- editor and cursor state
        +-- local document and recovery storage
        +-- e-paper rendering and refresh scheduling
        +-- four-button input
```

## One-way wired viewport feasibility boundary

Before keyboard integration, `fruitjam/` provides a deliberately narrower
host-tested boundary. The Fruit Jam owns deterministic complete semantic
viewports, sequences, and revisions. A 3.3 V receive-only UART carries bounded
binary frames to the MagTag. The MagTag validates and coalesces them, drains all
currently available transport work before rendering, and never edits or
persists their text. This harness has no return channel, acknowledgement,
keyboard, Wi-Fi, or storage role. The physical one-way boundary passed on
2026-07-28; it does not imply bidirectional or acknowledged transport.

## Responsibility boundaries

### Keyboard bridge

The LOLIN32 Lite owns:

- keyboard discovery, pairing, bonding, and reconnect;
- HID report parsing;
- keyboard layout translation;
- modifier, Caps Lock, and repeat state;
- normalized semantic key events;
- bounded event buffering;
- private Wi-Fi access point or other proven offline network topology;
- reliable delivery and retransmission.

It does not own the document.

### MagTag application

The MagTag owns:

- authoritative document buffer;
- editor commands and cursor position;
- viewport and word wrapping;
- autosave, checkpoints, and recovery;
- document metadata;
- display snapshots and refresh scheduling;
- physical button interpretation.

The display is never treated as authoritative state.

## Runtime model

The MagTag main loop must remain cooperative and non-blocking:

1. Drain available network events.
2. Validate sequence and acknowledge accepted events.
3. Apply events to the editor buffer.
4. Run autosave/checkpoint work when due.
5. If the display is idle and a refresh is due, render the newest snapshot.
6. Start a non-blocking partial refresh.
7. Continue receiving input while the panel remains busy.
8. When the panel completes, refresh again only if the visible revision is stale.

## Display strategy

The experimental UC8151D driver provides 1-bit differential no-flash refresh but not true rectangular windowing. The entire framebuffer is transmitted, while unchanged pixels receive no visible drive.

Initial policy:

- first frame: full refresh;
- active typing: coalesced partial refreshes;
- refresh as soon as the display is idle and the visible revision is stale;
- do not animate a blinking cursor;
- periodic full refresh according to measured ghosting and wear;
- force full refresh on document open and explicit user command;
- preserve panel OLD/NEW differential state by avoiding panel power-off during an active writing session.

The full-refresh interval must remain configurable and must be based on hardware testing.

## Storage model

Use one open document at a time.

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
- reserve free flash space and fail safely before exhaustion.

## Portability

The editor, protocol, and storage layers must not import display hardware modules. The display adapter must be replaceable so the same writing engine can later run on a larger partial-refresh e-paper panel or another controller.
