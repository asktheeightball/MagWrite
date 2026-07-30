# MagWrite Product Specification

## Vision

MagWrite is a portable, distraction-free writing appliance that lets a user connect a preferred external keyboard and write into a persistent e-paper interface without opening a phone, tablet, or laptop.

It is inspired by BYOK-style drafting devices while deliberately using e-paper and accepting predictable display latency in exchange for a calm, persistent screen.

## Current prototype target

The current prototype uses:

- Adafruit Fruit Jam as the authoritative editor, viewport, storage, and workflow controller;
- original Adafruit MagTag with the UC8151D/IL0373-compatible 2.9-inch e-paper panel as a display terminal and four-button control surface;
- bidirectional 3.3 V UART between Fruit Jam and MagTag;
- direct USB HID keyboard input through the Fruit Jam USB host port;
- CircuitPython on both boards during the prototype phase;
- microSD-backed plain-text persistence on the Fruit Jam;
- a future unified single-battery power system.

The 2025 SSD1680 MagTag is not assumed compatible with the selected partial-refresh driver.

The LOLIN32 Lite Bluetooth bridge is deferred. It should be introduced only if the intended keyboard is Bluetooth-only and cannot operate through wired USB or a standard USB receiver.

## Primary user

A writer or journaler who wants to:

- sit down and begin writing quickly;
- use a preferred external keyboard;
- avoid notifications and general-purpose apps;
- trust that every keypress is captured and saved;
- keep work in portable plain-text files;
- use simple physical controls without moving document authority onto the display terminal.

## Core experience

1. Power on MagWrite.
2. The Fruit Jam initializes the keyboard, document, storage, and display link.
3. The latest draft or today’s journal entry opens.
4. Keyboard input updates the authoritative Fruit Jam text buffer immediately.
5. The Fruit Jam sends complete semantic viewports to the MagTag.
6. The MagTag reports frame acceptance, refresh start, refresh completion, displayed revision, and errors.
7. The e-paper display catches up through non-blocking partial refreshes.
8. Autosave and recovery run independently from display refresh.
9. MagTag button events are sent to the Fruit Jam, which decides their meaning.
10. The writer can create, open, save, rename, and archive plain-text documents.

## Version 1 scope

### Required

- direct USB HID keyboard support on Fruit Jam;
- wired keyboard and wireless-receiver compatibility where standard USB HID is available;
- automatic keyboard reconnect where supported;
- normalized, bounded input-event handling;
- insert, Backspace, Delete, Enter, arrows, Home, and End;
- Shift and Caps Lock;
- authoritative multiline editor on Fruit Jam;
- deterministic wrapping and scrolling;
- monospaced 1-bit writing view;
- visible cursor without continuous blinking;
- deferred/non-blocking e-paper updates;
- periodic full ghost-clearing refresh based on measured behavior;
- bidirectional display acknowledgements;
- MagTag button events reported to Fruit Jam;
- local plain-text storage on microSD;
- append-only recovery journal;
- autosave and manual save;
- dated journal entry creation;
- recent-document list;
- word count and save state;
- one unified rechargeable battery system;
- battery, keyboard, display, and save indicators where practical.

### Deferred

- Bluetooth-only keyboard support through LOLIN32;
- rich text;
- spell-checking;
- cloud account system;
- collaborative editing;
- full-text search across an archive;
- unlimited undo;
- touch interface;
- integrated keyboard;
- custom PCB.

## Product-control principles

- Fruit Jam owns all document, cursor, viewport, storage, and workflow state.
- MagTag renders supplied viewports and reports physical state.
- MagTag buttons generate normalized events; they do not independently edit, save, scroll, or switch documents.
- The display is never treated as authoritative state.
- Keyboard, editor, storage, transport, buttons, and display drivers remain modular.
- The device remains fully usable without internet access.

## Non-goals

MagWrite is not intended to be:

- a general-purpose computer;
- a desktop-class word processor;
- an instant-refresh LCD replacement;
- dependent on internet access;
- a browser or app platform.

## Success criteria

Version 1 succeeds when:

1. A supported USB HID keyboard connects or reconnects reliably.
2. No input events are lost or reordered during display activity.
3. Visible text catches up after the typist pauses.
4. A full refresh does not interrupt input capture.
5. MagTag button events reach the Fruit Jam exactly once and produce Fruit Jam-owned actions.
6. A draft survives forced reboot or power loss.
7. The system operates from one rechargeable battery and one charging port.
8. Ghosting and display wear are measured and documented.
9. The device is usable for a continuous 30-minute journaling session.
10. All hardware limitations are explicit rather than hidden.