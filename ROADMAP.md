# MagWrite Roadmap

## Priority 0 — Hardware gate

### P0.1 Identify MagTag revision

- Confirm whether the physical MagTag uses the original UC8151D/IL0373-compatible panel.
- Record board markings, purchase era, CircuitPython version, and display behavior.
- Stop and redesign the display driver path if the board is the 2025 SSD1680 edition.
- **Implemented, host-verified:** fail-closed revision/controller configuration
  gate and repeatable setup instructions.
- **Pending physical verification:** identification of the actual board and
  controller.
- **Completed 2026-07-28:** CircuitPython boot, USB, filesystem, and photographic
  evidence is recorded in `docs/HARDWARE_IDENTITY_REPORT.md`. The photographed
  `WFT0290CZ10 LW` display-flex marking, compared with Adafruit's documented
  physical verification, identifies the original UC8151D/T5-family panel.
  Decision is **`COMPATIBLE`** with high confidence. Physical display activation
  remains disabled pending driver integration and controlled testing.

### P0.2 Validate partial refresh

- Run the upstream clock example unchanged.
- Confirm the first full refresh and subsequent no-flash updates.
- Measure average, minimum, and maximum partial-refresh time.
- Run 20, 50, 100, 500, and 1,000 update tests.
- Photograph or record ghosting and pixel degradation.
- Determine an initial safe full-refresh interval.

**Exit:** physical MagTag produces repeatable no-flash updates and measured results are documented.

Test procedure is documented; every physical result remains pending.

**Integrated and host-verified:** GPL-3.0-or-later UC8151 driver at upstream
commit `61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`, isolated adapter, four-way
activation gate, full-seed/differential-state policy, timeout handling, and
bounded one-full-plus-20-partial test harness. Physical refresh behavior remains
pending until the controlled device run is completed and inspected.

**Physically run 2026-07-28:** one 3,324 ms full seed and exactly 20 partial
updates completed with zero timeouts. Partial timing was 718 ms mean, 716 ms
minimum, and 720 ms maximum. The user observed no full-screen flashing, and the
final update-20 photograph shows the expected stable pattern with no obvious
ghosting, incomplete erasure, border artefact, or pixel defect at the supplied
resolution. The controlled 20-update result is **`PASS`**.

**Physically run 2026-07-28:** the independent 50-update characterization
completed after one 3,324 ms full seed with zero timeouts and no stop
conditions. Partial refreshes measured 717.5 ms mean, 716 ms minimum, 719 ms
maximum, 0.8 ms standard deviation, and -0.6 ms first-to-final-ten drift. The
user approved every visual checkpoint and reported the final frame good. The
controlled 50-update result is **`PASS`**. The 100/500/1,000-update tests,
long-term pixel longevity, and production refresh cadence remain pending.

**Physically run 2026-07-28:** the independent 100-update characterization
completed after one 3,323 ms full seed with zero timeouts and no stop
conditions. Partial refreshes measured 717.4 ms mean, 713 ms minimum, 720 ms
maximum, 1.0 ms standard deviation, and +0.5 ms first-to-final-ten drift. The
user approved every visual checkpoint and reported the final frame good. The
controlled 100-update result is **`PASS`**. The 500/1,000-update tests,
long-term pixel longevity, and production refresh cadence remain pending.

## Priority 1 — Local typing harness

- Create a host-testable editor buffer.
- Render one editable monospaced line.
- Simulate key events locally without Bluetooth.
- Use non-blocking refresh and revision tracking.
- Prove that simulated input remains ordered while the display is busy.
- Add a non-blinking block or underscore cursor.

**Implemented and host-verified:** bounded line editor, deterministic 40/60/80
WPM producer, bounded explicit-overflow queue, fixed landscape text snapshot
with static underscore cursor, cooperative asynchronous refresh scheduling,
separate document/display revisions, catch-up after busy periods, configurable
full-refresh cadence, and structured refresh/event logs.

**Pending physical verification:** actual MagTag drawing, no-flash partial
refresh, refresh timing, ghosting, and the Priority 1 hardware exit.

**Physically verified 2026-07-28:** one bounded local single-line typing run
processed all 201 deterministic events exactly once and in order across
ordinary 40 WPM insertion, 80 WPM continuous typing, correction, and horizontal
viewport scenarios. All four final texts matched, the bounded queue peaked at
18/128 with zero overflow, 165 stale snapshots were skipped, 32 catch-up
refreshes completed, and displayed revision 201 caught up to render revision
201. The run used one initial full and 36 partial refreshes with zero timeout.
The user approved every final state. Physical activation was restored disabled
and both typing guards are present. Bluetooth, UART, multiline editing,
storage, production cadence, and production readiness remain pending.

**Exit:** a simulated 80 WPM stream is captured without loss and the display catches up after input stops.

**Implemented and host-verified 2026-07-28:** a separate, one-way Fruit Jam to
MagTag UART feasibility harness with versioned CRC-32 binary frames, explicit
192-byte payload, 256-byte UART FIFO, and 512-byte parser bounds, deterministic complete semantic
viewports, sequence/revision validation, malformed-stream resynchronization,
newest-frame coalescing, drain-before-render scheduling, independent fail-closed
activation gates, and independent persistent guards. The 83-test host suite
passes. The Fruit Jam identity/pin alias, physical low-solder link, electrical
behavior, two-console evidence, no-flash rendering, final catch-up, and both
completion guards were subsequently physically tested.

**Physically verified 2026-07-28:** the separately USB-powered Fruit Jam
`board.A0` TX to original MagTag `board.D10` RX link transmitted 17/17
CRC-valid frames and 11 complete semantic viewports at 115200 baud. The MagTag
rendered six newest snapshots, superseded five obsolete snapshots, reached
displayed revision 11, and reconciled final hash `2171BE7F` with zero rejected
frames, CRC failures, sequence gaps, or timeouts. One initial full and five
no-flash partial refreshes completed; four observed partials measured
699–702 ms (700.5 ms mean). The user approved the final viewport, cursor,
erasure, ghosting, border/pixel condition, wiring, and power behavior. Both
devices were restored disabled and all four independent UART guards are
present. See `docs/FRUITJAM_MAGTAG_UART_TEST.md` for retained failed-attempt
evidence and measurement limitations. Bidirectional traffic, acknowledgements,
buttons, keyboards, editing, persistence, Wi-Fi, and production power remain
unimplemented.

**Implemented and host-verified 2026-07-28; physical test NOT RUN:** the
existing UART frame format now carries bounded MagTag status messages for frame
acceptance, physical refresh start/completion, displayed-revision catch-up,
bounded errors, and final revision/hash reconciliation. The Fruit Jam has a
bounded acknowledgement tracker with distinct fail-closed timeouts and no
automatic physical retries. Both parsers account for discarded prefixes and
resynchronization, and the MagTag has a bounded status queue whose overflow is
fatal. Independent disabled modes and guards are present. No bidirectional
hardware outcome is claimed; wiring, serial evidence, display behavior, and
completion guards remain pending.

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
