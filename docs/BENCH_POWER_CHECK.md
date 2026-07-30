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

**PASSED 2026-07-30.** Evidence: `BENCH_ONECABLE_FRUITJAM_SERIAL.jsonl` and its
`.timestamped.jsonl`, 351 records over two cold boots. Only the Fruit Jam console
exists in this configuration, by construction.

**One USB-C cable was connected and the complete device started by itself.** No
reset was pressed, no start order was used, and no key was touched before the
document was on the panel.

### The two cold boots, which are the same boot twice

| | Boot 1 | Boot 2 |
| --- | --- | --- |
| Handshake attempts | 4 | 4 |
| `display_wait_seconds` | 9.05 | 9.05 |
| Document recovered | `NOTE 1`, 96 chars, revision 361 | `NOTE 1`, **107 chars, revision 372** |
| Keyboard | `EPOMAKER TH40` `36B0:304E`, boot interface claimed | same |
| First refresh | full, 3586 ms | full, 3525 ms |

Boot 2 recovered exactly the 107 characters the MENU button checkpointed on the
way out of boot 1, so the round trip closes: written, made durable by a button,
power removed, and recovered by a rig that was told nothing.

The wait is the phase's central number, and it is worth reading twice. **The
Fruit Jam's first three handshakes went to a board that was not listening**, at
3.00 s, 6.01 s, and 9.01 s, each one logging the 96 (then 107) characters it was
holding and `"document_preserved": true`. The fourth was answered. On the code
this replaced, the session would have ended in `status_hello timeout` and
`result: ERROR` at five seconds — twice over, on both boots.

### Everything else the run measured

- 26 viewports sent, 26 caught up. Nothing lost, nothing stale at the end;
- 24 partial refreshes: 845–966 ms, mean 924 ms — in line with every previous
  bench run, so the shared supply did not slow the panel;
- two full refreshes, one per session, 3586 ms and 3525 ms. The largest current
  step of a run, taken twice, with no brownout and no reset;
- 23 button presses received, 23 applied. One press, one action, ordinals 1..23
  monotonic;
- typing reached the document through the shared rail with no dropped or
  duplicated report;
- autosave journaled and the MENU exit checkpointed to `SAVED` every time;
- microSD adopted the firmware's `/sd` mount on both boots.

Zero of each of the following, across both sessions: `live_display_handshake_restarted`,
`result: ERROR`, `duplicate or reversed input sequence`, `dev_display_error`,
`shell_fault`, rejected events, queue overflows, keyboard disconnects, CRC
failures, resynchronisation events, and storage faults.

Operator observations, which the logs cannot supply: **nothing was warm to the
touch** on either board, the cable, or the MagTag's regulator area, and **the
panel was clean and legible** through both sessions.

### What this run does not claim

- **No current was measured.** There is still no USB power meter on the bench, so
  every figure in `BENCH_POWER.md` section 4 remains documented-elsewhere or
  estimated, and `HARDWARE.md`'s measurement item stays open. Two boards, a hub,
  a keyboard, and a panel ran through one USB-C connector from a PC port without
  a brownout; that is an observation, not an amperage;
- **the receiver question is untouched.** It was not part of this run and nothing
  here bears on `36B0:3002`;
- **no thermal measurement.** "Nothing warm to the touch" is a hand, not a
  thermocouple, and it is recorded as such;
- **a long session was not run.** Two boots and a few minutes each is what this
  check is; soak testing belongs to Priority 7.

### The capture kept running, and caught something

Three further records were appended to the evidence file at 16:52:41, after this
write-up, while the rig was still connected and nobody was typing at it:

```json
{"event":"dev_runtime_session_summary","result":"ERROR","stop_reason":"live session idle timeout","timeouts":1}
{"event":"dev_runtime_stopped","result":"ERROR","detail":"live session idle timeout"}
```

The device switched itself off after the development runtime's 1800-second idle
bound, and reported `ERROR` for it. The document was `SAVED` and all 107
characters survived, so this costs the result above nothing — the check was over
and everything it claims had already happened.

It is left here because it is the clearest possible statement of why V1.6 exists.
Every bound in that runtime was written to end a *run* on a bench with a console,
and this rig has neither. See [STANDALONE.md](STANDALONE.md).

### Recorded along the way

The Fruit Jam was captured waiting **24 seconds and climbing** before the rewire,
with the MagTag not running at all — `BENCH_ONECABLE_PREFLIGHT_FRUITJAM.jsonl`.
That is the retry doing the thing it was built for, on hardware, before the
arrangement that needs it was even wired up.
