"""Host-safe display abstraction and physical-test activation checks."""


PHYSICAL_TEST_MODE = "UC8151_20_UPDATE"
REFRESH_50_MODE = "REFRESH_50"
REFRESH_100_MODE = "REFRESH_100"
SINGLE_LINE_TYPING_MODE = "SINGLE_LINE_TYPING"
UART_VIEWPORT_RX_MODE = "MAGTAG_UART_VIEWPORT_RX"
UART_ACK_RX_MODE = "MAGTAG_UART_ACK_RX"
EDITOR_DISPLAY_MODE = "MAGTAG_EDITOR_DISPLAY"
USB_KEYBOARD_DISPLAY_MODE = "MAGTAG_USB_KEYBOARD_DISPLAY"
# Guarded one-shot harness modes. Each claims a ``.started`` guard, so each needs
# a filesystem the board itself can write; ``hardware_test_boot.py`` remounts for
# exactly this tuple and a host test asserts the two agree.
APPROVED_TEST_MODES = (
    PHYSICAL_TEST_MODE,
    REFRESH_50_MODE,
    REFRESH_100_MODE,
    SINGLE_LINE_TYPING_MODE,
    UART_VIEWPORT_RX_MODE,
    UART_ACK_RX_MODE,
    EDITOR_DISPLAY_MODE,
    USB_KEYBOARD_DISPLAY_MODE,
)

# The repeatable development runtime. Kept out of APPROVED_TEST_MODES on purpose:
# it writes no guard, so it must *not* appear in the boot remount gate, and the
# filesystem stays under the host's control. See magtag/dev_display_runtime.py.
DEV_DISPLAY_MODE = "MAGTAG_DEV_DISPLAY"
DEV_MODES = (DEV_DISPLAY_MODE,)

# Every mode the display may be activated for, guarded or not.
ACTIVATION_MODES = APPROVED_TEST_MODES + DEV_MODES


class DisplayAdapter:
    def initialize(self):
        raise NotImplementedError

    def begin_refresh(self, framebuffer, full=False):
        raise NotImplementedError

    def is_busy(self):
        raise NotImplementedError

    def wait_until_idle(self, timeout_seconds):
        raise NotImplementedError

    def power_off(self):
        raise NotImplementedError


def validate_physical_test_activation(config, selected_mode):
    if getattr(config, "HARDWARE_COMPATIBILITY_DECISION", None) != "COMPATIBLE":
        raise RuntimeError("physical display refused: decision is not COMPATIBLE")
    if getattr(config, "DISPLAY_CONTROLLER", None) != "UC8151D":
        raise RuntimeError("physical display refused: controller is not UC8151D")
    if not getattr(config, "ENABLE_PHYSICAL_DISPLAY", False):
        raise RuntimeError("physical display refused: activation is disabled")
    if selected_mode not in ACTIVATION_MODES:
        raise RuntimeError("physical display refused: explicit test mode not selected")
    return True
