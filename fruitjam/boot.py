"""No filesystem remount occurs unless the one-shot UART mode is armed."""
import storage
try:
    import config
except ImportError:
    config = None
if config and config.ENABLE_UART_TEST and config.UART_TEST_MODE == "FRUITJAM_UART_VIEWPORT_TX":
    storage.remount("/", readonly=False)
