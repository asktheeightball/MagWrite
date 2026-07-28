# Fruit Jam to MagTag UART viewport test

Status: **PASS**

Date: 2026-07-28
Physical attempt: 3 (attempts 1–2 are retained as software compatibility failures)

## Hardware and wiring

- Fruit Jam: Adafruit Fruit Jam RP2350B, board id `adafruit_fruit_jam`,
  UID `FFDBA7B15146C218`
- Fruit Jam firmware: official CircuitPython 10.2.1 stable
- Firmware UF2 SHA-256:
  `67316D4B6884BBA24681A284F514658D4AE58F46D36AE18DC62D9698F2C0E199`
- Fruit Jam TX: physically queried `board.A0`; transmit-only UART initialization
  verified at 115200 baud
- MagTag: original Adafruit MagTag 2.9 ESP32-S2,
  board id `adafruit_magtag_2.9_grayscale`, UID `C7FD1A005DEA`
- MagTag firmware: CircuitPython 9.1.1
- MagTag RX: physically queried `board.D10`; receive-only UART initialization
  verified at 115200 baud
- Wiring: Fruit Jam A0/TX to MagTag D10/RX plus common ground
- Power: separate USB power to each board
- Inter-board power: no 3.3 V, 5 V, BAT, USB, or red power conductor connected
- Wiring was user-confirmed by connector position/pin rather than assumed colour.

Both complete CIRCUITPY volumes were backed up at
`C:\tmp\MagWrite-UART-preflight-20260728` before deployment.

## Protocol and limits

- Protocol version: 1
- Baud: 115200
- Payload maximum: 192 bytes
- Frame maximum: 210 bytes
- Hardware receive FIFO: 256 bytes
- Parser accumulator: 512 bytes
- Encoding: ASCII
- Inter-frame delay: 150 ms
- Inter-scenario observation delay: 4.5 s
- Post-reset sender delay: 3.0 s
- Deterministic run: 17 frames, including 11 VIEWPORT frames
- Display cap: one initial full plus at most 30 partial refreshes

The device UC8151 driver SHA-256 was verified from the host immediately before
arming:
`A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E`.
It remains the unmodified GPL-3.0-or-later upstream file from commit
`61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`.

## Attempt history

Attempt 1 stopped before guard claim, UART traffic, or display activity because
CircuitPython 9.1.1 does not expose SHA-256 through `hashlib`. The driver hash
remained externally verified.

Attempt 2a stopped with zero received bytes and zero display activity because
CircuitPython 9.1.1 lacks `bytearray.clear()`.

Attempt 2b transmitted all sender frames, but the receiver stopped before
reading bytes because CircuitPython 9.1.1 also rejects bytearray item deletion.
The failed receiver and successful sender evidence was preserved before the
three guards were deleted with explicit user authorization.

Attempt 3 used bounded slice reassignment throughout the parser and passed.

## Attempt 3 results

```text
Fruit Jam bytes sent:             1,027
Fruit Jam frames sent:               17

MagTag bytes observed:            1,323
Valid frames received:               17
Rejected frames:                       0
CRC failures:                          0
Sequence gaps:                         0
Viewport frames received:             11
Viewport frames rendered:              6
Viewport frames superseded:            5
Latest received revision:             11
Displayed revision:                   11
Initial full refreshes:                1
Partial refreshes:                     5
Timeouts:                              0
Final viewport hash:            2171BE7F
```

The 296-byte difference between observed UART bytes and framed sender bytes was
discarded as pre-magic input while the transmitter pin transitioned from its
startup/default state. It produced no invalid frame, CRC failure, sequence gap,
buffer overflow, or semantic message. This should be explicitly counted as
discarded-prefix bytes in the next protocol revision.

Four partial completion observations were captured: 701, 699, 702, and 700 ms.
Minimum was 699 ms, maximum 702 ms, and mean 700.5 ms. Five partial refreshes
completed; one completion timing log was missed when completion and catch-up
start occurred in the same scheduler service.

The full refresh occurred through the driver's blocking full-update call. The
recorded `5 ms` value is only the subsequent idle-observation delay and is not
a valid full-refresh duration. This run therefore does not claim a new full
timing measurement. The same physical panel's separately controlled prior full
seed measurement was 3,329 ms.

## Final viewport and visual acceptance

```text
Title:  UART VIEWPORT
Line 1: < FIVE DOZEN LIQUOR JUGS
Line 2: CURSOR AT J
Line 3: FRAME 11 >
Status: REV 11
Cursor: row 1, column 10 (the J cell)
```

The user confirmed:

- the expected final viewport and cursor;
- one initial full refresh;
- no full-screen flashing during subsequent updates;
- complete erasure of old viewport text;
- no severe ghosting, border corruption, pixel defect, heating, power
  instability, or wiring problem.

No photograph was supplied for attempt 3.

## Final safety state

- MagTag `ENABLE_PHYSICAL_DISPLAY = False`
- MagTag `PHYSICAL_TEST_MODE = "DISABLED"`
- MagTag `ENABLE_UART_RECEIVER = False`
- MagTag `UART_TEST_MODE = "DISABLED"`
- Fruit Jam `ENABLE_UART_TEST = False`
- Fruit Jam `UART_TEST_MODE = "DISABLED"`
- `/magwrite_uart_rx.started`: present
- `/magwrite_uart_rx.complete`: present
- `/magwrite_uart_tx.started`: present
- `/magwrite_uart_tx.complete`: present
- Every prior MagTag characterization and typing guard remains present.

Conclusion: **PASS** for the bounded, one-way Fruit Jam-to-MagTag deterministic
UART viewport feasibility boundary. This does not validate bidirectional UART,
acknowledgements, keyboard input, editing, storage, Wi-Fi, or production power.
