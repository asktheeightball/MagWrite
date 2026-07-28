# MagWrite Roadmap

## Priority 0 — Hardware gate

### P0.1 Identify MagTag revision

- Confirm whether the physical MagTag uses the original UC8151D/IL0373-compatible panel.
- Record board markings, purchase era, CircuitPython version, and display behavior.
- Stop and redesign the display driver path if the board is the 2025 SSD1680 edition.

### P0.2 Validate partial refresh

- Run the upstream clock example unchanged.
- Confirm the first full refresh and subsequent no-flash updates.
- Measure average, minimum, and maximum partial-refresh time.
- Run 20, 50, 100, 500, and 1,000 update tests.
- Photograph or record ghosting and pixel degradation.
- Determine an initial safe full-refresh interval.

**Exit:** physical MagTag produces repeatable no-flash updates and measured results are documented.

## Priority 1 — Local typing harness

- Create a host-testable editor buffer.
- Render one editable monospaced line.
- Simulate key events locally without Bluetooth.
- Use non-blocking refresh and revision tracking.
- Prove that simulated input remains ordered while the display is busy.
- Add a non-blinking block or underscore cursor.

**Exit:** a simulated 80 WPM stream is captured without loss and the display catches up after input stops.

## Priority 2 — Bluetooth keyboard bridge

- Start from the ESP-IDF HID host example supported by the installed toolchain.
- Pair with the actual intended keyboard.
- Verify BLE versus Bluetooth Classic mode.
- Normalize characters and semantic navigation keys.
- Implement bonding, reconnect, repeat handling, and queue overflow reporting.
- Add serial diagnostics and a documented bond-reset flow.

**Exit:** keyboard input remains correct through keyboard sleep, power cycle, and bridge reboot.

## Priority 3 — Reliable wireless transport

- Establish an offline local network topology.
- Start with persistent TCP.
- Add protocol versioning, sequence numbers, acknowledgements, duplicate suppression, and reconnect replay.
- Keep a bounded bridge queue and expose overflow visibly.
- Add heartbeat and status frames.

**Exit:** no events are lost or reordered through MagTag display refresh, temporary disconnect, or reconnect within the queue limit.

## Priority 4 — Journal vertical slice

- Create/open today’s entry.
- Insert text, Backspace, Delete, Enter, arrows, Home, and End.
- Add wrapping, scrolling, word count, and save state.
- Add autosave, recovery log, checkpointing, and boot recovery.
- Map MagTag buttons to previous page, next page, save, and menu.

**Exit:** complete a 30-minute journal session and recover the final checkpoint after forced power loss.

## Priority 5 — Product hardening

- Recent-document browser.
- New, rename, and archive flows.
- Storage-space safeguards.
- Battery measurement and low-battery behavior.
- Enclosure and one-battery power design.
- Keyboard layout abstraction.
- Export or backup over Wi-Fi.
- Long-duration soak and display-wear testing.

## Future options

- Larger monochrome partial-refresh display.
- microSD storage.
- integrated keyboard or clamshell enclosure.
- consolidated ESP32-S3/custom PCB design.
- optional BYOK-style capture commands such as `::note` and `::task`.