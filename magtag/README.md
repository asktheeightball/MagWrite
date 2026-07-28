# MagTag Application

CircuitPython application for the original Adafruit MagTag.

## Implemented feasibility modules

```text
code.py                  fail-closed physical entrypoint
config.py                bounded settings and hardware confirmation
hardware_gate.py         original-panel/controller gate
hardware_identity.py     recorded compatibility decision
magwrite/editor.py       host-testable bounded line editor
magwrite/events.py       bounded queue and deterministic producer
magwrite/renderer.py     fixed 1-bit text/cursor snapshot
magwrite/refresh.py      cooperative revision/refresh scheduler
magwrite/serial_log.py   constant-space JSON-lines serial logger
magwrite/display_adapter.py host-safe display contract and activation gates
magwrite/uc8151_adapter.py  gated UC8151 adapter with lazy hardware imports
magwrite/physical_test.py   bounded one-full-plus-20-partial runner
uc8151.py                verbatim GPL upstream driver
hardware_refresh_test.py dedicated physical-test entry point
hardware_test_boot.py    gated writable-filesystem setup for one-time guard
hardware_uart_viewport_test.py guarded one-way UART physical receiver
magwrite/uart_protocol.py bounded binary parser and CRC-32
magwrite/uart_receiver.py sequence validation and newest-viewport coalescer
magwrite/transport_scheduler.py drain-first single-refresh scheduler
magwrite/viewport_message.py bounded semantic viewport model
magwrite/viewport_renderer.py display-only complete-snapshot renderer
```

## First implementation task

Build a typing feasibility harness before the full editor:

1. Verify the hardware revision.
2. Integrate the compatible no-flash partial-refresh driver with licence notices intact.
3. Draw one line of monospaced text.
4. Feed simulated sequenced key events.
5. Start partial refresh non-blockingly.
6. Continue updating the editor while the display is busy.
7. Refresh the latest revision after the panel becomes idle.
8. Log timing, stale revisions, and update counts.

The host harness and adapter gates pass independently of display hardware.
Physical execution requires the explicit gates and the applicable procedure in
`../docs/`. The one-way Fruit Jam UART viewport gate passed on 2026-07-28.
No Wi-Fi or Bluetooth code is included.
