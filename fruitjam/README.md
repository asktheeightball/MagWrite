# Fruit Jam UART viewport harness

This directory is copied to a physically identified Adafruit Fruit Jam only
after checking `dir(board)` on that board. It is disabled by default. Set the
confirmed `UART_TX_PIN_ALIAS`, then arm `ENABLE_UART_TEST` and select
`FRUITJAM_UART_VIEWPORT_TX` for one guarded run. Never connect a red power wire
between independently USB-powered boards.
