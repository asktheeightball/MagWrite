"""Copy to config_local.py and confirm the physical board before enabling."""

CIRCUITPYTHON_VERSION = "9.1.1"
HARDWARE_COMPATIBILITY_DECISION = "COMPATIBLE"
MAGTAG_REVISION = "ORIGINAL_MAGTAG_2.9"
DISPLAY_CONTROLLER = "UC8151D"
ENABLE_PHYSICAL_DISPLAY = False
PHYSICAL_TEST_MODE = "DISABLED"
ENABLE_UART_RECEIVER = False
UART_TEST_MODE = "DISABLED"
UART_RX_PIN_ALIAS = "D10"
UART_BAUD = 115200
UART_READ_BUDGET = 256
ENABLE_UART_STATUS_TX = False
BIDIRECTIONAL_UART_TEST_MODE = "DISABLED"
UART_TX_PIN_ALIAS = "A1"
UART_STATUS_QUEUE_CAPACITY = 32
UART_ACK_TEST_TIMEOUT_SECONDS = 60
UART_DISPLAY_BUSY_TIMEOUT_SECONDS = 20
EDITOR_DISPLAY_TEST_MODE = "DISABLED"
EDITOR_TEST_TIMEOUT_SECONDS = 150
# Bounds only the idle wait between "ready" and the Fruit Jam's first frame,
# which is operator-paced and must not be charged to EDITOR_TEST_TIMEOUT_SECONDS.
EDITOR_ARMING_TIMEOUT_SECONDS = 900
USB_KEYBOARD_DISPLAY_TEST_MODE = "DISABLED"
# A live typing run is operator-paced at both ends, so both bounds are larger
# than the scripted editor run's. The arming wait keeps its own separate bound.
USB_KEYBOARD_DISPLAY_TIMEOUT_SECONDS = 2700
USB_KEYBOARD_ARMING_TIMEOUT_SECONDS = 1800
# Repeatable development runtime. Disabled by default like every harness, but it
# claims no one-shot guard, is absent from the boot remount gate, and may be
# started and stopped as often as development needs. It has no run clock: a
# development session is open-ended and is stopped by the operator, not by a
# certification budget. See magtag/dev_display_runtime.py.
DEV_DISPLAY_RUNTIME_MODE = "DISABLED"
FULL_REFRESH_INTERVAL = 50
EVENT_QUEUE_CAPACITY = 128
MAX_LINES = 64
MAX_CHARS = 8192
