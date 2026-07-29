# Fruit Jam Live USB HID Keyboard Test

**Status: FAIL after two guarded attempts on 2026-07-29. Neither attempt was
blocked by a software defect. The run is blocked on a hardware finding: the
wireless keyboard stopped delivering any HID data to its receiver while that
receiver was in the Fruit Jam host port, even though the same keyboard and
receiver had delivered real usages to that same port earlier the same day and
typed correctly on a PC afterwards.**

Zero keystrokes were captured, so **no PASS criterion below has been tested**.
Everything in the "USB host discovery gate" section *was* observed on real
hardware and remains valid evidence.

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

`Escape` (`0x29`) is the deliberate **finish key**: it ends the live run and
produces no editor event.

**Application/Menu (`0x65`) is a second, equally deliberate finish key.** The
keyboard used for the physical phase is a 40% board that cannot deliver `0x29`
from a standalone key: its Escape lives on an Fn layer, and on that board the
Fn combination *also switches the keyboard out of USB mode*, so pressing
"Escape" silences the device instead of ending the run. This was established by
the unguarded probe before any guarded attempt, and is recorded under Results.
`0x65` has no glyph and no editor action, so accepting it costs nothing: it
previously counted only as an unsupported key. Both usages are exercised by
host tests that prove one action per press, no duplicate finish from a held or
repeated report, and correct release behaviour.

Every character the keymap can emit is present in the proven 3x5 glyph table; a
host test asserts that directly. Deliberately unsupported, ignored with a
bounded `usb_keyboard_unsupported_usage` diagnostic and never crashing:
function keys, Tab, Insert, Page Up/Down, keypad digits, and the shifted forms
with no glyph (`@ # $ % ^ & * _ + = [ ] { } \ | ~` and backtick).

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

### Unguarded wired-keyboard probe — 2026-07-29, commit `4e431a3` — **PASS**

This phase is a read-only probe, not a physical attempt. It created no guard,
wrote nothing to either board's filesystem beyond a temporary probe module,
never activated the display, and never entered the editor integration state
machine. It was run with both `config.py` files still `DISABLED`, so no
one-shot harness was ever armed and no guarded attempt was consumed.

Its purpose was the question attempts 1 and 2 could not answer: does a real
keyboard deliver non-zero HID reports into the already-implemented adapter?

Probe source: `tools/fruitjam_usb_keyboard_probe.py`, deployed to the Fruit Jam
as `/usb_probe.py` and run from the serial REPL. Descriptor reading, interface
selection, endpoint claiming, and report reading are performed by the shipped
`usb_host_backend` and `usb_hid_descriptors` modules rather than by a parallel
implementation, so these results are evidence about the real code path.

Capture: `FRUITJAM_USB_KEYBOARD_PROBE.jsonl` (211 records, five runs).

#### The wireless receiver was re-tested and failed again

Before the wired keyboard was fitted, the operator found that the inter-board
`GND` wire had been disconnected and reseated it, on the theory that this had
caused attempt 2. It had not, and the probe demonstrated so at no cost:

| Run | Device | Duration | Endpoint polls | Non-zero reports |
| --- | --- | --- | --- | --- |
| Smoke | `36B0:3002` Wireless 2.4G Dongle | 8 s | 3,950 | 0 |
| After GND reseat | `36B0:3002` Wireless 2.4G Dongle | 90 s | 44,456 | 0 |

A missing inter-board ground cannot explain absent USB reports in any case: HID
reports arrive over the Fruit Jam's USB host port and never cross the UART
link. Attempt 2's own record is consistent with this, showing `bytes_received:
43` and a completed HELLO handshake — the UART was working. Both boards are
powered from the same host PC, so their grounds were already bonded through the
USB ground and the dedicated wire was not isolating anything.

**Attempt 2 therefore stands as `FAIL` exactly as recorded.** Its evidence is
unmodified. The receiver enumerates, parses, selects, and claims correctly, and
delivers no key data on its boot-keyboard interface. Whether a paired wireless
keyboard was powered and paired at the time was never established, and the
receiver is out of scope for this phase.

#### CircuitPython's built-in driver owns the keyboard until it is detached

When the wired keyboard was first fitted, the operator's keystrokes appeared in
the CircuitPython serial REPL and interleaved with the probe command, which
died with `SyntaxError`. This is the condition `usb_host_backend.py` documents:
CircuitPython's own USB host keyboard driver routes an attached keyboard to the
serial console, and `_claim()` must detach it before the interrupt endpoint can
be read.

The detach is confirmed empirically. Before the probe claims the interface,
keystrokes echo into the console; while it holds the interface, the serial
output is pure JSON with no stray characters and 735 reports arrive at the
endpoint. `is_kernel_driver_active(0)` reports `false` both before and after
the claim, so that call is not by itself a reliable indicator of console
ownership on this build — the observed console behaviour is.

The receiver never exercised this path, because it had no key data to route.

#### Wired keyboard identity and descriptors

| Field | Observed |
| --- | --- |
| Product | EPOMAKER TH40 |
| Manufacturer | RDMCTMZT |
| Vendor ID | `36B0` |
| Product ID | `304E` |
| Serial number | none reported |
| Speed | 2 |
| Configuration descriptor | 91 bytes |
| HID interfaces | 3 |
| Selected interface | 0 |
| Interface class/subclass/protocol | `03` / `01` / `01` |
| Endpoint | `0x81` |
| Maximum packet size | 8 |
| Polling interval | 1 |
| Report length | 8 |

Raw configuration descriptor:

```
09025B00030100A0FA0904000001030101000921110100012244000705810308
00010904010002030000000921110100012222000705820320000107050303200001
09040200010300000009211101000122B60007058403200001
```

#### Observed reports

90 s run, operator typing continuously:

| Field | Observed |
| --- | --- |
| Reports received | 850 |
| Non-zero reports | 735 |
| Release reports | 77 |
| Duplicate reports | 38 |
| Error/rollover reports | 0 |
| Unsupported usages | 4 |
| Idle polls | 43,352 |
| Disconnects | 0 |

Sample reports, decoded through the shipped `hid_keymap`:

```
0000040F00000000  ->  a, l
0000040F0E000000  ->  a, l, k
0000361011061B00  ->  , m n c x
2000370000000000  ->  '>'  (right Shift, usage 0x37)
0000370000000000  ->  '.'
0000000000000000  ->  release
```

Press and release cascades are clean, six-key rollover is handled, and no stale
held-key state was observed.

#### Key coverage established before arming

| Key | Usage | Observed | Notes |
| --- | --- | --- | --- |
| Letters | `0x04`–`0x1D` | yes | lowercase and uppercase |
| Shift | modifier `0x02` / `0x20` | yes | both left and right seen |
| Punctuation | `0x36`, `0x37` | yes | `,` `.` `>` |
| Enter | `0x28` | yes | |
| Backspace | `0x2A` | yes | |
| Left | `0x50` | yes | |
| Right | `0x4F` | yes | |
| Up | `0x52` | yes | |
| Down | `0x51` | yes | |
| Home | `0x4A` | **no** | see limitation below |
| End | `0x4D` | **no** | see limitation below |
| Delete | `0x4C` | **no** | see limitation below |
| Caps Lock | `0x39` | not exercised | |
| Key repeat | — | not exercised | |
| Application/Menu | `0x65` | yes | correctly reported `UNSUPPORTED` |

**Documented keyboard limitation.** The EPOMAKER TH40 is a 40% board with no
dedicated navigation cluster. A 45 s probe restricted to Home, End and Delete
produced zero reports of any kind across 22,228 endpoint polls. The operator
does not know the TH40's layer mapping for these keys, so it is not established
whether they are unmapped or simply were not pressed. They are recorded as
**not exercised**, and Scenario 4 is run with the four arrow keys and Backspace,
all of which are confirmed. This is a property of the keyboard, not of the
adapter, and no software conclusion is drawn from it.

#### The keyboard silently leaves USB mode on some Fn combinations

Three probe runs returned **zero reports of any kind** — no key usages and no
modifier bytes — across 22,228, 29,632, and 29,632 endpoint polls, while the
keyboard continued to enumerate normally as `36B0:304E` and the interface was
claimed successfully every time. Every one of those runs was one in which the
operator pressed unfamiliar Fn combinations while hunting for Home, End, Delete
or Escape. Every run restricted to ordinary keys produced hundreds of reports.

The TH40 is a multi-mode keyboard (USB, 2.4 GHz, Bluetooth) whose mode is
changed by an Fn combination. The observed behaviour is the keyboard leaving
USB mode and transmitting on its radio instead: still powered, still enumerated,
still claimable, and completely mute on the wire. Restoring USB mode restored
reports immediately (294 non-zero reports in the next run).

This also retrospectively explains attempts 1 and 2. The receiver used there is
`36B0:3002`, the same vendor ID and the same `RDMCTMZT` manufacturer string as
this keyboard: **it is this keyboard's own 2.4 GHz receiver.** Those attempts
had the receiver attached while the keyboard was not paired to it or not in
2.4 GHz mode, so the receiver enumerated correctly and forwarded nothing. No
software defect was ever involved in either attempt.

**Operational consequence for the guarded run: press no unfamiliar Fn
combinations.** A mode switch mid-attempt would mute the keyboard and cost the
attempt.

#### Escape cannot be produced, so a second finish control was added

Escape (`0x29`) was never observed. Pressing the operator's Escape binding
consistently coincided with the keyboard falling silent, consistent with that
binding being an Fn combination that also switches mode. A standalone key
remapped by the operator produced `0x65` (Keyboard Application) reliably: 21
presses, 21 clean release pairs, no mode switch, no instability.

Escape is the only route to `finish_requested`, and therefore the only route to
`DISPLAY_CAUGHT_UP` and `TEST_COMPLETE`. Without a usable finish key a guarded
attempt can only end by idle timeout, the 500-event ceiling, or the session
timeout, all of which are `FAIL`. A PASS would have been unreachable.

`0x65` was therefore adopted as an additional `FINISH` control, by operator
decision, as a deliberate hardware-compatibility change rather than a probe
workaround. The physical key mapping was left exactly as the operator set it.
Escape remains a finish key and no other usage changed behaviour.

#### What the probe establishes

Verified on real hardware, with a real wired keyboard:

- enumeration, descriptor read, and descriptor parse;
- interface selection by the HID class triple;
- endpoint claim, `SET_PROTOCOL` boot, and `SET_IDLE`;
- detach of CircuitPython's own console keyboard driver;
- real non-zero boot reports at the interrupt endpoint;
- correct translation of letters, Shift, punctuation, Enter, Backspace, and all
  four arrow keys through the shipped keymap;
- correct press/release handling and six-key rollover;
- duplicate suppression against real reports;
- 43,352 bounded polls with zero errors and zero disconnects.

Not established by the probe, and left to the guarded run: normalized event
generation, the editor, the viewport builder, the UART transport, the display,
Caps Lock, and key repeat.

### Attempt 2 — 2026-07-29, run commit `ab52961` — **FAIL**

Authorised by the operator, who explicitly named
`/magwrite_usb_keyboard_display.started` for deletion after attempt 1. No other
guard, evidence file, capture, configuration, or backup was touched.

Captures: `FRUITJAM_USB_KEYBOARD_SERIAL.jsonl` (8 records) and
`MAGTAG_USB_KEYBOARD_DISPLAY_SERIAL.jsonl` (3 records). Both are the verbatim
JSON records from this attempt.

**Stop condition: `live session idle timeout`**, raised by the Fruit Jam after
the configured 600 s of no keyboard activity.

| Field | Observed |
| --- | --- |
| Repository commit | `ab52961` |
| Fruit Jam CircuitPython | 10.2.1 (`adafruit_fruit_jam`, UID `FFDBA7B15146C218`) |
| MagTag CircuitPython | 9.1.1 (`adafruit_magtag_2.9_grayscale`, UID `C7FD1A005DEA`) |
| Wiring | A0→D10, A1→A1, common ground; no inter-board power conductor; both separately USB-powered |
| Baud / protocol version | 115200 8N1 / version 1 |
| Keyboard | wireless keyboard with 2.4 GHz USB receiver; no operator-supplied make/model recorded |
| USB vendor / product ID | `0x36B0` / `0x3002` |
| USB strings | `RDMCTMZT`, `Wireless 2.4G Dongle`, serial `19971217` |
| Interface / endpoint selected | interface 0 (class 3, subclass 1, protocol 1), endpoint `0x81`, 8-byte packets, 1 ms interval |
| HID interfaces present | 3 |
| USB device state | reached `READY`; 1 open attempt, 1 connect, 0 disconnects, 0 errors, 2 transitions |
| MagTag arming wait | 79.664 s, correctly excluded from the run budget |
| HID reports received | **2**, both all-zero release reports (`keys:[0,0,0,0,0,0]`); the second correctly suppressed as a duplicate |
| Normalized events | **0** |
| Events processed / rejected | 0 / 0 |
| Duplicate reports suppressed | 1 |
| Repeat events | 0 |
| Unsupported usages | 0 |
| Rollover reports | 0 |
| Maximum queue depth / overflows | 0 of 64 / 0 |
| Held-key resets | 1 (the correct reset on connect) |
| Final document text | empty |
| Viewport frames sent / accepted / rendered / superseded | 0 / 0 / 0 / 0 |
| Viewports built / coalesced locally | 0 / 0 |
| FRAME_ACCEPTED / REFRESH_STARTED / REFRESH_COMPLETED / DISPLAY_CAUGHT_UP | 0 / 0 / 0 / 0 |
| STATUS_HELLO | received; `receiver_ready` and `display_ready` both true |
| TEST_COMPLETE | not received |
| Final transmitted / displayed revision | 0 / 0 |
| Final hash | `00000000` |
| Refreshes | 0 full, 0 partial — the panel was never sent a viewport |
| CRC failures / parser rejections | 0 / 0 |
| Sequence gaps / duplicates / stale | 0 / 0 / 0 |
| Discarded prefix bytes / resynchronizations | 0 / 0 |
| Bytes sent / received (Fruit Jam) | 35 / 43 |
| Timeouts | 1 |
| Visual observations | The panel never displayed a MagWrite viewport. It retained the CircuitPython traceback drawn during an earlier autoreload boot, which is expected: the MagTag only refreshes on receiving a VIEWPORT frame and none was ever sent. No ghosting, corruption, or defect assessment is possible from this attempt. |
| Lowercase glyph legibility | **untested** — nothing was ever rendered |
| Photograph | **No photograph was taken.** |
| Fruit Jam guard states | `/magwrite_usb_keyboard.started` present, holding the FAIL summary; `.complete` absent |
| MagTag guard states | `/magwrite_usb_keyboard_display.started` present; `.complete` absent |
| Prior guards verified untouched | yes — all 20 SHA-256 inventoried before the run and re-verified byte-identical after |
| Final activation states | both restored to disabled and verified on-device |
| Result | **FAIL** |

#### What the attempt did prove

Everything up to the keyboard itself worked on real hardware, first time:

- the Fruit Jam enumerated the receiver and selected the correct interface out of
  three by the HID class triple;
- `detach_kernel_driver`, `set_configuration`, `SET_PROTOCOL(boot)` and
  `SET_IDLE` all succeeded against the real device;
- the connection state machine ran `NO_DEVICE → ENUMERATING → READY` and logged
  the observed descriptor;
- the two all-zero reports were parsed correctly and produced **zero** editor
  events, and the second was correctly suppressed as a duplicate — the
  duplicate-suppression rule working on real data;
- the HELLO/STATUS_HELLO handshake completed over the real UART;
- the MagTag reached `usb_keyboard_display_ready` and started its run clock only
  on the first received frame, excluding a 79.7 s operator arming wait — the
  `RunClock` fix from the editor phase working as intended;
- the idle timeout fired, wrote a complete FAIL summary, preserved the
  `.started` guard, wrote no `.complete`, and did not retry.

#### Root cause

The keyboard was not transmitting to its receiver. Three independent checks:

1. Polling endpoint `0x81` alone for 18 s while the operator typed: **0 reports**.
2. Polling all three interrupt IN endpoints for 18 s while typing: 4 reports,
   all on `0x84`, all zero-payload, **none on the keyboard endpoint**.
3. Re-attaching CircuitPython's own host keyboard driver and typing for 15 s:
   `supervisor.runtime.serial_bytes_available` stayed at **0**, so CircuitPython
   received nothing either.

All three runs showed roughly 8,900 clean `USBTimeoutError` reads per 18 s, so
the read path was healthy throughout — there was simply no data.

Two hypotheses were tested and **disproved**:

- *`SET_PROTOCOL(boot)` silences this receiver.* Polling with and without it in
  the same session gave 1 all-zero report and 0 reports respectively. Not the
  cause.
- *CircuitPython's host driver wins a race for the interrupt endpoint.* With the
  driver deliberately re-attached and owning the interface, its own console
  received nothing. Not the cause.

The receiver enumerated correctly and its consumer-control interface kept
emitting idle reports throughout, so the receiver was powered and responsive.
The keyboard typed correctly on a PC immediately afterwards. Earlier the same
day, before any harness existed, the same keyboard and receiver in the same
Fruit Jam port delivered real usages (`0x04` a, `0x07` d, `0x0B` h, `0x13` p,
`0x16` s) including a three-key rollover.

The remaining candidates are physical and were not resolved: marginal 5 V supply
to the receiver's radio from the Fruit Jam host port, or the keyboard losing its
pairing session. This is recorded as an open hardware question, not a diagnosis.

### Attempt 1 — 2026-07-29, run commit `ab52961` — **FAIL**

**Stop condition: `KeyboardInterrupt` inside `magwrite/sha256.py` line 72,
`_compress`.** The armed MagTag harness was aborted partway through the
pre-existing `sha256_file("/uc8151.py")` driver-hash gate.

Root cause: **operator-procedure defect, introduced by the harness driver, not
by the repository.** The MagTag was reset by issuing `microcontroller.reset()`
over its serial REPL. That is unsafe for a one-shot armed harness, because the
same CDC channel used to trigger the reset can also deliver a Ctrl-C into the
harness it just started. The pure-Python SHA-256 over a 10 KB file takes many
seconds on the ESP32-S2, which is a wide window for a stray interrupt to land.

Because the hash check runs at line 67 and the guard is claimed at line 73, this
particular boot wrote no guard. A subsequent boot claimed
`/magwrite_usb_keyboard_display.started`; a later boot then correctly refused at
line 69 with `RuntimeError: MagTag USB keyboard display guard exists`, which is
the fail-closed behaviour working, not a defect.

The MagTag also dropped off USB entirely during this attempt and required a
physical power-cycle to re-enumerate.

No keystrokes were typed, no viewport was sent, and the Fruit Jam was never
armed during attempt 1.

**Corrected procedure, used for attempt 2 and required for any future attempt:
never write to either serial port while a harness is armed. Start the read-only
captures first, then have the operator press the physical reset button.**

#### A second, harmless failure mode found during attempt 2 arming

Writing an armed `config.py` from the host triggers CircuitPython autoreload,
which re-runs `code.py` but **not** `boot.py`. Without `boot.py` the filesystem
is never remounted writable for the device, so the harness reaches its guard
write and dies with `OSError: [Errno 30] Read-only filesystem` at line 73. The
operator's subsequent physical reset then boots cleanly and the run proceeds
normally. This is visible in the MagTag capture and is benign — it writes no
guard and corrupts nothing — but it means the panel can be left showing a
traceback from that aborted boot until the first real viewport arrives.

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
