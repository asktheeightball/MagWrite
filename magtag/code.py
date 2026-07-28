"""Fail-closed device dispatcher for explicitly armed physical harnesses."""

import time
import config

print('{"event":"boot","circuitpython":"%s"}' % config.CIRCUITPYTHON_VERSION)
if (
    config.ENABLE_PHYSICAL_DISPLAY
    and getattr(config, "ENABLE_UART_RECEIVER", False)
    and getattr(config, "ENABLE_UART_STATUS_TX", False)
    and config.PHYSICAL_TEST_MODE == "MAGTAG_UART_ACK_RX"
    and getattr(config, "UART_TEST_MODE", "DISABLED") == "MAGTAG_UART_ACK_RX"
    and getattr(config, "BIDIRECTIONAL_UART_TEST_MODE", "DISABLED") == "MAGTAG_UART_ACK_RX"
):
    import hardware_uart_ack_test
elif (
    config.ENABLE_PHYSICAL_DISPLAY
    and getattr(config, "ENABLE_UART_RECEIVER", False)
    and config.PHYSICAL_TEST_MODE == "MAGTAG_UART_VIEWPORT_RX"
    and getattr(config, "UART_TEST_MODE", "DISABLED") == "MAGTAG_UART_VIEWPORT_RX"
):
    import hardware_uart_viewport_test
else:
    print('{"event":"physical_test_refused","reason":"disabled_or_mode_mismatch"}')
    while True:
        time.sleep(3600)
