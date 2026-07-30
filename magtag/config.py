"""MagTag configuration. Ships as the standalone writing appliance. V1.6.

Every *harness* in this file still ships disabled and still has to be armed by
name. What changed in V1.6 is the default when nothing is armed: the board now
comes up as the product rather than refusing to come up at all.

``ENABLE_PHYSICAL_DISPLAY`` is therefore ``True``. That is not a weakening of the
fail-closed gate, and the gate is unchanged: a harness needs both this flag *and*
its own ``PHYSICAL_TEST_MODE`` string, and none of those strings is set here. What
this flag now means is what it always should have meant on a finished device --
this board is allowed to drive the panel it was built around. The compatibility
decision above still governs whether it may, and it is still checked first.

``MAGTAG_STANDALONE`` is deliberately absent from the boot remount tuple in
``hardware_test_boot.py``, exactly as ``MAGTAG_DEV_DISPLAY`` is: the runtime
writes no guard, so it needs no writable filesystem, and CIRCUITPY stays under the
host's control. A host test asserts that tuple against the approved harness modes.
"""

CIRCUITPYTHON_VERSION = "9.1.1"
HARDWARE_COMPATIBILITY_DECISION = "COMPATIBLE"
MAGTAG_REVISION = "ORIGINAL_MAGTAG_2.9"
DISPLAY_CONTROLLER = "UC8151D"
ENABLE_PHYSICAL_DISPLAY = True
PHYSICAL_TEST_MODE = "MAGTAG_STANDALONE"
ENABLE_UART_RECEIVER = True
UART_TEST_MODE = "DISABLED"
UART_RX_PIN_ALIAS = "D10"
UART_BAUD = 115200
UART_READ_BUDGET = 256
ENABLE_UART_STATUS_TX = True
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
# ------------------------------------------------ the standalone default, V1.6
# The same runtime as above, on a device with no console and no operator. Set
# ENABLE_STANDALONE False and this board refuses to start, which is a thing to do
# on purpose and never a thing to leave set.
ENABLE_STANDALONE = True
STANDALONE_DISPLAY_MODE = "MAGTAG_STANDALONE"
# How long the panel shows only STARTING before it says it is waiting for the
# writer board. Mirrors dev_display_runtime.DEFAULT_STARTUP_WAIT_SECONDS, which
# carries the reasoning; a host test asserts the two agree. Above the 9.05 s a
# measured cold boot took, so an ordinary start never draws the second screen.
STANDALONE_DISPLAY_WAIT_SECONDS = 15.0
# ---------------------------------------------------------- MagTag buttons
# V1.5. Enabled by default, unlike every harness in this repository, and for the
# same reason persistence and the shell are: this is the product's primary
# control surface, not a hardware experiment. It claims no guard, writes nothing,
# remounts nothing, and reads four GPIOs. A pin alias the board does not expose
# is a reported degraded mode -- the display runs and the keyboard still drives
# the shell -- never a refusal to start.
ENABLE_MAGTAG_BUTTONS = True
# The four front buttons, left to right, and the normalized action each sends.
# Back-to-menu and select are the outer two so a thumb cannot confuse them with
# the movement pair between them. Only names the board actually exposes are
# trusted, exactly as for the UART and microSD pins.
BUTTON_MENU_PIN_ALIAS = "BUTTON_A"
BUTTON_UP_PIN_ALIAS = "BUTTON_B"
BUTTON_DOWN_PIN_ALIAS = "BUTTON_C"
BUTTON_SELECT_PIN_ALIAS = "BUTTON_D"
# These mirror magwrite/buttons.py, which is the single source of truth and
# carries the reasoning behind each value; a host test asserts the two agree.
BUTTON_DEBOUNCE_SECONDS = 0.025
BUTTON_MINIMUM_INTERVAL_SECONDS = 0.25
FULL_REFRESH_INTERVAL = 50
EVENT_QUEUE_CAPACITY = 128
MAX_LINES = 64
MAX_CHARS = 8192
