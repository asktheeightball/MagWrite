# Fruit Jam ↔ MagTag UART acknowledgement test

Status: **NOT RUN**

The software and deterministic host simulation are complete. This document
does not claim that the return wire, status UART, or physical acknowledgement
lifecycle has passed.

## Fixed configuration

- Fruit Jam RP2350B, CircuitPython 10.2.1
- Fruit Jam `board.A0` TX and verified accessible `board.A1` RX
- Original 2.9-inch ESP32-S2/UC8151D MagTag, CircuitPython 9.1.1
- MagTag `board.D10` RX and verified `board.A1` TX
- 115200 baud; protocol version 1
- Separately USB-powered; signal and common ground only
- Timeouts: hello 5 s, accepted 3 s, refresh start 8 s, refresh completion
  15 s, catch-up 18 s, whole run 60 s, display busy 20 s
- No automatic retry

## Intended wiring (not yet physically confirmed)

```text
Fruit Jam A0 signal -> MagTag D10 signal
MagTag A1 signal    -> Fruit Jam A1 signal
Fruit Jam GND       <-> MagTag GND
```

Fruit Jam A1 is the exposed three-pin analog/GPIO connector adjacent to A0.
Verify connector position or continuity, not cable colour. Leave every 3.3 V,
5 V, BAT, USB, and red power conductor disconnected.

## Independent guards

```text
Fruit Jam: /magwrite_uart_ack_tx.started
           /magwrite_uart_ack_tx.complete
MagTag:    /magwrite_uart_ack_rx.started
           /magwrite_uart_ack_rx.complete
```

All one-way UART, 20/50/100 refresh, and typing guards remain untouched. A
`.started` file is preserved on failure. Either new `.started` or `.complete`
guard prevents that entry point from running again.

## One guarded physical procedure

1. Back up both complete CIRCUITPY drives outside the repository.
2. Record every existing guard and confirm all old guards remain.
3. Inspect both boards, connectors, USB leads, and jumper insulation.
4. Reconfirm `dir(board)` exposes Fruit Jam A0/A1 and MagTag A1/D10.
5. Reconfirm connector positions and both full-duplex UART constructors.
6. Install the two signal wires and common ground shown above.
7. Confirm no power conductor joins the separately USB-powered boards.
8. Check for shorts, unstable power, heating, and wrong connector order.
9. Boot both devices with all activation disabled; capture refusal messages.
10. Open separate timestamped USB serial captures before either reset.
11. Arm and reset MagTag first with:

    ```python
    ENABLE_PHYSICAL_DISPLAY = True
    PHYSICAL_TEST_MODE = "MAGTAG_UART_ACK_RX"
    ENABLE_UART_RECEIVER = True
    ENABLE_UART_STATUS_TX = True
    UART_TEST_MODE = "MAGTAG_UART_ACK_RX"
    BIDIRECTIONAL_UART_TEST_MODE = "MAGTAG_UART_ACK_RX"
    ```

12. Confirm `uart_ack_rx_ready`.
13. Arm and reset Fruit Jam second with:

    ```python
    ENABLE_BIDIRECTIONAL_UART_TEST = True
    BIDIRECTIONAL_UART_TEST_MODE = "FRUITJAM_UART_ACK_TX"
    ```

14. Observe STATUS_HELLO; one complete lifecycle; revisions 2..5
    supersession; final revision 6; DISPLAY_CAUGHT_UP; and TEST_COMPLETE.
15. Confirm the final text and cursor and photograph where practical.
16. Stop immediately on any protocol, display, runtime, electrical, USB,
    timeout, overflow, unexpected flash, erasure, ghosting, border, or pixel
    concern. Preserve both `.started` guards and captures; do not retry.
17. Save both raw serial streams.
18. Restore every MagTag activation to false/`DISABLED` and both Fruit Jam
    bidirectional settings to false/`DISABLED`.
19. Confirm four new guards for PASS, unchanged old guards, and disabled
    configurations.
20. Do not delete guards or rerun without explicit authorization.

## Evidence record

Repository commit: pending implementation commit  
Fruit Jam serial: `docs/FRUITJAM_UART_ACK_SERIAL.jsonl` — NOT RUN  
MagTag serial: `docs/MAGTAG_UART_STATUS_SERIAL.jsonl` — NOT RUN  
Physical result: **NOT RUN**

Pending evidence includes run time, wiring confirmation, message counts,
discard/resynchronization metrics, final revisions/hash, refresh counts,
measured timings, visual observations, photograph filename or explicit
missing-photo statement, guard states, and restored configurations.
