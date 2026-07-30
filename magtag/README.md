# MagTag Application

CircuitPython application for the original Adafruit MagTag.

From V1.6 this directory ships as the **display half of the writing appliance**:
copy it onto CIRCUITPY and it runs, with no flag to set. `PHYSICAL_TEST_MODE`
ships as `MAGTAG_STANDALONE`, which is activatable but is **not** a guarded
harness mode and is deliberately absent from `hardware_test_boot.py`'s remount
tuple — the runtime writes no guard, so it needs no writable filesystem. Every
guarded harness below still ships disabled, still needs its own mode string, and
still wins when armed. The compatibility gate is unchanged and still checked
first. See [../docs/STANDALONE.md](../docs/STANDALONE.md).

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
magwrite/viewport_renderer.py display-only renderer, geometry derived from the font
magwrite/font.py         the UI's one font: terminalio.FONT at native scale 1
magwrite/button_footer.py the persistent strip naming the four bezel actions
magwrite/mono_canvas.py  1-bit framebuffer and the landscape drawing primitives
magwrite/test_pattern.py the superseded 3x5 table, kept for the proven harnesses
magwrite/buttons.py      debounced four-button pad and normalized actions
magwrite/startup_screens.py the two local screens drawn before the link is up
dev_display_runtime.py   the runtime, in the STANDALONE or DEVELOPMENT profile
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
