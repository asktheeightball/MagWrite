# MagWrite

MagWrite is a focused, portable writing terminal inspired by BYOK-style drafting devices, but built around an e-paper display.

## Version B prototype

```text
Bluetooth keyboard
        |
        v
LOLIN32 Lite (original ESP32)
- Bluetooth HID host
- pairing and reconnect
- normalized key-event queue
- private Wi-Fi access point
        |
        | reliable TCP link
        v
Original Adafruit MagTag
- authoritative editor
- local journal storage
- no-flash 1-bit partial refresh
- four-button interface
```

The first prototype uses hardware already on hand. It is intended to prove that the original MagTag can deliver a usable typing experience with the experimental UC8151D/IL0373 no-flash partial-refresh driver.

## Product principles

- Capture every keypress immediately.
- Treat the text buffer and saved document as authoritative, never the display.
- Remain fully usable without internet access.
- Store plain UTF-8 text with resilient recovery.
- Keep the writing interface calm and distraction-free.
- Never claim a hardware test passed unless it ran on the physical device.
- Keep keyboard transport, editor, storage, and display drivers modular.

## Immediate milestone

Build a typing feasibility harness before the full journal application:

1. Confirm the MagTag display revision.
2. Validate no-flash partial refresh on the physical panel.
3. Render an editable line and measure update latency.
4. Pair and reconnect a Bluetooth keyboard through the LOLIN32 Lite.
5. Prove that no key events are lost while the display is busy.
6. Measure ghosting and establish a safe full-refresh cadence.
7. Save and recover one plain-text draft after forced power loss.

See [PRODUCT.md](PRODUCT.md), [ROADMAP.md](ROADMAP.md), and [ARCHITECTURE.md](ARCHITECTURE.md) for the current specification.

## Repository layout

```text
magtag/             CircuitPython editor and e-paper frontend
fruitjam/           CircuitPython one-way UART viewport feasibility sender
keyboard-bridge/    ESP-IDF Bluetooth HID bridge for LOLIN32 Lite
host-tests/         Host-runnable protocol and editor tests
docs/               Build, wiring, testing, and research notes
```

## Status

The MagTag partial-refresh, local single-line typing, and bounded one-way Fruit
Jam UART viewport gates have passed on physical hardware. Bidirectional status,
acknowledgements, and all keyboard integration remain out of scope.

## Related research

The partial-refresh approach is based on the experimental GPL-3.0-or-later project `bciuca/magtag-partial-refresh-driver`. Any incorporated or derived code must preserve its applicable licence obligations.

## Licence

MagWrite is distributed under the GNU General Public License v3.0 or later.
See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
