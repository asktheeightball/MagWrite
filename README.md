# MagWrite

MagWrite is a focused, portable writing terminal inspired by BYOK-style drafting devices, but built around a persistent e-paper display.

## Current prototype

```text
Wired USB keyboard (proven); wireless keyboard with USB receiver (intended, not
yet working on any receiver tested)
        |
        v
Adafruit Fruit Jam
- USB HID host
- application shell and input routing
- authoritative multiline editor
- viewport generation
- microSD storage and forced-power-loss recovery
- MagTag button-event interpretation
        |
        | bidirectional UART
        v
Original Adafruit MagTag
- no-flash 1-bit partial refresh
- display acknowledgements
- four-button control surface
```

The Fruit Jam owns document, cursor, layout, storage, and workflow state. The MagTag renders complete semantic viewports, reports physical display state, and sends normalized button events back to the Fruit Jam.

The LOLIN32 Lite Bluetooth bridge is deferred. It should be considered only if the required keyboard is Bluetooth-only and cannot use wired USB or a standard USB receiver.

## Product principles

- Capture every input event immediately.
- Treat the Fruit Jam text buffer and saved document as authoritative, never the display.
- Keep the MagTag display-only except for normalized physical button events.
- Remain fully usable without internet access.
- Store portable plain UTF-8 text with resilient recovery.
- Keep the writing interface calm and distraction-free.
- Never claim a hardware test passed unless it ran on the physical device.
- Keep keyboard, button, editor, storage, transport, and display layers modular.

## Verified foundations

The project has physically verified:

- original UC8151D/T5-family MagTag compatibility;
- 20-, 50-, and 100-update no-flash partial-refresh runs;
- deterministic local typing while the display is busy;
- one-way Fruit Jam → MagTag semantic viewport transport;
- bidirectional UART display acknowledgements;
- stale-frame coalescing;
- physical displayed-revision and viewport-hash reconciliation;
- the multiline editor and five-line MagTag layout;
- one wired USB HID keyboard directly on the Fruit Jam;
- microSD autosave and forced-power-loss recovery;
- the MagWrite Shell;
- the four writing modes, over an append-only document catalogue;
- the one-gesture exit from a document, and the four MagTag buttons as the
  primary shell controls;
- one USB-C cable into the Fruit Jam starting the complete device by itself, with
  no reset and no start order.

## Current milestone order

1. ~~Physically verify the integrated multiline editor and five-line MagTag layout.~~
2. ~~Integrate one known USB HID keyboard directly on the Fruit Jam.~~
3. ~~Add microSD autosave, forced-power-loss recovery, and the four writing modes.~~
4. ~~Add MagTag button events over the existing return UART link, and remove the
   Save/Status interruption.~~ Physically verified 2026-07-30.
5. Support a wireless keyboard with a USB receiver. **Blocked on hardware** —
   the one receiver available is incompatible; see `ROADMAP.md`.
6. ~~Bring the bench to one-cable power.~~ Physically verified 2026-07-30. A
   direct 5 V feed between the boards is refused, because neither board has a 5 V
   input; see [docs/BENCH_POWER.md](docs/BENCH_POWER.md).
7. Build the minimum standalone writing workflow. **<- current.** Implemented
   and host-verified; the physical check in
   [docs/STANDALONE_CHECK.md](docs/STANDALONE_CHECK.md) has not been run.
8. Integrate one rechargeable battery and one charging port.
9. Complete enclosure and product hardening.

## Running it

Copy `fruitjam/` and `magtag/` onto their boards and connect one USB-C cable to
the Fruit Jam. From V1.6 that is the whole procedure: the shipped configuration
**is** the writing appliance, and there is no flag to set, no console to attach,
no volume to mount, and no start order. See [docs/STANDALONE.md](docs/STANDALONE.md).

The bench configuration, with two consoles and a stop gesture, is now the thing
you opt into — see [docs/DEVELOPMENT_RUNTIME.md](docs/DEVELOPMENT_RUNTIME.md).
Every guarded harness still ships disabled and still has to be armed by name.

## Repository layout

```text
fruitjam/           authoritative editor, viewport, UART, and future storage code
magtag/             CircuitPython e-paper terminal, acknowledgements, and buttons
host-tests/         host-runnable editor, layout, protocol, and scheduler tests
docs/               build, wiring, testing, reports, and research notes
keyboard-bridge/    deferred LOLIN32 Bluetooth adapter work, if later required
```

See [PRODUCT.md](PRODUCT.md), [ROADMAP.md](ROADMAP.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [HARDWARE.md](HARDWARE.md) for the current specification and decisions. [docs/STANDALONE.md](docs/STANDALONE.md) is the device as a writer meets it; [docs/PERSISTENCE.md](docs/PERSISTENCE.md), [docs/SHELL.md](docs/SHELL.md), and [docs/MODES.md](docs/MODES.md) carry the storage, shell, and writing-mode designs, and [docs/BENCH_POWER.md](docs/BENCH_POWER.md) the bench power audit.

## Related research

The partial-refresh approach is based on the experimental GPL-3.0-or-later project `bciuca/magtag-partial-refresh-driver`. Any incorporated or derived code must preserve its applicable licence obligations.

## Licence

MagWrite is distributed under the GNU General Public License v3.0 or later.
See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).