# MagTag Application

CircuitPython application for the original Adafruit MagTag.

## Planned modules

```text
code.py             cooperative application loop
config.py           local settings and hardware constants
editor.py           host-testable text buffer and commands
input_events.py     normalized key-event definitions
transport.py        TCP protocol client and replay handling
renderer.py         monospaced viewport rendering
refresh.py          partial/full refresh scheduler
document_store.py   checkpoints, journal, and recovery
buttons.py          four-button input adapter
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

No Wi-Fi or Bluetooth work is required until the local harness passes.