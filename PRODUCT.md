# MagWrite Product Specification

## Vision

MagWrite is a pocketable, distraction-free writing appliance that lets a user bring a Bluetooth keyboard and write into a persistent e-paper interface without opening a phone, tablet, or laptop.

It is inspired by the portability and focused workflow of BYOK-style drafting devices, while deliberately using e-paper and accepting predictable display latency in exchange for a calm, persistent screen.

## Version B target

Version B uses:

- Original Adafruit MagTag with UC8151D/IL0373-compatible 2.9-inch e-paper panel
- Wemos LOLIN32 Lite based on the original ESP32
- Bluetooth HID keyboard
- Private local Wi-Fi connection between the bridge and MagTag
- CircuitPython on MagTag
- ESP-IDF on LOLIN32 Lite

The 2025 SSD1680 MagTag is not assumed compatible with the selected partial-refresh driver.

## Primary user

A writer or journaler who wants to:

- sit down and begin writing quickly;
- use a preferred external keyboard;
- avoid notifications and general-purpose apps;
- trust that every keypress is captured and saved;
- keep work in portable plain-text files.

## Core experience

1. Power on MagWrite.
2. The Bluetooth bridge reconnects to the bonded keyboard.
3. The MagTag opens the latest draft or today’s journal entry.
4. Typing updates the authoritative text buffer immediately.
5. The e-paper display catches up through non-blocking partial refreshes.
6. Autosave and recovery run independently from display refresh.
7. The writer can create, open, save, rename, and archive plain-text documents.

## Version 1 scope

### Required

- BLE and/or Bluetooth Classic HID keyboard support according to actual keyboard capability
- automatic keyboard reconnect
- reliable sequenced key-event transport
- insert, Backspace, Delete, Enter, arrows, Home, and End
- Shift and Caps Lock
- monospaced 1-bit writing view
- visible cursor without continuous blinking
- deferred/non-blocking e-paper updates
- periodic full ghost-clearing refresh
- local plain-text storage
- append-only recovery journal
- autosave and manual save
- dated journal entry creation
- recent-document list
- word count and save state
- battery and connection indicators where practical

### Deferred

- rich text
- spell-checking
- cloud account system
- collaborative editing
- full-text search across an archive
- unlimited undo
- touch interface
- integrated keyboard
- custom PCB

## Non-goals

MagWrite is not intended to be:

- a general-purpose computer;
- a desktop-class word processor;
- an instant-refresh LCD replacement;
- dependent on internet access;
- a browser or app platform.

## Success criteria

Version B succeeds when:

1. A bonded keyboard reconnects after keyboard and bridge reboot.
2. No key events are lost or reordered during display activity.
3. Visible text catches up after the typist pauses.
4. A full refresh does not interrupt text capture.
5. A draft survives a forced MagTag reboot or power loss.
6. Ghosting and display wear are measured and documented.
7. The device is usable for a continuous 30-minute journaling session.
8. All hardware limitations are explicit rather than hidden.