# One-cable bench power — physical check

The smallest check that settles whether the arrangement in
[BENCH_POWER.md](BENCH_POWER.md) actually runs the rig. Not a harness: no guard,
no remount, no PASS/FAIL verdict written by a board. It uses the ordinary
[development runtime](DEVELOPMENT_RUNTIME.md) and reports what happened.

The intended finished behaviour is one sentence long: **connect one USB-C cable
to the Fruit Jam and the complete device starts by itself.**

## Configuration under test

```text
5 V supply, ≥1.5 A ──► one USB-C cable ──► Fruit Jam
                                             │
                                             ├── USB-A ──► wired USB keyboard
                                             │
                                             └── USB-A ──► USB-A-to-USB-C ──► MagTag
```

UART unchanged: Fruit Jam `A0` TX → MagTag `D10` RX, MagTag `A1` TX → Fruit Jam
`A1` RX, common ground, 115200 baud, **red/power conductor disconnected and
insulated**.

The MagTag has no separate power source, no console, and no host-visible
`CIRCUITPY` in this configuration. That is the arrangement, not a fault.

### Where the one cable goes

For this check the single upstream cable goes to the **PC**, so the Fruit Jam's
console is readable and the run leaves evidence. That is the development
configuration; it is the same wiring. A wall charger is the standalone
configuration and changes nothing on either board.

If the PC's port cannot hold the rig up — the symptom would be a brownout on the
first full refresh, which is the largest current step of the run — repeat from a
≥1.5 A charger and accept that there is no console. Everything the check needs to
see is also visible on the panel.

## Before the cable is connected

1. **Deploy both boards while they are still reachable.** The MagTag's USB-C is
   about to be occupied by the Fruit Jam, so this is the last moment its
   `CIRCUITPY` is host-writable. Copy the current `magtag/` and `fruitjam/`
   payloads, then move the MagTag's cable off the PC.
2. **Confirm by eye** that the UART cable carries only TX, RX, and ground, and
   that the red conductor is still disconnected and insulated at both ends. On
   both boards that conductor is 5 V by default.
3. Confirm both board power switches are ON, and that nothing else is plugged
   into either board.

## Procedure

1. Connect the one cable. Both boards cold boot **simultaneously**; no reset
   order is used, and none is available.
2. Start a read-only capture on the Fruit Jam console.
3. Watch for `dev_runtime_ready`, then for the handshake. Expect one or more
   `live_waiting_for_display` lines while the panel initialises, then
   `live_typing_started` carrying `hello_attempts` and `display_wait_seconds`.
   **A wait is the expected result here, not a fault.**
4. Confirm the existing document opens on the panel, with its words intact.
5. Type a short line from the wired keyboard and confirm the characters reach the
   panel.
6. Press one MagTag button and confirm it acts — `dev_display_button_pressed` is
   not visible without a MagTag console, but `button_event_received` and
   `shell_button_applied` are on the Fruit Jam's.
7. Trigger a full display refresh — leaving the document and returning is enough,
   and it is also the largest current step in the run.
8. Remove power. Wait for both boards to go dark.
9. Connect the one cable again and confirm the rig reconnects **with no
   intervention of any kind**: no reset, no order, no key pressed.
10. Throughout: watch for unexplained resets, keyboard disconnects, display
    failures, and anything hot to the touch.

## What would fail it

- either board failing to boot, or the Fruit Jam failing to enumerate;
- the handshake never completing, or completing only after an operator
  intervened;
- `duplicate or reversed input sequence`, `status_hello timeout`, or
  `result: ERROR` on either board;
- a restored document that comes back short, altered, or empty;
- a full refresh that does not complete, or a display busy timeout;
- CRC failures, sequence gaps, or resynchronisation events in the summary;
- keyboard enumeration failing, or reports stopping;
- an unexplained reset on either board — the brownout symptom, since both boards
  now share one supply through one connector;
- anything on either board hot to the touch.

No current figure is expected from this run: there is no USB power meter on the
bench, so `HARDWARE.md`'s measurement item stays open and is not claimed here.

## Result

Not yet run. The code it exercises is host-verified — `host-tests/test_display_wait.py`
covers the simultaneous cold boot end to end, including a display that arrives
after the old timeout would have ended the session, a restored document that
survives the wait untouched, and the sequence rules on both boards.
