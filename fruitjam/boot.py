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
