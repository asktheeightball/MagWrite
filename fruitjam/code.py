"""Fail-closed Fruit Jam UART viewport test entry point."""
import time
import config

if not config.ENABLE_UART_TEST or config.UART_TEST_MODE != "FRUITJAM_UART_VIEWPORT_TX":
    print('{"event":"uart_tx_refused","reason":"disabled"}')
    while True:
        time.sleep(3600)
if not config.UART_TX_PIN_ALIAS:
    raise RuntimeError("UART_TX_PIN_ALIAS must be physically confirmed")

import board
import busio
import json
import os
import storage
import supervisor
from magwrite_transport.diagnostics import log
from magwrite_transport.uart_sender import UartSender

START = "/magwrite_uart_tx.started"
COMPLETE = "/magwrite_uart_tx.complete"
if START[1:] in os.listdir("/") or COMPLETE[1:] in os.listdir("/"):
    raise RuntimeError("UART TX guard exists")
supervisor.runtime.autoreload = False
with open(START, "w") as handle:
    handle.write("claimed\n")
pin = getattr(board, config.UART_TX_PIN_ALIAS)
uart = busio.UART(tx=pin, rx=None, baudrate=config.UART_BAUD, timeout=0)
sender = UartSender(uart, log)
log({"event": "uart_tx_ready", "baud": config.UART_BAUD,
     "tx_alias": config.UART_TX_PIN_ALIAS,
     "startup_delay_seconds": config.STARTUP_DELAY_SECONDS})
time.sleep(config.STARTUP_DELAY_SECONDS)
sender.run(time.sleep, config.INTER_FRAME_DELAY_SECONDS, config.SCENARIO_DELAY_SECONDS)
summary = {"event": "uart_tx_summary", "result": "PASS",
           "frames_sent": sender.frames_sent, "bytes_sent": sender.bytes_sent}
log(summary)
with open(COMPLETE, "w") as handle:
    handle.write(json.dumps(summary))
try:
    storage.remount("/", readonly=True)
except RuntimeError as error:
    log({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
