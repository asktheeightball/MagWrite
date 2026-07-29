# Fruit Jam Live USB HID Keyboard Test

**Status: NOT RUN**

This is one bounded integrated smoke test of the first *interactive* MagWrite
writing prototype: a real USB HID keyboard typing into the authoritative Fruit
Jam editor while the MagTag display trails and catches up.

It is not a new qualification campaign. Detailed HID, keymap, repeat, adapter,
and scheduling correctness is owned by the host suite; this device run exists
only to confirm that a real keyboard, the real USB host stack, and the real
e-paper path work together.

Every field in the Results section must be filled in from observed evidence
only. Nothing in that section may be written in advance of the run.

## Repository state

| Item | Value |
| --- | --- |
| Repository | `asktheeightball/MagWrite` |
| Branch | `main` |
| Starting commit | `040af09` |
| Host tests at `040af09` (baseline) | 253/253 pass |
| Host tests at the implementation commit | 447/447 pass |
| `python -m compileall -q magtag fruitjam host-tests` | pass |
| `python tools/validate_uart_harness.py` | pass, output byte-identical to baseline |
| `git diff --check` | pass |

## USB host discovery gate

Performed on the real Fruit Jam over the serial REPL **before** the adapter was
written. No descriptor value below is inferred or assumed; every one was read
off the device.

| Item | Observed |
| --- | --- |
| `board.board_id` | `adafruit_fruit_jam` |
| CircuitPython | 10.2.1, 2026-05-13 build, `RP2350` |
| Board UID | `FFDBA7B15146C218` |
| `usb` / `usb.core` | present |
| `usb_host` | present (`Port`, `set_user_keymap`) |
| `usb_hid` | present (device-side; not used by this phase) |
| `max3421e` | **absent** — the host port is native, not an external controller |
| `adafruit_usb_host_descriptors` | **absent**, and `/lib` is empty |
| `usb.core` surface | `Device`, `USBError`, `USBTimeoutError`, `find` |
| `usb.core.Device` surface | `idVendor`, `idProduct`, `manufacturer`, `product`, `serial_number`, `bus`, `port_numbers`, `speed`, `set_configuration`, `read`, `write`, `ctrl_transfer`, `is_kernel_driver_active`, `detach_kernel_driver`, `attach_kernel_driver`, `deinit` |

Because `adafruit_usb_host_descriptors` is not installed, descriptors are read
with a standard GET_DESCRIPTOR control transfer and parsed in-repo by
`magwrite_transport/usb_hid_descriptors.py`. This phase adds **no** third-party
dependency and no new licence obligation.

### Observed device identity

| Item | Observed |
| --- | --- |
| Devices enumerated | 1 |
| `idVendor` | `0x36B0` |
| `idProduct` | `0x3002` |
| `manufacturer` | `RDMCTMZT` |
| `product` | `Wireless 2.4G Dongle` |
| `serial_number` | `19971217` |
| Bus / port numbers / speed | 1 / `(1,)` / 2 (full speed) |
| `bDeviceClass` / `SubClass` / `Protocol` | 0 / 0 / 0 (per-interface) |
| `bMaxPacketSize0` | 64 |
| `bNumConfigurations` | 1 |
| Configuration `wTotalLength` | 98 bytes |
| `bNumInterfaces` | 3 |

Raw device descriptor:

```text
1201000200000040B0360230040101020301
```

Raw configuration descriptor, all 98 bytes:

```text
09026200030100A0FA
09040000010301010009211101000122440007058103080001
090401000203000000092111010001222200070582032000010705030320000109
040200020300000009211101000122D3000705840340000107050503400001
```

Parsed:

| Interface | Class | SubClass | Protocol | Endpoints | Report descriptor |
| --- | --- | --- | --- | --- | --- |
| **0** | 3 (HID) | **1 (Boot)** | **1 (Keyboard)** | `0x81` IN, interrupt, 8 bytes, 1 ms | 68 bytes |
| 1 | 3 (HID) | 0 | 0 | `0x82` IN 32 B, `0x03` OUT 32 B | 34 bytes |
| 2 | 3 (HID) | 0 | 0 | `0x84` IN 64 B, `0x05` OUT 64 B | 211 bytes |

**The receiver exposes three HID interfaces and only interface 0 is a
keyboard.** Selection is therefore by the HID class triple
(class 3 / subclass 1 / protocol 1), never "the first HID interface wins".
Interfaces 1 and 2 were observed emitting only zero-payload idle reports with
report IDs 2, 3, 4, and 6, and are ignored entirely.

`is_kernel_driver_active(0)` returned **True**: CircuitPython 10's own USB host
keyboard driver claims the boot interface for the REPL, so
`detach_kernel_driver(0)` is required before the interrupt endpoint can be read.
Interfaces 1 and 2 were not claimed.

### Observed report format

The device is a **boot-protocol keyboard**, confirmed by descriptor and by a
successful `SET_PROTOCOL(boot)` control transfer. `SET_IDLE(indefinite)` also
succeeded, so the device reports only on change.

```text
byte 0     modifier bitmap
byte 1     reserved, observed always zero
bytes 2-7  up to six concurrently held usage IDs, zero-padded
```

Real reports captured from live typing on endpoint `0x81`:

```text
00 00 0B 00 00 00 00 00     h
00 00 07 00 00 00 00 00     d
00 00 04 00 00 00 00 00     a
00 00 04 07 00 00 00 00     a + d held
00 00 04 07 16 00 00 00     a + d + s held  (three-key rollover)
00 00 13 00 00 00 00 00     p
00 00 13 65 00 00 00 00     p + Application/Menu
00 00 00 00 00 00 00 00     all released
```

An idle read raises `usb.core.USBTimeoutError`, which is the normal "no key
activity" case: 22,298 clean timeouts were observed across a 45-second window at
a 2 ms read timeout, alongside 25 real reports. That confirms polling is
non-blocking at millisecond granularity.

The exact 98-byte configuration descriptor above is a **host-test fixture**
(`host-tests/keyboard_simulator.py`), so descriptor parsing and interface
selection are proven in CPython against real observed bytes.

## Input architecture

```text
Real USB HID keyboard + 2.4 GHz receiver
        |
        v
Fruit Jam native USB host port
        |
        v
UsbHostKeyboardBackend            (usb_host_backend.py — the only hardware module)
        +--> detach_kernel_driver(0)
        +--> set_configuration
        +--> SET_PROTOCOL(boot), SET_IDLE(indefinite)
        +--> read(0x81) -> 8-byte boot report
        |
        v
HidKeyboardTranslator             (hid_keyboard.py)
        +--> duplicate report suppression
        +--> rollover / POST-failure rejection
        +--> press / release / held-key tracking
        |
        v
hid_keymap.translate              (hid_keymap.py)
        +--> Shift, Caps Lock, Shift+Caps
        +--> unsupported usage -> None, counted, ignored
        |
        v
KeyRepeat                         (keyboard_repeat.py)
        +--> deliberate delay then interval, bounded catch-up
        |
        v
UsbKeyboardAdapter                (usb_keyboard_adapter.py)
        +--> monotonic sequence numbering
        +--> normalized InputEvent
        |
        v
BoundedEventQueue, explicit overflow          (editor.py — unchanged)
        |
        v
Fruit Jam authoritative MultilineEditor       (editor.py — unchanged)
        |
        v
Layout and viewport builder                   (unchanged)
        |
        v
Bidirectional UART transport                  (unchanged)
        |
        v
MagTag display-only terminal                  (unchanged)
```

Nothing downstream of the queue was modified. The editor, the layout, the
viewport builder, the protocol, and the acknowledgement tracker are the
physically verified modules from the editor phase, reused byte-for-byte. The
scripted `EditorSession` also remains untouched; `LiveTypingSession` is a
sibling that swaps only the input source.

The adapter owns no document, cursor, layout, or revision state, and the editor
never sees a USB or HID concept.

## HID translation coverage

Supported and normalized:

```text
a-z  A-Z  0-9  space
Enter (Return and Keypad Enter)
Backspace  Delete
Left  Right  Up  Down  Home  End
Shift (either)  Caps Lock
.  ,  '  -  :  ;  !  ?  "  (  )  /  <  >
```

`Escape` is the deliberate **finish key**: it ends the live run and produces no
editor event.

Every character the keymap can emit is present in the proven 3x5 glyph table; a
host test asserts that directly. Deliberately unsupported, ignored with a
bounded `usb_keyboard_unsupported_usage` diagnostic and never crashing:
function keys, Tab, Insert, Page Up/Down, Application/Menu, keypad digits, and
the shifted forms with no glyph (`@ # $ % ^ & * _ + = [ ] { } \ | ~` and
backtick).

### Glyph additions

Thirty glyphs were added to `magtag/magwrite/test_pattern.py`: lowercase `a-z`
plus `;` `"` `(` `)`. The 3x5 cell is unchanged and every previously proven
glyph is byte-identical, so all earlier rendered frames remain bit-identical —
confirmed by `tools/validate_uart_harness.py` producing output identical to the
baseline (`DC12F5C9` and `2171BE7F`).

Lowercase in a 3x5 cell is necessarily compact: an x-height body on rows 1-3,
ascenders reaching row 0, descenders reaching row 4. **Legibility of lowercase
at this cell size is an open question for the operator to judge**, and is
recorded as a visual observation below rather than assumed. Host tests assert
every added glyph is distinct from every other glyph. One pre-existing
collision is documented and deliberately left alone: `O` and `0` already shared
a bitmap before this phase, and changing either would break bit-identity with
the verified editor frames.

## Press, release, and repeat behaviour

| Rule | Implementation |
| --- | --- |
| One event on initial press | new usages are those absent from the previous report |
| Identical reports never repeat anything | byte-identical report is counted as a duplicate and discarded |
| Deliberate repeat only | 500 ms delay, then 80 ms interval, configurable |
| Repeat eligibility | printable characters, Enter, Backspace, Delete, all four arrows |
| Home and End never repeat | both are idempotent; repeating them would only burn frames |
| Newest press owns the repeat | `KeyRepeat.arm` replaces the previous owner |
| Release cancels the repeat | immediately, on the report that drops the usage |
| Modifiers alone | never create an editor event |
| Caps Lock | toggles once per press, deterministic, no editor event |
| Shift | read from the current report's modifier byte |
| Shift + Caps Lock | returns letters to lowercase |
| Simultaneous non-modifier keys | resolved in report-array order, deterministically |
| Rollover / POST failure | emits nothing, preserves held state, counted |
| Persistent rollover | stops the run past a tolerance of 8 consecutive reports |
| Reconnect | clears held keys and the Caps latch; never replays a held key |
| Catch-up after a stall | bounded to 4 repeats, then resynchronizes |

All timing constants live in `keyboard_repeat.py`.

## Connection behaviour

States: `NO_DEVICE`, `ENUMERATING`, `READY`, `DISCONNECTED`, `ERROR`.

There is no unbounded reconnect loop. An open attempt is permitted at most once
per second and at most 30 times in total; once exhausted the machine latches
`ERROR` and the harness fails closed rather than spinning. A disconnect clears
held keys and cancels any repeat, so a reconnect starts from a known state and
cannot replay a key that was held when the link dropped.

Automatic reconnect is desirable but **not required for PASS**. The minimum PASS
path is one stable connected session.

## Authorised physical limits

| Limit | Ceiling | Host simulation at 60 WPM |
| --- | --- | --- |
| Normalized keyboard events | 500 | 177 |
| Viewport frames | 100 | 29 |
| Protocol frames per direction | 200 | 31 sent, 117 received |
| Partial refreshes | 50 | 28 |
| Initial full refreshes | 1 | 1 |
| Guarded physical attempts | 1 | — |

**The 100-frame viewport ceiling is not the binding one.** Almost every accepted
frame is rendered, so 100 frames would demand roughly 99 partial refreshes
against a ceiling of 50, and roughly 400 status frames against a ceiling of 200
per direction. Fifty partial refreshes is the real bound.

Transmission is therefore paced to the panel at a 2.6 s minimum send interval —
the same pacing the physically verified editor scenarios used — rather than to
the typing rate. A keypress never gets its own frame, and a pause costs nothing
because a frame is only built when the viewport state actually changed. If a
typing pattern would still exceed a ceiling, the harness stops with an explicit
stop condition rather than quietly over-running an authorised physical limit.

A second attempt requires explicit authorisation. The harness never retries
automatically.

## Activation

Both devices ship disabled and fail closed.

Fruit Jam `config.py`:

```python
ENABLE_USB_KEYBOARD_TEST = False
USB_KEYBOARD_TEST_MODE = "DISABLED"
```

MagTag `config.py`:

```python
ENABLE_PHYSICAL_DISPLAY = False
ENABLE_UART_RECEIVER = False
ENABLE_UART_STATUS_TX = False
PHYSICAL_TEST_MODE = "DISABLED"
USB_KEYBOARD_DISPLAY_TEST_MODE = "DISABLED"
```

To arm the run, set the Fruit Jam to `ENABLE_USB_KEYBOARD_TEST = True` and
`USB_KEYBOARD_TEST_MODE = "FRUITJAM_USB_KEYBOARD"`, and the MagTag to
`ENABLE_PHYSICAL_DISPLAY = True`, `ENABLE_UART_RECEIVER = True`,
`ENABLE_UART_STATUS_TX = True`,
`PHYSICAL_TEST_MODE = "MAGTAG_USB_KEYBOARD_DISPLAY"`, and
`USB_KEYBOARD_DISPLAY_TEST_MODE = "MAGTAG_USB_KEYBOARD_DISPLAY"`.

Physical execution fails closed unless the correct mode is selected, both guards
are absent, both UART pin aliases are confirmed, the protocol constants match,
the USB host adapter initializes, the UART initializes, the pinned driver hash
verifies, and the display controller is compatible.

## Guards

New, independent guards for this phase:

| Device | Started | Complete |
| --- | --- | --- |
| Fruit Jam | `/magwrite_usb_keyboard.started` | `/magwrite_usb_keyboard.complete` |
| MagTag | `/magwrite_usb_keyboard_display.started` | `/magwrite_usb_keyboard_display.complete` |

Either device refuses to run if its own started or complete guard already
exists. No prior guard is read, written, renamed, or deleted. The twenty guards
from earlier phases must remain byte-identical.

## Hardware

| Item | Fruit Jam | MagTag |
| --- | --- | --- |
| Board | Adafruit Fruit Jam | original Adafruit MagTag 2.9-inch |
| MCU | RP2350B | ESP32-S2 |
| CircuitPython | 10.2.1 | 9.1.1 |
| Role | authoritative controller and USB HID host | display terminal |
| UART TX | `board.A0` | `board.A1` |
| UART RX | `board.A1` | `board.D10` |
| Display controller | — | UC8151D |

### Wiring

```text
Fruit Jam A0 signal --> MagTag D10 signal
MagTag A1 signal    --> Fruit Jam A1 signal
Fruit Jam GND       --- MagTag GND
```

Both boards are powered separately over USB. There is no inter-board power
conductor. Baud rate is 115200, 8N1. The keyboard receiver is in the Fruit Jam
USB host (type-A) port.

### Pinned display driver

The UC8151 driver is unmodified at upstream commit
`61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`, SHA-256
`A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E`. The MagTag
entry point verifies this hash before it constructs the UART or touches the
panel, and fails closed on mismatch.

## Live physical scenarios

All input is typed by hand on the real keyboard. Nothing is automated.

### Scenario 1 — connection and basic typing

Type exactly:

```text
MAGWRITE USB KEYBOARD TEST
```

Verify the exact characters, the spaces, and the cursor position.

### Scenario 2 — punctuation and Shift

Type exactly:

```text
Hello, MagWrite! It's working.
```

Verify Shift, lowercase, uppercase, comma, apostrophe, exclamation, and period.

### Scenario 3 — correction

Type the deliberate error:

```text
TODAY I WROTE A JORUNAL ENTRY
```

Correct it with the real keyboard to:

```text
TODAY I WROTE A JOURNAL ENTRY
```

using arrows, Backspace, Delete, Home, and End as appropriate.

### Scenario 4 — multiline editing

Type at least three logical lines using Enter. Verify line splitting, cursor
movement, Backspace at line start, Delete at line end, Up, Down, Home, and End.

### Scenario 5 — typing while the display is busy

Type continuously for at least one refresh interval. Verify no lost keypresses,
no duplicated keypresses, that input continues while the MagTag refreshes, that
stale viewport states are coalesced, and that the final display catches up.

### Scenario 6 — final usable note

Finish with a short realistic note. Press **Escape** to end the run. The final
screen must be visually approved by the operator.

## Procedure

1. Confirm the working tree is clean and record the commit.
2. Back up both `CIRCUITPY` volumes; record drive letters and COM ports.
3. Confirm both devices are disabled and all four new guard files are absent.
4. Inventory every prior guard by SHA-256.
5. Confirm A0→D10, A1→A1, and common ground; confirm no inter-board power
   conductor; keep both boards separately USB-powered.
6. Connect the keyboard receiver to the Fruit Jam USB host port and confirm the
   keyboard is powered on.
7. Copy `magtag/` to the MagTag volume and `fruitjam/` to the Fruit Jam volume.
8. Boot both devices disabled and confirm fail-closed diagnostics.
9. Start two separate timestamped serial captures.
10. Arm the MagTag first, reset it once, and confirm `usb_keyboard_display_ready`.
11. Arm the Fruit Jam second, reset it once, and confirm `usb_keyboard_test_ready`
    followed by `usb_keyboard_connected` and a `READY` state.
12. Type the six scenarios by hand. Press Escape to finish.
13. Inspect the final screen and record the visual observations.
14. Record both summaries, restore both configurations to disabled, confirm all
    four new guards exist, and confirm every prior guard is untouched.

Do not retry automatically. One guarded physical attempt without explicit
authorisation.

## Stop conditions

Stop immediately and mark FAIL or INCONCLUSIVE on any of:

**USB integrity** — enumeration failure, unsupported interface, endpoint error,
malformed report, rollover persisting beyond tolerance, disconnect during the
required stable session, duplicate normalized event, missing normalized event,
stale held-key state, repeat-state inconsistency, queue overflow.

**Editor integrity** — unexpected rejected edit, final text mismatch, cursor
inconsistency, revision inconsistency.

**Transport integrity** — CRC failure, parser overflow, status queue overflow,
unsupported protocol version, sequence reversal, impossible revision, a stale
acknowledgement advancing state, acknowledgement timeout, final hash mismatch.

**Display integrity** — busy timeout, unexpected full-screen flash during a
partial refresh, incomplete erase, severe ghosting, border corruption, pixel
defects, displayed revision exceeding transmitted revision, final catch-up
failure.

**Runtime or electrical** — unhandled exception, device reset, memory allocation
failure, USB disconnect from the host PC, unstable power, wiring fault,
unexpected heating, driver hash mismatch.

On failure: stop both state machines, preserve both `.started` guards, preserve
both serial captures, preserve the USB descriptor evidence, record the exact
key/report/event state, record all revisions, restore the disabled configuration
where safely possible, do not delete guards, do not retry automatically, and
mark FAIL or INCONCLUSIVE.

## Results

**NOT RUN.** No physical live-typing attempt has been made at the implementation
commit. `docs/FRUITJAM_USB_KEYBOARD_SERIAL.jsonl` and
`docs/MAGTAG_USB_KEYBOARD_DISPLAY_SERIAL.jsonl` are placeholders and contain no
run data.

The USB host discovery gate above **was** performed on real hardware and every
descriptor value in it is observed, not inferred. No other physical claim in
this document is evidence of anything yet.

When the run happens, record: repository commit; both CircuitPython versions;
exact wiring; keyboard make/model and receiver type; USB vendor and product ID;
interface descriptors; endpoint details; report format; events generated and
processed; duplicate reports suppressed; repeat events; unsupported usages;
maximum queue depth and overflow count; final document text; viewport frames
sent, rendered, and superseded; acknowledgement counts; CRC failures; sequence
gaps; discarded-prefix bytes; resynchronization count; final transmitted
revision; final displayed revision; final hash; refresh counts; valid timing
observations; disconnects; timeouts; visual observations including lowercase
legibility; photograph filename or an explicit no-photo statement; guard states;
final disabled configurations; and PASS, FAIL, or INCONCLUSIVE.

## PASS criteria

Mark PASS only when every one of the following holds:

- the real keyboard is detected as a usable USB HID keyboard;
- all required keys normalize correctly;
- Shift and Caps Lock work;
- punctuation works;
- press and release handling is correct;
- no duplicate normalized event occurs;
- no keypress is lost during a display refresh;
- no queue overflow occurs;
- multiline editing works through the real keyboard;
- the Fruit Jam remains authoritative and the MagTag remains display-only;
- stale viewports are coalesced;
- skipped revisions are never falsely reported displayed;
- final displayed revision equals final transmitted revision;
- the final hash matches;
- final `DISPLAY_CAUGHT_UP` and `TEST_COMPLETE` are received;
- no CRC failure occurs;
- no timeout occurs;
- no display corruption occurs;
- the operator visually approves the final screen;
- both devices return to the disabled state;
- all four new guards exist;
- every prior guard remains untouched.

## Measurement limitations

Refresh durations are measured by the MagTag between the physical
`begin_refresh` call and the first observation of an idle busy line, polled
cooperatively. They include up to one loop period of quantisation and are not a
substitute for instrumented timing.

Host simulation timings are modelled, not measured, and are never evidence of
physical behaviour. The 60 WPM figures in the limits table come from a paced
simulated keyboard; a real operator's frame and refresh counts will differ with
their typing pattern.

Typing rate is not controlled in this test. It is a human at a keyboard, so
event counts, timings, and frame counts are observations of one session and not
a reproducible measurement.
