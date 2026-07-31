# MagWrite Hardware

## Prototype hardware

### Adafruit Fruit Jam

Role: authoritative editor, viewport controller, microSD storage, autosave/recovery controller, USB HID host, and MagTag button-event interpreter.

Relevant characteristics:

- RP2350B main processor;
- USB host support;
- microSD storage;
- Wi-Fi through the onboard ESP32-C6 coprocessor;
- exposed GPIO suitable for bidirectional UART to the MagTag.

### Adafruit MagTag

Role: e-paper display terminal and four-button input surface.

Required prototype revision:

- original 2.9-inch panel compatible with UC8151D/IL0373 and GDEW029T5D behavior;
- not assumed compatible with the 2025 SSD1680 MagTag revision.

Relevant characteristics:

- ESP32-S2 with Wi-Fi and no native Bluetooth radio;
- 296×128 e-paper display;
- four front buttons;
- onboard LiPo charging and battery connector;
- internal flash and PSRAM subject to actual firmware availability.

The MagTag does not own document, cursor, wrapping, storage, or workflow state. It renders Fruit Jam-supplied viewports, reports physical display status, and sends normalized button events.

### Wemos LOLIN32 Lite — deferred fallback

The LOLIN32 Lite is not part of the current default prototype.

It may be revisited only if the intended keyboard is Bluetooth-only and cannot use wired USB or a standard USB receiver.

If reintroduced, its role is limited to Bluetooth HID reception and normalized key-event forwarding into the Fruit Jam. It must not own document or display state.

## Intended system architecture

```text
Wired USB keyboard or wireless keyboard with USB receiver
        |
        v
Fruit Jam
- USB HID host
- authoritative editor
- microSD storage and recovery
- viewport generation
- button-event interpretation
        |
        | bidirectional UART
        v
MagTag
- partial-refresh e-paper display
- display acknowledgements
- four-button event capture
```

The internal Fruit Jam ↔ MagTag link is wired for reliability and lower power consumption.

## Fruit Jam to MagTag UART connection

### Verified bench wiring

```text
Fruit Jam board.A0 / UART TX  ---> MagTag board.D10 / UART RX
Fruit Jam board.A1 / UART RX  <--- MagTag board.A1 / UART TX
Fruit Jam GND                 <--> MagTag GND
```

The bidirectional link passed physical testing at 115200 baud.

Connect only TX, RX, and common ground. **Do not connect their 3.3 V, 5 V, BAT, charger, or USB power rails together** with a conductor, in any arrangement, ever. Feeding both boards from one shared upstream supply through their own USB-C ports is a different thing and is supported — see [Bench power](#bench-power-one-cable) below.

### Plug-in cable approach

Prefer pre-crimped plug-in cables rather than soldering directly to either board:

- JST-PH 2 mm 3-pin/STEMMA-style cables for compatible three-pin connectors;
- female-to-female Dupont jumpers for exposed header pins;
- insulated unused power conductors.

Typical three-wire cable colours are:

```text
black = ground
red   = power
white = signal
```

Do not rely on colour alone. Confirm connector position and pinout before powering the boards.

For UART bench testing, leave red/power conductors disconnected and insulated.
This is not a precaution about unknown cables. **Both boards' 3-pin JST
connectors carry 5 V on the red conductor by default**, so a stock 3-wire STEMMA
cable between Fruit Jam `A0` and MagTag `D10` connects the two 5 V rails on its
own, with no intent and no extra part.

## Bench power: one cable

Audited 2026-07-30 against Adafruit's board documentation. The full audit, with
sources, is in [docs/BENCH_POWER.md](docs/BENCH_POWER.md).

**A direct 5 V feed between the boards is not supported, in either direction.**
The MagTag has exactly two documented power inputs — its USB-C connector and a
3.7/4.2 V LiPo on the JST 2-PH connector — and **no 5 V input pin, pad, or header
anywhere on the board**. The only 5 V it exposes is VCC on the two 3-pin STEMMA
connectors, documented as an *output* rated 200 mA. The Fruit Jam's 5V header pin
is likewise a regulator *output*, ~500 mA peak, not a supply input. Driving
either would be undocumented back-powering of a USB VBUS node and a charger
input.

The supported arrangement, and the one in use:

```text
one 5 V source (wall charger, or the PC), ≥1.5 A
        |  one USB-C cable
        v
   Fruit Jam ---- USB-A ----> wired USB keyboard
        |
        +-------- USB-A ---- USB-A-to-USB-C ----> MagTag
        |
        \___ A0/A1 UART + common GND ___/
             (red conductor insulated)
```

- each board is still powered through its own **USB-C** input, with its own
  switch, protection, and regulator. The MagTag's supply is a Fruit Jam USB-A
  **host port**, a documented 5 V output, so this is a host powering a device
  rather than a header pin being back-fed;
- both boards are **sinks**; nothing sources current into the shared node;
- supply 5 V at **≥1.5 A** — everything now draws through one USB-C connector,
  and the estimated combined budget is ~450 mA typical and ~900 mA worst case,
  with **no figure yet measured on this bench**;
- swapping the one cable between the PC and a charger is the whole difference
  between the development and standalone configurations. From V1.6 it is the
  *only* difference: the shipped configuration on both boards is the writing
  appliance, so a wall charger and nothing else is a working device. See
  [docs/STANDALONE.md](docs/STANDALONE.md).

**The MagTag has no console and no host-visible `CIRCUITPY` while wired this
way** — its USB-C goes to the Fruit Jam. Move that cable to the PC to deploy to
it, and move it back. **Deploy to the MagTag first**, for that reason. The Fruit Jam's console reports the handshake from its own
end, so a MagTag that is not answering is still diagnosable.

**There is no start order, and there cannot be one.** The Fruit Jam's USB-A ports
carry no 5 V while the Fruit Jam is in reset, so the MagTag cannot be booted
first. Both boards cold boot together and the Fruit Jam retries the display
handshake until the panel answers — see
[docs/DEVELOPMENT_RUNTIME.md](docs/DEVELOPMENT_RUNTIME.md). From V1.6 the MagTag
draws `MAGWRITE / STARTING` of its own accord while that happens, so a panel with
nothing on it during the boot window is now a fault rather than the norm.

**One USB-C connection per board, always.** Never plug the MagTag into the PC
while the Fruit Jam is also feeding it. Neither board's power-path design has
been shown to make two simultaneous sources safe: the MagTag documents
power-path behaviour for USB against a *battery* only, and the Fruit Jam
documents none at all on its 5V pin.

The powered-hub variant — one source, one upstream cable, a hub with per-port
current limiting, one USB-C cable into each board — remains valid and is the way
to get **both** consoles at once.

## UART protocol direction

The Fruit Jam sends complete semantic viewport snapshots rather than one display command per typed character.

The MagTag returns bounded status and input messages, including:

- frame accepted;
- refresh started;
- refresh completed;
- display caught up;
- display error;
- test complete;
- normalized button events, from V1.5.

The protocol uses versioning, sequence numbers, length framing, CRC32, bounded parsing, resynchronization, duplicate/stale handling, and display backpressure. While the MagTag is refreshing, the Fruit Jam retains only the newest required viewport rather than queueing every intermediate editor state.

## MagTag buttons

Implemented in V1.5. The four front buttons control Fruit Jam-owned application
behaviour through the existing return UART path, and are the **primary** shell
control surface; the keyboard's shell keys remain as a fallback.

```text
MagTag button (active low, internal pull-up)
        |
        v
stability debounce, per-action minimum interval, monotonic press ordinal
        |
        v
sequenced BUTTON_EVENT on the acknowledgement channel
        |
        v
Fruit Jam action mapping
```

| Button | Pin alias | Action sent |
| --- | --- | --- |
| A | `BUTTON_A` | `MENU` |
| B | `BUTTON_B` | `UP` |
| C | `BUTTON_C` | `DOWN` |
| D | `BUTTON_D` | `SELECT` |

Back-to-menu and select are the outer two so a thumb cannot confuse either with
the movement pair between them.

From V1.7 the panel says so. A persistent footer sits directly above the bezel on
every screen — editor, menus, drafts, startup, waiting, status, and error — with
`MENU`, an up arrow, a down arrow, and `SELECT` centred on the four
quarter-centres of the panel's long axis, left to right in the pin order above.
It changes no button behaviour and carries no state; it is drawn locally by the
MagTag and costs no protocol. See `ARCHITECTURE.md`, "The button footer".

Left-to-right on the panel must be left-to-right on the bezel, and that was a
claim only the physical device could settle. **Settled 2026-07-31: it is, with A
on the left.** `button_footer.FOOTER_ACTIONS` is the panel's order and needed no
change; it stays the single line to reverse if that ever stops being true.

The MagTag reports only:

- a **normalized action** — `MENU`, `UP`, `DOWN`, `SELECT` — never which physical
  switch closed and never what the action should do;
- the press edge. A held button does not repeat, and long press is not modelled;
- a monotonic press ordinal, a timestamp, and bounded diagnostics.

The Fruit Jam decides whether an event means:

- menu or document action;
- move the selection up or down;
- open, confirm, or dismiss;
- leave the editor, which checkpoints the document first.

The MagTag must not independently edit, move the authoritative cursor, save, open a document, or change application workflow.

A button pin the board does not expose is a **reported degraded mode**: the panel
runs and the keyboard still drives the shell. It is never a refusal to start.

## Keyboard

### Preferred path: direct USB HID

Use one known keyboard directly through the Fruit Jam USB host port.

Preferred order:

1. wired USB keyboard;
2. wireless keyboard with a standard USB receiver.

The USB HID adapter must support the required editing keys, modifiers, key release, hold, and deliberate repeat while preserving bounded normalized event processing.

### Deferred path: Bluetooth bridge

Use the LOLIN32 Lite only if a required keyboard is Bluetooth-only and direct USB HID is not viable.

Do not assume a generic USB Bluetooth adapter will work without a proven USB-host driver path.

## Unified power target

For bench development, separate USB power remains acceptable where needed for
serial diagnostics and safe hardware isolation. One shared upstream supply
through a hub is the ordinary configuration — see [Bench power: one
cable](#bench-power-one-cable) — and neither arrangement is the finished
device's.

The finished device must use one unified rechargeable power system:

- one protected single-cell battery;
- one charger with power-path/load-sharing support;
- one external charging port;
- one system power switch;
- regulated feeds appropriate to Fruit Jam and MagTag;
- measured peak current and brownout margin;
- measured active, refresh, idle, and sleep consumption;
- battery-level and low-battery behavior.

Do not connect one battery simultaneously to the independent charger circuits on both development boards.

## Hardware validation checklist

- [x] Photograph MagTag and record display-flex markings.
- [x] Confirm MagTag display controller/revision as original UC8151D/T5 family.
- [x] Measure controlled 20-, 50-, and 100-update partial refresh behavior.
- [x] Verify one-way Fruit Jam-to-MagTag UART using signal and common ground.
- [x] Verify bidirectional UART acknowledgements using A0→D10 and A1→A1.
- [x] Confirm no inter-board power conductor during verified UART bench tests.
- [x] Physically verify the integrated multiline editor and five-line layout.
- [x] Implement MagTag button events over return UART. Physically verified
      2026-07-30 — all four buttons claimed, 9 presses delivered and applied
      exactly once each, none reaching the document. Recorded in `ROADMAP.md`.
- [x] Draw the panel in `terminalio.FONT` and label the bezel. Physically
      verified 2026-07-31 — 1× scale, 6×12 cell, 48 columns by 6 content rows,
      the four footer labels confirmed over A/B/C/D, and 898 ms mean partial
      refresh on roughly double the text. See `docs/PANEL_UI_CHECK.md`.
- [x] Verify one known USB HID keyboard on the Fruit Jam. Done with the **wired**
      EPOMAKER TH40, across V1.2 through V1.5 and re-confirmed as a control on
      2026-07-30: enumeration, interface selection, boot-report reading, and live
      typing into the document. The two early failures were the **wireless
      receiver**, not the keyboard. See `docs/FRUITJAM_USB_KEYBOARD_TEST.md`.
- [ ] **The TH40's own 2.4 GHz receiver (`36B0:3002`) is incompatible** with the
      Fruit Jam host port. Three further boots on 2026-07-30 reproduced the
      original failure exactly: enumerates on the first attempt, holds the
      connection, sends zero HID reports, with the wired cable working in the
      same port and session as a control. Not to be pursued further. Evidence
      `docs/FRUITJAM_DONGLE_PROBE_SERIAL.jsonl`; the account is in `ROADMAP.md`.
- [ ] Determine whether the Fruit Jam host port supplies enough current for a
      2.4 GHz receiver's radio. **Still open**, and note that one-cable power did
      *not* answer it even though the host port now also carries a MagTag: the
      bench check ran with no meter, so "no brownout" is an observation about a
      panel and a keyboard, not a figure about a radio. The powered-hub test that would
      settle it was declined on 2026-07-30; the wired control does not answer it,
      because a wired keyboard and a radio are not comparable loads. Worth
      re-asking after one-cable bench power — but note that the receiver hangs
      off the Fruit Jam's own host port, behind `USB_HOST_5V_POWER` and the
      CH334F hub, and **that path's limit is unchanged by anything upstream**.
      More headroom at the supply makes the question worth re-asking; it does not
      answer it.
- [ ] Obtain **one ordinary wireless keyboard with a USB receiver** — any vendor,
      not the TH40's own dongle. This is the only thing that can say whether the
      wireless path works at all or fails only with this receiver, and the dongle
      phase is blocked on it.
- [ ] Verify keyboard reconnect, modifiers, hold, and repeat.
- [x] Read the microSD pin aliases off the board and set them in
      `fruitjam/config.py`. Done 2026-07-30 with `tools/fruitjam_sd_probe.py`;
      evidence `docs/FRUITJAM_SD_PROBE.jsonl`. The board exposes `SD_CS`,
      `SD_SCK`, `SD_MOSI`, `SD_MISO`, `SD_CARD_DETECT`, and a separate `SDIO_*`
      interface. The card is on the **dedicated** SPI bus, so those four aliases
      are now named explicitly rather than using the shared `board.SPI()`.
      `SD_CARD_DETECT` is claimed by the firmware before user code runs, so the
      optional card-detect path stays disabled.
- [x] **Provide a microSD card with a FAT filesystem.** Done 2026-07-30. The
      card found in the slot had a valid MBR whose one partition entry claimed
      more sectors than the card physically had, with no FAT volume boot record
      at that offset or twelve others; the runtime correctly reported
      `UNMOUNTABLE`. It was reformatted with explicit authorisation. FatFs sizes
      the FAT width from the volume, so the 946 MB card came out **FAT16, not
      FAT32**; nothing in V1.2 depends on the width. The format was proved by
      write, sync, unmount, remount, read back.
- [x] Verify microSD autosave and forced-power-loss recovery. **PASSED
      2026-07-30**; evidence `docs/FRUITJAM_V12_PERSISTENCE_SERIAL.jsonl`. A
      writing session produced 12 autosaves and 3 checkpoints, Ctrl-S manual save
      worked and inserted no character, and after the USB cable was pulled
      mid-session the restart recovered revision 73, 71 characters, cursor
      (2, 8) — exactly the last acknowledged edit.
- [x] Audit one-cable bench power. Done 2026-07-30; the audit is
      `docs/BENCH_POWER.md`. **The direct 5 V inter-board feed is not supported
      by either board**: the MagTag has no 5 V input at all, and the Fruit Jam's
      5V pin is a regulator output. One shared 5 V source feeding each board
      through its own USB-C port is what the documentation permits, and it is
      also the smaller change. **Superseded the same day by a smaller
      arrangement still:** one supply into the Fruit Jam's USB-C, and the MagTag
      fed from a Fruit Jam **USB-A host port** — a documented output into a
      documented input, and genuinely one cable rather than one cable and a hub.
- [x] Remove the board start order. Required by the arrangement above rather than
      chosen: **the Fruit Jam's USB-A ports carry no 5 V while it is held in
      reset**, so the MagTag cannot be started first and both boards necessarily
      cold boot together. The Fruit Jam now retries the display handshake until
      the panel answers instead of failing after one attempt, and the MagTag lets
      a handshake re-baseline its input numbering as long as it has displayed
      nothing yet. Host-verified; see `host-tests/test_display_wait.py`.
- [x] Run the physical one-cable bench check. **PASSED 2026-07-30**; evidence
      `docs/BENCH_ONECABLE_FRUITJAM_SERIAL.jsonl`, procedure and result in
      `docs/BENCH_POWER_CHECK.md`. One USB-C cable was connected and the complete
      device started by itself, twice, with no reset and no start order: four
      handshake attempts and a 9.05 s wait on both boots, the document recovered
      both times — the second recovering exactly what a MagTag button had
      checkpointed before power was pulled — 26 viewports all displayed, two full
      refreshes at 3586 ms and 3525 ms with no brownout, 24 partial refreshes
      averaging 924 ms, 23 button presses all applied, and zero faults of any
      kind. Nothing warm to the touch; panel clean.
- [x] Run the physical standalone check, `docs/STANDALONE_CHECK.md`. **PASSED
      2026-07-30**, every step, with no faults observed; result in
      `docs/STANDALONE_CHECK.md`. V1.6 makes the shipped configuration on both
      boards the writing appliance — no flag, no console, no host-mounted volume,
      no start order — and it now behaves that way on the bench with neither board
      connected to the PC. The two steps that mattered both passed: a keyboard
      connected *after* startup became usable with no reboot, and the device left
      idle past the removed 1800 s bound did not shut itself down.
      **No evidence file, and by design** — the check removes both consoles, so
      the panel is the only instrument and the operator's observation is the only
      record. No current, timing, or refresh figure was measured or is claimed.
- [ ] Measure active and idle current for each board and USB receiver. **Still
      open, and now the one thing bench power leaves unmeasured.** A USB power
      meter on the upstream cable closes it, and would also give the receiver
      current question a measurement instead of an argument.
- [ ] Determine and verify safe single-battery capacity, charging, and distribution topology.
- [ ] Complete enclosure and field-use testing.

## Display-driver dependency

The no-flash refresh implementation derives from `bciuca/magtag-partial-refresh-driver`, which is GPL-3.0-or-later. Preserve all applicable licence notices, modification records, GPL text, and corresponding-source obligations.