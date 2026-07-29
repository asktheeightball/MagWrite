"""No filesystem remount occurs unless the one-shot UART mode is armed."""
import storage
try:
    import config
except ImportError:
    config = None
if config and config.ENABLE_UART_TEST and config.UART_TEST_MODE == "FRUITJAM_UART_VIEWPORT_TX":
    storage.remount("/", readonly=False)
elif (
    config
    and getattr(config, "ENABLE_BIDIRECTIONAL_UART_TEST", False)
    and getattr(config, "BIDIRECTIONAL_UART_TEST_MODE", "DISABLED")
        == "FRUITJAM_UART_ACK_TX"
):
    storage.remount("/", readonly=False)
elif (
    config
    and getattr(config, "ENABLE_EDITOR_INTEGRATION_TEST", False)
    and getattr(config, "EDITOR_INTEGRATION_TEST_MODE", "DISABLED")
        == "FRUITJAM_EDITOR_INTEGRATION"
):
    storage.remount("/", readonly=False)
elif (
    config
    and getattr(config, "ENABLE_USB_KEYBOARD_TEST", False)
    and getattr(config, "USB_KEYBOARD_TEST_MODE", "DISABLED")
        == "FRUITJAM_USB_KEYBOARD"
):
    storage.remount("/", readonly=False)
# The development runtime is deliberately absent from this gate. It writes no
# guard, so it needs no writable filesystem, and leaving CIRCUITPY under the
# host's control is what makes it repeatable: saving a file restarts it.
