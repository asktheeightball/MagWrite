# MagWrite Hardware

## Prototype hardware

### Fruit Jam UART feasibility controller

The one-way feasibility harness uses an Adafruit Fruit Jam as an authoritative
deterministic viewport generator. The physical board identity and actual
CircuitPython A0/TX alias must be captured from that connected board before
activation. Bench wiring is Fruit Jam selected TX to MagTag selected D10/RX
plus common ground. Each board is USB-powered separately; all inter-board power
conductors remain disconnected and insulated. This exact separately powered
one-way link passed its controlled physical test on 2026-07-28.

### Adafruit MagTag

Role: e-paper display terminal and physical controls. The Fruit Jam is expected to become the authoritative editor and storage device in the expanded prototype.

Required prototype revision:

- original 2.9-inch panel compatible with UC8151D/IL0373 and GDEW029T5D behavior;
- not assumed compatible with the 2025 SSD1680 MagTag revision.

Relevant characteristics:

- ESP32-S2 with Wi-Fi and no Bluetooth radio;
- 296×128 e-paper display;
- four front buttons;
- onboard LiPo charging and battery connector;
- internal flash and PSRAM subject to actual firmware availability.

### Adafruit Fruit Jam

Role: authoritative editor, document storage, autosave/recovery, viewport generation, and optional USB-keyboard fallback.

Relevant characteristics:

- RP2350B main processor;
- USB host support;
- microSD storage;
- Wi-Fi through the onboard ESP32-C6 coprocessor;
- exposed GPIO suitable for a hardware UART connection to the MagTag.

### Wemos LOLIN32 Lite

Role: Bluetooth keyboard receiver.

Known characteristics:

- original dual-mode ESP32 with BLE and Bluetooth Classic capability;
- USB-C connector through CH340C USB-to-UART converter;
- USB-C is for power, flashing, and serial logs, not USB host;
- no assumption of native USB keyboard support.

## Intended system architecture

```text
Bluetooth keyboard
        |
        v
LOLIN32 Lite
Bluetooth HID host
        |
        | wired UART
        v
Fruit Jam
editor, microSD, autosave, recovery
        |
        | wired UART
        v
MagTag
partial-refresh e-paper display and buttons
```

Only the keyboard is wireless. The internal device links should be wired for reliability and lower power consumption.

## Fruit Jam to MagTag UART connection

### Development recommendation

Use a 3.3 V UART connection with a shared ground:

```text
Fruit Jam TX  ---> MagTag RX
Fruit Jam RX  <--- MagTag TX
Fruit Jam GND <--> MagTag GND
```

During bench development, power the Fruit Jam and MagTag separately over USB. Connect only TX, RX, and ground. Do not connect their 3.3 V, 5 V, or battery rails together.

### Lowest-solder prototype

Begin with a one-way display link:

```text
Fruit Jam TX  ---> MagTag RX
Fruit Jam GND <--> MagTag GND
```

This is sufficient to prove that the Fruit Jam can send a viewport or framebuffer and the MagTag can render it. Add the return UART line later for:

- display-ready and display-complete acknowledgements;
- refresh timing and error reports;
- MagTag button events;
- status and diagnostics.

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

Do not rely on colour alone. Confirm cable pin order and board pinout before powering the boards.

For the one-way prototype, use one signal conductor and one ground conductor. Leave the red power conductor disconnected and insulated.

### Verified one-way pin plan

The controlled one-way test verified:

```text
Fruit Jam A0 / selected UART TX  ---> MagTag D10 / selected UART RX
Fruit Jam GND                    <--> MagTag GND
```

The return aliases were confirmed on-device by `dir(board)` and successful
non-transmitting UART construction on the installed CircuitPython builds:

```text
MagTag board.A1 / UART TX  ---> Fruit Jam board.A1 / UART RX
```

On Fruit Jam, A1 is the exposed three-pin analog/GPIO connector adjacent to
A0. The intended complete bench wiring is:

```text
Fruit Jam A0 signal ---> MagTag D10 signal
MagTag A1 signal    ---> Fruit Jam A1 signal
Fruit Jam GND       <--> MagTag GND
```

The return wire has not yet been physically installed or tested. Keep both
boards separately USB-powered and connect no 3.3 V, 5 V, BAT, USB, or red
power conductor. Before the guarded run, verify connector position rather
than cable colour and reconfirm that the chosen pins:

- exist under the expected aliases;
- are not reserved by the display, microSD, Wi-Fi coprocessor, audio, DVI, boot, or another required peripheral;
- initialize together as `UART(tx=A0, rx=A1)` on Fruit Jam and
  `UART(tx=A1, rx=D10)` on MagTag;
- use 3.3 V logic.

Do not hard-code an unverified `board.GPIO37` or similar alias.

### UART protocol direction

The Fruit Jam should send complete viewport snapshots or 1-bit framebuffers rather than one display command per typed character.

The MagTag framebuffer is approximately 4,736 bytes:

```text
296 × 128 ÷ 8 = 4,736 bytes
```

The protocol must use sequence numbers, length framing, integrity checking, and display backpressure. While the MagTag is refreshing, the Fruit Jam should retain only the newest pending viewport rather than queue every intermediate frame.

## Keyboard

The intended keyboard must be tested to determine whether it uses:

- BLE HID over GATT;
- Bluetooth Classic HID;
- or a proprietary USB receiver that is unsuitable for this prototype.

The bridge firmware should support both BLE and Classic HID where practical on the selected ESP-IDF release.

## Power prototype

For bench development, power each board independently over USB.

Do not parallel charger circuits onto one shared LiPo during early testing.

The finished one-battery design should use:

- one protected 1-cell LiPo;
- one charger with power-path/load-sharing support;
- one system power switch;
- regulated or battery-range feeds appropriate to each board;
- common ground;
- measured peak current and brownout margin.

## Hardware validation checklist

- [x] Photograph MagTag and record display-flex markings.
- [x] Confirm the exact one-way Fruit Jam and MagTag UART pin aliases on-device.
- [x] Verify the one-way Fruit Jam-to-MagTag UART link using signal and ground only.
- [ ] Verify the later bidirectional UART link and MagTag button events.
- [ ] Confirm UART logic levels are 3.3 V.
- [x] Confirm no power conductors were connected during the separately powered one-way bench test.
- [ ] Confirm keyboard Bluetooth mode.
- [ ] Confirm LOLIN32 flash size and available GPIO.
- [x] Confirm MagTag display controller/revision as original UC8151D/T5 family.
- [x] Measure initial 20-run MagTag partial-refresh duration.
- [x] Measure initial full-refresh duration.
- [ ] Measure active and idle current for each board.
- [ ] Determine safe battery capacity and charging topology.

## Display-driver dependency

The no-flash refresh implementation derives from `bciuca/magtag-partial-refresh-driver`, which is GPL-3.0-or-later. Preserve all applicable licence notices, modification records, GPL text, and corresponding-source obligations.
