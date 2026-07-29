"""Fail-closed device dispatcher for explicitly armed physical harnesses."""

import time
import config

print('{"event":"boot","circuitpython":"%s"}' % config.CIRCUITPYTHON_VERSION)
if (
    config.ENABLE_PHYSICAL_DISPLAY
    and getattr(config, "ENABLE_UART_RECEIVER", False)
    and getattr(config, "ENABLE_UART_STATUS_TX", False)
    and config.PHYSICAL_TEST_MODE == "MAGTAG_DEV_DISPLAY"
    and getattr(config, "DEV_DISPLAY_RUNTIME_MODE", "DISABLED")
        == "MAGTAG_DEV_DISPLAY"
):
    # The repeatable development runtime, not a guarded harness. It returns when
    # the operator stops it, so this branch is terminal on its own rather than
    # relying on the imported module never returning.
    import dev_display_runtime  # noqa: F401 - imported for its side effects
    print('{"event":"dev_display_exited","restartable":true}')
    while True:
        time.sleep(3600)
elif (
    config.ENABLE_PHYSICAL_DISPLAY
    and getattr(config, "ENABLE_UART_RECEIVER", False)
    and getattr(config, "ENABLE_UART_STATUS_TX", False)
    and config.PHYSICAL_TEST_MODE == "MAGTAG_USB_KEYBOARD_DISPLAY"
    and getattr(config, "USB_KEYBOARD_DISPLAY_TEST_MODE", "DISABLED")
        == "MAGTAG_USB_KEYBOARD_DISPLAY"
):
    import hardware_usb_keyboard_display_test
elif (
    config.ENABLE_PHYSICAL_DISPLAY
    and getattr(config, "ENABLE_UART_RECEIVER", False)
    and getattr(config, "ENABLE_UART_STATUS_TX", False)
    and config.PHYSICAL_TEST_MODE == "MAGTAG_EDITOR_DISPLAY"
    and getattr(config, "EDITOR_DISPLAY_TEST_MODE", "DISABLED")
        == "MAGTAG_EDITOR_DISPLAY"
):
    import hardware_editor_display_test
elif (
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
