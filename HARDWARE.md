# MagWrite Hardware

## Prototype hardware

### Adafruit MagTag

Role: editor, storage, e-paper display, and physical controls.

Required prototype revision:

- original 2.9-inch panel compatible with UC8151D/IL0373 and GDEW029T5D behavior;
- not assumed compatible with the 2025 SSD1680 MagTag revision.

Relevant characteristics:

- ESP32-S2 with Wi-Fi and no Bluetooth radio;
- 296×128 e-paper display;
- four front buttons;
- onboard LiPo charging and battery connector;
- internal flash and PSRAM subject to actual firmware availability.

### Wemos LOLIN32 Lite

Role: Bluetooth keyboard receiver and local wireless bridge.

Known characteristics:

- original dual-mode ESP32 with BLE and Bluetooth Classic capability;
- USB-C connector through CH340C USB-to-UART converter;
- USB-C is for power, flashing, and serial logs, not USB host;
- no assumption of native USB keyboard support.

## Keyboard

The intended keyboard must be tested to determine whether it uses:

- BLE HID over GATT;
- Bluetooth Classic HID;
- or a proprietary USB receiver that is unsuitable for this prototype.

The bridge firmware should support both BLE and Classic HID where practical on the selected ESP-IDF release.

## Power prototype

For bench development, power each board independently over USB.

Do not parallel two charger circuits onto one shared LiPo during early testing.

The finished one-battery design should use:

- one protected 1-cell LiPo;
- one charger with power-path/load-sharing support;
- one system power switch;
- regulated or battery-range feeds appropriate to each board;
- common ground;
- measured peak current and brownout margin.

## Hardware validation checklist

- [ ] Photograph both boards and record silkscreen markings.
- [ ] Confirm MagTag display controller/revision.
- [ ] Confirm keyboard Bluetooth mode.
- [ ] Confirm LOLIN32 flash size and available GPIO.
- [ ] Measure MagTag partial-refresh duration.
- [ ] Measure full-refresh duration.
- [ ] Measure active and idle current for each board.
- [ ] Verify simultaneous Bluetooth and Wi-Fi stability on LOLIN32.
- [ ] Verify MagTag Wi-Fi remains responsive during non-blocking display refresh.
- [ ] Determine safe battery capacity and charging topology.

## Display-driver dependency

The initial no-flash refresh research is based on `bciuca/magtag-partial-refresh-driver`, which is GPL-3.0-or-later. Before copying or deriving source, preserve licence notices and decide whether MagWrite will adopt a GPL-compatible project licence.