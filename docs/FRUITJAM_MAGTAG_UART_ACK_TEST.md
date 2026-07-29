# Fruit Jam ↔ MagTag UART acknowledgement test

Status: **PASS**

The return wire, status UART, and physical acknowledgement lifecycle have all
been exercised on hardware. The Fruit Jam can now distinguish viewport
transmitted, frame accepted, refresh started, refresh completed, display
caught up, and test complete as independent physical facts.

## Run identification

```text
Date/time            2026-07-28 17:51:17 - 17:51:53 local
Repository commit    5193a24 (main)
Fruit Jam            Adafruit Fruit Jam, RP2350B, UID FFDBA7B15146C218
                     CircuitPython 10.2.1 (2026-05-13)
MagTag               Original Adafruit MagTag 2.9-inch, ESP32-S2, UC8151D
                     Board ID adafruit_magtag_2.9_grayscale
                     UID C7FD1A005DEA, CircuitPython 9.1.1 (2024-07-22)
Serial consoles      Fruit Jam COM11, MagTag COM10
Baud                 115200
Protocol version     1
```

## Confirmed wiring

Confirmed by the operator against connector position and continuity, not by
cable colour, before the boards were armed:

```text
Fruit Jam A0 signal -> MagTag D10 signal
MagTag A1 signal    -> Fruit Jam A1 signal
Fruit Jam GND       <-> MagTag GND
```

Both boards were separately USB-powered throughout. No 3.3 V, 5 V, BAT, or
USB power conductor joined the boards. No wiring fault and no unexpected
heating was observed.

Pin aliases were re-confirmed on the hardware itself through each board's
REPL before arming:

```text
MagTag     board.D10 present, board.A1 present
Fruit Jam  board.A0 present, board.A1 present
```

## Implementation defects found and fixed before the run

Two blocking defects in the committed bidirectional implementation were
discovered during preflight. Both were fixed, host-validated, and committed
before any board was armed.

1. `251aaae` — Neither boot gate recognised the new modes, so the
   filesystem stayed read-only and the first guard write failed before any
   UART traffic. `MAGTAG_UART_ACK_RX` and `FRUITJAM_UART_ACK_TX` were added
   to the remount conditions; every previously armed mode is untouched.
2. `5193a24` — CircuitPython 9.1.1 on the ESP32-S2 ships `hashlib` with
   `sha1` only, so the receiver crashed with `AttributeError` at its UC8151
   driver integrity check. A host-safe pure-Python SHA-256 is now used only
   when no native implementation exists, keeping the pinned hash invariant
   byte-exact rather than weakening the gate. It costs roughly 10 s on-device
   for the 10,412-byte driver, once, at startup.

## Attempt 1 — INCONCLUSIVE

```text
Fruit Jam reset without the MagTag having been reset first.
Fruit Jam result   FAIL, stop_reason "status_hello timeout"
                   input_frames_sent 1, bytes_sent 32, bytes_received 0
                   viewport_frames_sent 0, crc_failures 0, test_complete false
MagTag             never armed, no guards created, no display activity
```

The return path was never exercised, so this attempt says nothing about
whether bidirectional acknowledgement works. It does confirm that the
HELLO-timeout stop condition fires on schedule, that the failure summary is
written to `.started` and never to `.complete`, and that the guard blocks
re-entry on the following boot.

The operator explicitly authorised deleting exactly one guard path,
`F:\magwrite_uart_ack_tx.started`, to permit attempt 2. Its FAIL summary is
reproduced above and was archived before deletion. No other guard was
touched.

## Attempt 2 — PASS

Both hard resets were issued from the host through each board's REPL with
`microcontroller.reset()`, so `boot.py` ran and reset ordering was exact.
The MagTag was armed and reset first and confirmed ready before the Fruit Jam
was reset.

```text
17:51:17  MagTag  uart_ack_rx_ready, rx_alias D10, tx_alias A1, baud 115200
17:51:47  Fruit Jam sends HELLO, MagTag answers STATUS_HELLO
17:51:53  TEST_COMPLETE received, both summaries PASS
```

### Required lifecycle, revision 1

```text
VIEWPORT sent            revision 1, sequence 2
FRAME_ACCEPTED           received_sequence 2, pending_revision 1
REFRESH_STARTED          refresh_mode 1 (full), previous_displayed_revision 0
REFRESH_COMPLETED        duration_ms 3578, stale false
DISPLAY_CAUGHT_UP        displayed_revision 1, viewport_hash 3506882175
```

### Supersession, revisions 2 to 5

```text
Revisions 2, 3, 4, 5 transmitted back to back.
All four accepted:  rev 2 superseded false
                    rev 3, 4, 5 superseded true
Only revision 5 rendered: REFRESH_STARTED refresh_mode 0 (partial),
                          REFRESH_COMPLETED duration_ms 952, stale false,
                          DISPLAY_CAUGHT_UP displayed_revision 5
Revisions 2, 3 and 4 were never reported as displayed.
```

`DISPLAY_CAUGHT_UP` was emitted only for revisions 1, 5 and 6. No skipped
viewport was ever falsely reported as displayed.

### Final revision 6

```text
FRAME_ACCEPTED           received_sequence 7, pending_revision 6
REFRESH_STARTED          refresh_mode 0 (partial), previous_displayed_revision 5
REFRESH_COMPLETED        duration_ms 988, stale false
DISPLAY_CAUGHT_UP        displayed_revision 6, viewport_hash 3692230089
TEST_COMPLETE            accepted 6, rendered 3, superseded 3, refreshes 3,
                         displayed_revision 6, error_count 0
```

### Counted results

```text
Viewport frames sent                6
Total input frames sent             8   (limit 100)
Status frames sent by MagTag       17
Status frames received by Fruit Jam 17
FRAME_ACCEPTED acknowledgements     6
REFRESH_STARTED acknowledgements    3
REFRESH_COMPLETED acknowledgements  3
DISPLAY_CAUGHT_UP acknowledgements  3
Frames rejected                     0
CRC failures                        0
Sequence gaps                       0
Status duplicates                   0
Stale acknowledgements              0
Parser rejections                   0
Discarded prefix bytes            567
Resynchronization events            5
Status queue maximum depth          2   (capacity 32)
Timeouts                            0
Final transmitted revision          6
Final displayed revision            6
Final hash                 3692230089 = 0xDC12F5C9
Full refreshes                      1   (limit 1)
Partial refreshes                   2   (limit 30)
Partial refresh durations     952 ms, 988 ms
Full refresh duration            3578 ms
```

### Byte reconciliation

```text
MagTag sent      517 bytes  =  Fruit Jam received 517 bytes
Fruit Jam sent   520 bytes
MagTag received 1087 bytes, of which 567 discarded before magic
1087 - 567 = 520, exactly the bytes the Fruit Jam sent
```

Every received byte is accounted for. The 567 discarded bytes are line noise
produced on the shared TX line while the Fruit Jam was resetting, before it
began transmitting. The bounded parser resynchronized 5 times and recovered
every valid frame with zero CRC failures and zero rejections, so the discard
and resynchronization counts are evidence that resynchronization works rather
than evidence of a fault.

### Final hash reconciliation

The physical final hash `0xDC12F5C9` equals the deterministic host-simulated
value reported by `tools/validate_uart_harness.py`, and the physical final
revision 6 equals the host-simulated final revision.

## Visual observation

The operator confirmed the panel showed revision 6 exactly:

```text
Title    UART ACK TEST
Line 1   < FIVE DOZEN LIQUOR JUGS
Line 2   CURSOR AT J          cursor on this line at column 10
Line 3   ACK COMPLETE >
Status   ACK REV 06
```

No corruption, ghosting, banding, or partial-update artifacts were reported.
No unexpected full-screen flash occurred; the single full refresh was the
intended initial one.

**No photograph was taken of the final screen.**

## Stop conditions encountered

None during attempt 2. Attempt 1 stopped on `status_hello timeout`, which was
the correct response to a receiver that had never been armed.

## Guard states

New guards, all four present:

```text
E:\magwrite_uart_ack_rx.started      8 bytes
E:\magwrite_uart_ack_rx.complete   652 bytes, result PASS
F:\magwrite_uart_ack_tx.started      8 bytes
F:\magwrite_uart_ack_tx.complete   628 bytes, result PASS
```

All 13 pre-existing guards were verified byte-identical against a backup
taken before any change, after the run completed:

```text
magwrite_refresh_test_20.started / .complete
magwrite_refresh_test_50.started / .complete / .pass
magwrite_refresh_test_100.started / .complete
magwrite_single_line_typing.started / .complete
magwrite_uart_rx.started / .complete
magwrite_uart_tx.started / .complete
```

The UC8151 driver hash on the device remains
`A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E`,
unchanged and matching the pinned upstream value.

## Final device configuration

Both boards were restored to disabled and observed failing closed:

```text
MagTag     ENABLE_PHYSICAL_DISPLAY = False
           PHYSICAL_TEST_MODE = "DISABLED"
           ENABLE_UART_RECEIVER = False
           UART_TEST_MODE = "DISABLED"
           ENABLE_UART_STATUS_TX = False
           BIDIRECTIONAL_UART_TEST_MODE = "DISABLED"
           observed {"event":"physical_test_refused",
                     "reason":"disabled_or_mode_mismatch"}

Fruit Jam  ENABLE_UART_TEST = False
           UART_TEST_MODE = "DISABLED"
           ENABLE_BIDIRECTIONAL_UART_TEST = False
           BIDIRECTIONAL_UART_TEST_MODE = "DISABLED"
           observed {"event":"uart_tx_refused","reason":"disabled"}
```

## Evidence record

```text
Fruit Jam serial   docs/FRUITJAM_UART_ACK_SERIAL.jsonl   26 device records
MagTag serial      docs/MAGTAG_UART_STATUS_SERIAL.jsonl  20 device records
Photograph         none taken
Physical result    PASS
```

## Known limitations

- The MagTag's final `storage.remount("/", readonly=True)` is refused with
  `Cannot remount '/' when visible via USB`, so its guards stay invisible to
  the USB host until the next boot with a disabled configuration. The guards
  are written correctly; only host visibility is delayed.
- Measured partial refreshes here are 952 ms and 988 ms against a previously
  characterized 700-718 ms. The difference has not been investigated and is
  recorded as observed.
- Malformed-frame and timeout handling remain host-test-only. No deliberately
  malformed traffic was injected physically.
