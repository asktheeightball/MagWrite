"""Copy as /boot.py only for the explicitly armed physical refresh test."""

import storage

try:
    import config
except ImportError:
    config = None

if (
    config is not None
    and config.ENABLE_PHYSICAL_DISPLAY
    and config.PHYSICAL_TEST_MODE in (
        "UC8151_20_UPDATE",
        "REFRESH_50",
        "REFRESH_100",
        "SINGLE_LINE_TYPING",
        "MAGTAG_UART_VIEWPORT_RX",
        "MAGTAG_UART_ACK_RX",
        "MAGTAG_EDITOR_DISPLAY",
        "MAGTAG_USB_KEYBOARD_DISPLAY",
        "MAGTAG_V1_RESPONSIVENESS_DISPLAY",
    )
):
    # Required only so the one-time guard can be persisted by CircuitPython.
    # While armed, CIRCUITPY may be read-only to the USB host.
    storage.remount("/", readonly=False)
