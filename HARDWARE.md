# MagWrite Hardware

## Prototype hardware

### Adafruit Fruit Jam

Role: authoritative editor, viewport controller, microSD storage, autosave/recovery controller, USB HID host, and MagTag button-event interpreter.

Relevant characteristics:

- RP2350B main processor;
- USB host support;
- microSD storage;
- Wi-Fi through the onboard ESP32-C6 coprocessor;
- exposed GPIO suitable for bidirectional UART to the MagTag.

### Adafruit MagTag

Role: e-paper display terminal and four-button input surface.

Required prototype revision:

- original 2.9-inch panel compatible with UC8151D/IL0373 and GDEW029T5D behavior;
- not assumed compatible with the 2025 SSD1680 MagTag revision.

Relevant characteristics:

- ESP32-S2 with Wi-Fi and no native Bluetooth radio;
- 296×128 e-paper display;
- four front buttons;
- onboard LiPo charging and battery connector;
- internal flash and PSRAM subject to actual firmware availability.

The MagTag does not own document, cursor, wrapping, storage, or workflow state. It renders Fruit Jam-supplied viewports, reports physical display status, and sends normalized button events.

### Wemos LOLIN32 Lite — deferred fallback

The LOLIN32 Lite is not part of the current default prototype.

It may be revisited only if the intended keyboard is Bluetooth-only and cannot use wired USB or a standard USB receiver.

If reintroduced, its role is limited to Bluetooth HID reception and normalized key-event forwarding into the Fruit Jam. It must not own document or display state.

## Intended system architecture

```text
Wired USB keyboard or wireless keyboard with USB receiver
        |
        v
Fruit Jam
- USB HID host
- authoritative editor
- microSD storage and recovery
- viewport generation
- button-event interpretation
        |
        | bidirectional UART
        v
MagTag
- partial-refresh e-paper display
- display acknowledgements
- four-button event capture
```

The internal Fruit Jam ↔ MagTag link is wired for reliability and lower power consumption.

## Fruit Jam to MagTag UART connection

### Verified bench wiring

```text
Fruit Jam board.A0 / UART TX  ---> MagTag board.D10 / UART RX
Fruit Jam board.A1 / UART RX  <--- MagTag board.A1 / UART TX
Fruit Jam GND                 <--> MagTag GND
```

The bidirectional link passed physical testing at 115200 baud.

During bench development, power the Fruit Jam and MagTag separately over USB. Connect only TX, RX, and common ground. Do not connect their 3.3 V, 5 V, BAT, charger, or USB power rails together.

### Plug-in cable approach

Prefer pre-crimped plug-in cables rather than soldering directly to either board:

- JST-PH 2 mm 3-pin/STEMMA-style cables for compatible three-pin connectors;
- female-to-female Dupont jumpers for exposed header pins;
- insulated unused power conductors.

Typical three-wire cable colours are:

```text
black = ground
red   = power
white = signal
```

Do not rely on colour alone. Confirm connector position and pinout before powering the boards.

For UART bench testing, leave red/power conductors disconnected and insulated.

## UART protocol direction

The Fruit Jam sends complete semantic viewport snapshots rather than one display command per typed character.

The MagTag returns bounded status and input messages, including:

- frame accepted;
- refresh started;
- refresh completed;
- display caught up;
- display error;
- test complete;
- normalized button events, from V1.5.

The protocol uses versioning, sequence numbers, length framing, CRC32, bounded parsing, resynchronization, duplicate/stale handling, and display backpressure. While the MagTag is refreshing, the Fruit Jam retains only the newest required viewport rather than queueing every intermediate editor state.

## MagTag buttons

Implemented in V1.5. The four front buttons control Fruit Jam-owned application
behaviour through the existing return UART path, and are the **primary** shell
control surface; the keyboard's shell keys remain as a fallback.

```text
MagTag button (active low, internal pull-up)
        |
        v
stability debounce, per-action minimum interval, monotonic press ordinal
        |
        v
sequenced BUTTON_EVENT on the acknowledgement channel
        |
        v
Fruit Jam action mapping
```

| Button | Pin alias | Action sent |
| --- | --- | --- |
| A | `BUTTON_A` | `MENU` |
| B | `BUTTON_B` | `UP` |
| C | `BUTTON_C` | `DOWN` |
| D | `BUTTON_D` | `SELECT` |

Back-to-menu and select are the outer two so a thumb cannot confuse either with
the movement pair between them.

The MagTag reports only:

- a **normalized action** — `MENU`, `UP`, `DOWN`, `SELECT` — never which physical
  switch closed and never what the action should do;
- the press edge. A held button does not repeat, and long press is not modelled;
- a monotonic press ordinal, a timestamp, and bounded diagnostics.

The Fruit Jam decides whether an event means:

- menu or document action;
- move the selection up or down;
- open, confirm, or dismiss;
- leave the editor, which checkpoints the document first.

The MagTag must not independently edit, move the authoritative cursor, save, open a document, or change application workflow.

A button pin the board does not expose is a **reported degraded mode**: the panel
runs and the keyboard still drives the shell. It is never a refusal to start.

## Keyboard

### Preferred path: direct USB HID

Use one known keyboard directly through the Fruit Jam USB host port.

Preferred order:

1. wired USB keyboard;
2. wireless keyboard with a standard USB receiver.

The USB HID adapter must support the required editing keys, modifiers, key release, hold, and deliberate repeat while preserving bounded normalized event processing.

### Deferred path: Bluetooth bridge

Use the LOLIN32 Lite only if a required keyboard is Bluetooth-only and direct USB HID is not viable.

Do not assume a generic USB Bluetooth adapter will work without a proven USB-host driver path.

## Unified power target

For bench development, separate USB power remains acceptable where needed for serial diagnostics and safe hardware isolation.

The finished device must use one unified rechargeable power system:

- one protected single-cell battery;
- one charger with power-path/load-sharing support;
- one external charging port;
- one system power switch;
- regulated feeds appropriate to Fruit Jam and MagTag;
- measured peak current and brownout margin;
- measured active, refresh, idle, and sleep consumption;
- battery-level and low-battery behavior.

Do not connect one battery simultaneously to the independent charger circuits on both development boards.

## Hardware validation checklist

- [x] Photograph MagTag and record display-flex markings.
- [x] Confirm MagTag display controller/revision as original UC8151D/T5 family.
- [x] Measure controlled 20-, 50-, and 100-update partial refresh behavior.
- [x] Verify one-way Fruit Jam-to-MagTag UART using signal and common ground.
- [x] Verify bidirectional UART acknowledgements using A0→D10 and A1→A1.
- [x] Confirm no inter-board power conductor during verified UART bench tests.
- [x] Physically verify the integrated multiline editor and five-line layout.
- [x] Implement MagTag button events over return UART. Physically verified
      2026-07-30 — all four buttons claimed, 9 presses delivered and applied
      exactly once each, none reaching the document. Recorded in `ROADMAP.md`.
- [ ] Verify one known USB HID keyboard on the Fruit Jam. Enumeration, interface
      selection, and boot-report reading are verified; **live typing is not** —
      two attempts failed because the keyboard sent no HID data to its receiver
      while that receiver was in the Fruit Jam host port. See
      `docs/FRUITJAM_USB_KEYBOARD_TEST.md`.
- [ ] Determine whether the Fruit Jam host port supplies enough current for a
      2.4 GHz receiver's radio, or retry with a wired USB keyboard.
- [ ] Verify keyboard reconnect, modifiers, hold, and repeat.
- [x] Read the microSD pin aliases off the board and set them in
      `fruitjam/config.py`. Done 2026-07-30 with `tools/fruitjam_sd_probe.py`;
      evidence `docs/FRUITJAM_SD_PROBE.jsonl`. The board exposes `SD_CS`,
      `SD_SCK`, `SD_MOSI`, `SD_MISO`, `SD_CARD_DETECT`, and a separate `SDIO_*`
      interface. The card is on the **dedicated** SPI bus, so those four aliases
      are now named explicitly rather than using the shared `board.SPI()`.
      `SD_CARD_DETECT` is claimed by the firmware before user code runs, so the
      optional card-detect path stays disabled.
- [x] **Provide a microSD card with a FAT filesystem.** Done 2026-07-30. The
      card found in the slot had a valid MBR whose one partition entry claimed
      more sectors than the card physically had, with no FAT volume boot record
      at that offset or twelve others; the runtime correctly reported
      `UNMOUNTABLE`. It was reformatted with explicit authorisation. FatFs sizes
      the FAT width from the volume, so the 946 MB card came out **FAT16, not
      FAT32**; nothing in V1.2 depends on the width. The format was proved by
      write, sync, unmount, remount, read back.
- [x] Verify microSD autosave and forced-power-loss recovery. **PASSED
      2026-07-30**; evidence `docs/FRUITJAM_V12_PERSISTENCE_SERIAL.jsonl`. A
      writing session produced 12 autosaves and 3 checkpoints, Ctrl-S manual save
      worked and inserted no character, and after the USB cable was pulled
      mid-session the restart recovered revision 73, 71 characters, cursor
      (2, 8) — exactly the last acknowledged edit.
- [ ] Measure active and idle current for each board and USB receiver.
- [ ] Determine and verify safe single-battery capacity, charging, and distribution topology.
- [ ] Complete enclosure and field-use testing.

## Display-driver dependency

The no-flash refresh implementation derives from `bciuca/magtag-partial-refresh-driver`, which is GPL-3.0-or-later. Preserve all applicable licence notices, modification records, GPL text, and corresponding-source obligations.