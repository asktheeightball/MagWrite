ENABLE_UART_TEST = False
UART_TEST_MODE = "DISABLED"
UART_TX_PIN_ALIAS = "A0"
UART_BAUD = 115200
INTER_FRAME_DELAY_SECONDS = 0.15
SCENARIO_DELAY_SECONDS = 4.5
STARTUP_DELAY_SECONDS = 3.0
ENABLE_BIDIRECTIONAL_UART_TEST = False
BIDIRECTIONAL_UART_TEST_MODE = "DISABLED"
UART_RX_PIN_ALIAS = "A1"
UART_READ_BUDGET = 256
UART_ACK_TEST_TIMEOUT_SECONDS = 60
UART_ACK_TRACKER_CAPACITY = 16
STATUS_HELLO_TIMEOUT_SECONDS = 5.0
FRAME_ACCEPTED_TIMEOUT_SECONDS = 3.0
REFRESH_STARTED_TIMEOUT_SECONDS = 8.0
REFRESH_COMPLETED_TIMEOUT_SECONDS = 15.0
DISPLAY_CAUGHT_UP_TIMEOUT_SECONDS = 18.0
ENABLE_EDITOR_INTEGRATION_TEST = False
EDITOR_INTEGRATION_TEST_MODE = "DISABLED"
EDITOR_EVENT_QUEUE_CAPACITY = 64
EDITOR_ACK_TRACKER_CAPACITY = 96
EDITOR_TEST_TIMEOUT_SECONDS = 240
ENABLE_USB_KEYBOARD_TEST = False
USB_KEYBOARD_TEST_MODE = "DISABLED"
USB_KEYBOARD_QUEUE_CAPACITY = 64
USB_KEYBOARD_ACK_TRACKER_CAPACITY = 128
USB_KEYBOARD_MAX_EVENTS = 500
# Bounded USB polling: at most four reports per loop, each with a short read
# timeout, so a silent keyboard never blocks display polling.
USB_KEYBOARD_POLL_BUDGET = 4
USB_KEYBOARD_READ_TIMEOUT_MS = 2
# Adaptive display pacing. These mirror magwrite_transport/pacing.py, which is
# the single source of truth and carries the measured panel numbers behind each
# value; a host test asserts the two agree. Fifty partial refreshes remains the
# binding physical ceiling.
USB_KEYBOARD_COALESCE_SECONDS = 0.25
USB_KEYBOARD_QUIET_SECONDS = 0.6
USB_KEYBOARD_CAUGHT_UP_MIN_SEND_SECONDS = 1.3
USB_KEYBOARD_SUSTAINED_MIN_SEND_SECONDS = 2.6
# "AUTO" identifies the keyboard from its USB descriptor and applies a recorded
# device layout if one matches; anything unrecognised gets standard HID.
USB_KEYBOARD_LAYOUT = "AUTO"
# Repeatable development runtime. Disabled by default like every harness, but
# unlike them it claims no one-shot guard, never remounts the filesystem, and may
# be started and stopped as often as development needs. See fruitjam/dev_runtime.py.
ENABLE_DEV_RUNTIME = False
DEV_RUNTIME_MODE = "DISABLED"
# Generous rather than absent: a development session is open-ended, but a board
# left typing into a UART nobody is watching should still give up eventually.
DEV_RUNTIME_IDLE_TIMEOUT_SECONDS = 1800
DEV_RUNTIME_SESSION_TIMEOUT_SECONDS = 7200
# The keyboard event budget is a bound on the adapter, not a certification
# ceiling, so a development session gets a much larger one than a bounded run.
DEV_RUNTIME_MAX_EVENTS = 100000
# A live run is operator-paced, so it is abandoned only after a long silence.
USB_KEYBOARD_IDLE_TIMEOUT_SECONDS = 600
USB_KEYBOARD_SESSION_TIMEOUT_SECONDS = 2700
# ------------------------------------------------------- microSD persistence
# Enabled by default, unlike the harnesses, because persistence is a product
# feature rather than a hardware experiment: a missing or unmountable card is a
# reported degraded mode, not a refusal to start. Setting this False runs the
# editor with no storage at all, which is also how the pre-V1.2 behaviour is
# reproduced exactly.
ENABLE_PERSISTENCE = True
# Pin aliases follow the same rule as the UART pins: only a name the board
# actually exposes is trusted. These four were read off the board in hand on
# 2026-07-30 with `tools/fruitjam_sd_probe.py`, on Adafruit CircuitPython 10.2.1
# / adafruit_fruit_jam / UID FFDBA7B15146C218, which reports:
#
#   SDA, SDIO_CLOCK, SDIO_COMMAND, SDIO_DATA0..3,
#   SD_CARD_DETECT, SD_CS, SD_MISO, SD_MOSI, SD_SCK
#
# The card is on the **dedicated** SPI bus, not the shared board.SPI(). The
# dedicated aliases are confirmed working: busio.SPI(SD_SCK, SD_MOSI, SD_MISO)
# plus sdcardio.SDCard(bus, SD_CS) initialises a real card. Leaving these None
# would have used board.SPI(), which is unproven here, so they are set
# explicitly rather than left to a default that happened to be untested.
SD_CS_PIN_ALIAS = "SD_CS"
SD_SCK_PIN_ALIAS = "SD_SCK"
SD_MOSI_PIN_ALIAS = "SD_MOSI"
SD_MISO_PIN_ALIAS = "SD_MISO"
# Deliberately None even though the board exposes SD_CARD_DETECT. On this
# firmware the pin is already claimed before user code runs -- constructing a
# DigitalInOut on it raises "SD_CARD_DETECT in use" -- so enabling it would only
# produce a noise diagnostic on every boot. Card presence is inferred from
# whether the card answers instead, which is the fallback the mount path was
# built with. Revisit if a later CircuitPython release releases the pin.
SD_CARD_DETECT_PIN_ALIAS = None
SD_MOUNT_POINT = "/sd"
DOCUMENT_ROOT = "/sd/magwrite"
# Refuse to append below this much free space. A journal append that fails
# halfway is recoverable by design; a full card is not a state to discover one
# record at a time.
DOCUMENT_RESERVE_BYTES = 32768
# These mirror magwrite_transport/persistence.py, which is the single source of
# truth and carries the reasoning behind each value; a host test asserts the two
# agree. Nothing may hard-code an autosave interval anywhere else.
AUTOSAVE_IDLE_SECONDS = 1.0
AUTOSAVE_MAX_AGE_SECONDS = 2.0
AUTOSAVE_REVISIONS = 12
CHECKPOINT_RECORDS = 24
CHECKPOINT_MAX_RECORDS = 48
CHECKPOINT_MAX_AGE_SECONDS = 120.0
CHECKPOINT_IDLE_SECONDS = 3.0
# ----------------------------------------------------------- MagWrite shell
# Enabled by default for the same reason persistence is: the shell is the product
# path, not a hardware experiment. Setting this False runs the editor with no
# shell at all, which is exactly how the V1.2 behaviour -- and every viewport
# payload the physical runs measured -- is reproduced.
#
# With the shell on, the finish gesture (Escape, or Keyboard Application on a 40%
# board) means *back* rather than stop: it leaves the editor through the save
# screen, and from the main menu it is still the clean stop. Ctrl-S is unchanged.
ENABLE_SHELL = True
# "LATEST" opens the most recent draft the card holds; "NEW" starts an empty
# document and discards the stored one. Opening the latest draft is the default
# because losing work to a mode switch is the failure this phase exists to
# prevent.
DOCUMENT_OPEN_MODE = "LATEST"
