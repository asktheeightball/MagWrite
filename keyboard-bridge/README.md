# LOLIN32 Keyboard Bridge

ESP-IDF firmware for the Wemos LOLIN32 Lite based on the original ESP32.

## Responsibilities

- Discover, pair, bond, and reconnect to a Bluetooth HID keyboard.
- Support BLE HID and Bluetooth Classic HID where available in the selected ESP-IDF release.
- Decode HID reports into normalized semantic key events.
- Track modifiers, Caps Lock, key-down/key-up state, and deliberate repeat behavior.
- Buffer events without blocking Bluetooth callbacks.
- Expose serial diagnostics through the onboard CH340C connection.
- Forward ordered events to the MagTag over the protocol in `../PROTOCOL.md`.

## Planned structure

```text
CMakeLists.txt
sdkconfig.defaults
main/
  CMakeLists.txt
  main.c
  ble_keyboard.c
  ble_keyboard.h
  hid_parser.c
  hid_parser.h
  keymap_us.c
  keymap_us.h
  event_queue.c
  event_queue.h
  transport.c
  transport.h
```

## First implementation task

Start from Espressif’s supported `esp_hid_host` example for the installed ESP-IDF version. Prove the actual keyboard can pair and reconnect before adding Wi-Fi transport.

Do not guess the keyboard’s Bluetooth mode. Record whether it uses BLE HID, Bluetooth Classic HID, or both.