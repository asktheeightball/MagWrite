# Fruit Jam application

This directory is copied to a physically identified Adafruit Fruit Jam. From V1.6
it ships as the **writing appliance**: copy it onto CIRCUITPY, connect one USB-C
cable, and the device runs. There is no flag to set and no start order. See
[../docs/STANDALONE.md](../docs/STANDALONE.md).

```text
code.py                  dispatcher: armed harnesses first, then the runtime
boot.py                  remounts only for an armed one-shot harness
config.py                bounded settings; standalone enabled, harnesses not
dev_runtime.py           the runtime, in the STANDALONE or DEVELOPMENT profile
magwrite_transport/      editor, layout, viewport, protocol, shell, storage
hardware_*_test.py       guarded one-shot harnesses, each disabled by name
```

## The gates that still apply

Every guarded harness ships disabled, needs both its enable flag and its own mode
string, claims a one-shot `.started` guard, and **wins over the standalone
default** when armed — `code.py` checks all of them first. `boot.py` remounts the
filesystem for exactly those modes and for nothing else, so the runtime never
takes CIRCUITPY away from the host.

`UART_TX_PIN_ALIAS` and `UART_RX_PIN_ALIAS` must be names the board actually
exposes; check `dir(board)` on the board in hand. Never connect a red power wire
between independently USB-powered boards — on both boards that conductor is 5 V.
