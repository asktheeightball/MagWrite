# One-cable bench power

The audit that had to happen before anything was wired, and the arrangement it
allows. Dated 2026-07-30. Sources are Adafruit's own board documentation, cited
inline; nothing here is inferred from a photograph or from how a connector looks.

**Result, first, because it changes the shape of the phase: the direct 5 V
inter-board feed is not supported by either board, in either direction.** The
goal — one USB-C connection at the bench, both boards powered, UART unchanged —
is still reachable, and the arrangement that reaches it is one shared 5 V source
feeding each board through its own USB-C port. That is not a compromise dressed
up as a result; it is the only wiring the two boards' documented power inputs
permit, and it is smaller than the alternative rather than larger.

Nothing in this document introduces a boost converter. The MT3608 belongs to the
battery revision, Priority 6, and stays there.

> **Correction, 2026-07-30, same day.** The audit's finding is unchanged — no 5 V
> header feed, in either direction — but the arrangement it recommended has been
> replaced by a smaller one. The MagTag is powered from a Fruit Jam **USB-A host
> port**, not from a second port on a hub, so the rig is genuinely one cable
> rather than one cable and a hub. Sections 5 to 7 are rewritten for it. That
> port carries no 5 V while the Fruit Jam is in reset, which is why the start
> order in section 7 is gone rather than merely relaxed.

## 1. The connection points, as documented

### Fruit Jam

Source: [Fruit Jam pinout](https://learn.adafruit.com/adafruit-fruit-jam/pinout),
[product page](https://www.adafruit.com/product/6200).

| Node | What it is |
| --- | --- |
| USB-C | power **and** data; the board's power input |
| `OFF`/`ON` slide switch | board power, bottom edge |
| 16-pin socket header | 10 A/D GPIO plus **5V**, **3V**, **GND** pins |
| 5V pin | **output of the 5 V regulator**, ~500 mA peak |
| 3V pin | output of the 3.3 V regulator, 500 mA peak |
| 3-pin JST-PH | VCC (red) / GND (black) / A0 (white); VCC is **5 V by default**, movable to 3.3 V by a back-side jumper |
| USB-A host ports | 5 V switched by `USB_HOST_5V_POWER` (GPIO11), behind a CH334F hub |

The 5V pin is documented as a regulator **output**. It is a place to take current
from, not a place to feed current into.

### MagTag

Source: [MagTag pinouts](https://learn.adafruit.com/adafruit-magtag/pinouts).

| Node | What it is |
| --- | --- |
| USB-C | power and programming; requests 5 V from a USB-C PD source |
| JST 2-PH LiPo connector | 3.7/4.2 V battery, with onboard charging |
| On/off switch | board power |
| STEMMA QT (JST SH 4-pin) | I2C, **3.3 V**, GND |
| 3-pin STEMMA JST ×2, labelled **D10** and **A1** | signal, GND, and a VCC that is **5 V by default** (jumper to 3.3 V); **maximum 200 mA from these connectors**; signal pins carry 1 kΩ series resistors and 3.6 V zeners |

The pinout page states the power inputs exhaustively: *"There are two ways to
power the MagTag board: the USB type C connector or a 3.7/4.2V Lipoly battery."*

**There is no 5 V input pin, pad, or header on the MagTag.** The only 5 V node it
exposes is the VCC on the two 3-pin connectors, and that is documented as an
output rated for 200 mA.

## 2. Which board takes USB-C and which takes 5 V

Neither, because the second half of the question has no answer on this hardware.

- The **MagTag cannot be fed at 5 V.** Its documented inputs are USB-C and a
  3.7–4.2 V LiPo. 5 V into the battery connector is above a single cell's
  maximum and drives the charger's output node; it is not a supply input.
- The **Fruit Jam cannot be fed at 5 V either.** Its 5V pin is a regulator
  output, and back-driving a regulator output is not a supported supply path.

So the direction of the feed was never the question. Both boards have exactly one
documented 5 V input each, and on both boards it is the USB-C connector.

## 3. Back-power, and the cable that already sits between the boards

A wire from the Fruit Jam 5V pin to the MagTag's STEMMA VCC would:

- drive the MagTag's 5 V rail backwards, into its USB-C connector's VBUS pin and
  into its charger input, through a connector Adafruit rates at 200 mA **as an
  output**;
- tie the two boards' 5 V rails into one node, so that plugging a development
  cable into either board's USB-C puts the host's supply in parallel with the
  Fruit Jam's regulator, with no documented OR-ing between them;
- leave the MagTag's own on/off switch and input protection in an undocumented
  position relative to the injected current.

This is not a marginal call, and it is worth naming why the temptation exists:
**both boards' 3-pin JST connectors carry 5 V on the red conductor by default.**
The UART link runs between two of those connectors. A stock, unmodified 3-wire
STEMMA cable between Fruit Jam A0 and MagTag D10 would therefore connect the two
5 V rails on its own, with no intent and no extra part. That is exactly the
failure the standing rule prevents:

> For UART bench testing, leave red/power conductors disconnected and insulated.

That rule now has its reason written next to it, and it does not relax.

## 4. Expected current

Measured where a source measured it, estimated where none did, and labelled
either way. **Nothing in this table was measured on this bench**, and the
`HARDWARE.md` checklist item asking for that measurement stays open.

| Load | At 5 V | Basis |
| --- | --- | --- |
| MagTag, running, WiFi off | ~50 mA active, ~33 mA before NeoPixels | Adafruit's [deep sleep power measurements](https://learn.adafruit.com/deep-sleep-with-circuitpython/power-consumption); measured on the rail, so budget ~60–80 mA at the USB input |
| MagTag, full refresh | short burst above the active figure | not separately published; the panel is a small load beside the SoC |
| Fruit Jam, editor session with microSD | 250–350 mA estimated | not published; RP2350B, CH334F hub, microSD, no HDMI display attached |
| Wired USB keyboard | ≤100 mA typical; the USB spec permits 500 mA | drawn from the Fruit Jam's own host port, not from the shared rail directly |
| USB receiver headroom | 100 mA reserved | a 2.4 GHz radio is not comparable to a wired keyboard, which is precisely the open question |
| **Combined budget** | **typical ~450 mA, worst case ~900 mA** | sum of the above |

Two consequences.

1. A supply rated **5 V at 1 A** covers the typical case with margin; **1.5–2 A**
   covers the worst case and leaves the receiver question room to be re-asked
   without changing the supply again. With the MagTag on a Fruit Jam host port
   the whole of this table draws through one USB-C connector, so 1.5 A is the
   figure to buy rather than the optimistic one.
2. Had the direct feed been available, the Fruit Jam's ~500 mA 5V pin would sit
   *under* the worst-case budget once a keyboard and a receiver are counted, and
   the MagTag's 200 mA connector path would be the tighter limit still. The
   arrangement was not only unsupported; it was also short of headroom.

## 5. The arrangement that is supported

One 5 V source into the Fruit Jam's USB-C, and the MagTag fed from a Fruit Jam
**USB-A host port** with an ordinary USB-A-to-USB-C cable.

```text
        5 V supply (charger, or the PC)
                     |
                     |  one USB-C cable
                     v
                 Fruit Jam
             USB-A         USB-A
               |             |
               |             +---- USB-A to USB-C ----> MagTag
               |
               +---- wired USB keyboard
                     |
                     |  A0 TX ------> D10 RX
                     |  A1 RX <------ A1 TX
                     +----- GND -----+
       (red/power conductor left disconnected and insulated)
```

Why this is supported, and by the same rule that refused the direct feed:

- each board is still powered through its **documented** power input. The Fruit
  Jam takes USB-C. The MagTag takes USB-C. Neither is back-fed;
- the Fruit Jam's USB-A ports are **documented outputs** — 5 V switched by
  `USB_HOST_5V_POWER` behind the CH334F hub — so this is a host port supplying a
  device, which is the one thing USB power is unambiguously for;
- **the MagTag remains a sink**, with exactly one cable into it. There is no
  source-against-source condition anywhere in the rig;
- the UART is untouched — same three conductors, same 115200 baud, same
  insulated red;
- ground was already common through the UART, and stays exactly as common;
- it adds no soldering, no new part on either board, and nothing to undo before
  the battery revision.

Nothing in section 2 is softened by this. The refused arrangement was a wire
from a **5 V header pin** into a node documented as an output; this is a USB
port doing its documented job. The distinction is the whole of it.

### What it costs

**The MagTag's USB-C is now occupied by the Fruit Jam, so the MagTag has no
console and no host-visible `CIRCUITPY` while the rig is wired this way.** That
is a real loss and it is not worked around: to deploy to the MagTag, move its
cable to the PC, copy, and move it back. In normal use there is nothing to
deploy, and the Fruit Jam's console reports the handshake from its own end, so a
MagTag that is not answering is still visible — see section 7.

The MagTag also enumerates on the Fruit Jam's USB host bus as an ordinary
CircuitPython device. It is not selected as the keyboard: the selector matches
the HID boot-keyboard class triple, and CircuitPython's own HID interface is not
a boot interface. It appears in the Fruit Jam's `usb_keyboard_opened` failure
list and is otherwise ignored.

### Requirements

- **Supply:** 5 V, ≥1.5 A. Everything now draws through the Fruit Jam's USB-C:
  the Fruit Jam, its hub, the keyboard, **and** the MagTag. The ≥1 A floor from
  the hub arrangement is no longer enough headroom to be comfortable.
- **Fuse:** none to add inline. The Fruit Jam's USB input protection and the
  CH334F's per-port limiting are the protection.
- **Cables:** short, and known-good for power. A marginal cable shows up here as
  a brownout under a full refresh, not as an obvious failure.

### Two configurations, one cable

| | Upstream | What you get |
| --- | --- | --- |
| **Development** | one USB-C cable from the **PC** to the Fruit Jam | both boards powered, the Fruit Jam's console and `CIRCUITPY`, no MagTag console |
| **Standalone** | one USB-C cable from a **wall charger** to the Fruit Jam | both boards powered, no host, no consoles |

Moving between them is one cable. Nothing on either board changes, and no
configuration file changes.

### The powered-hub variant

The hub arrangement — one source, one upstream cable, a powered hub with
per-port current limiting, one short USB-C cable into each board — remains valid
and remains the way to get **both** consoles at once. It is what to fall back to
if a MagTag console is needed for a session, and what to use if the Fruit Jam's
host port ever proves short of current for the panel. It is two cables at the
boards rather than one, which is the only reason it is no longer the default.

## 6. Both USB cables must not be connected at once

Each board has **one** USB-C port, and in this arrangement each one is already
occupied — the Fruit Jam's by the supply, the MagTag's by the Fruit Jam's host
port. So the rule is easy to keep and easy to state:

> **One USB-C connection per board, always.** Never plug the MagTag into the PC
> while the Fruit Jam is also feeding it, and never connect the two boards' 5 V
> or VBUS rails with a wire — including through the red conductor of a 3-pin JST
> cable.

Moving the MagTag's cable to the PC to deploy is fine, and is the intended way
to do it. Having **both** connected is what is forbidden.

Neither board's power-path design has been shown to make two simultaneous
sources safe. The MagTag documents power-path behaviour only for USB against a
**battery**, not USB against another board's regulator, and the Fruit Jam
documents no power-path behaviour on its 5V pin at all. Absent that proof, two
sources stay forbidden.

## 7. Reset procedure

**There is no start order any more, and there cannot be one.** The Fruit Jam's
USB-A ports carry no 5 V while the Fruit Jam is held in reset, so the MagTag has
no power until the Fruit Jam has one. "Restart the MagTag first" is not a
sequence this wiring can perform, and the software stopped requiring it:

1. connect the one cable. Both boards cold boot together;
2. the Fruit Jam wins that race — it has no e-paper panel to initialise — so its
   first handshake usually goes out before the MagTag is listening. It **waits**,
   re-sending every `DISPLAY_HANDSHAKE_RETRY_SECONDS` and logging
   `live_waiting_for_display` with the document it is holding, until the panel
   answers. A restored document is not touched while it waits;
3. to restart everything, pull the one cable, wait for both boards to go dark,
   and reconnect;
4. to restart only the Fruit Jam, press its reset button. The MagTag loses power
   with it, because its power comes through the Fruit Jam, so this is also a
   simultaneous cold start — which is now the only kind there is.

The old ordering rule and the `duplicate or reversed input sequence` failure it
existed to avoid are described in
[DEVELOPMENT_RUNTIME.md](DEVELOPMENT_RUNTIME.md). Both are retired: the Fruit Jam
keeps its frame numbering monotonic across handshake attempts and re-baselines
the status channel each time, and the MagTag lets a handshake restart the count
as long as it has displayed nothing yet.

## 8. What this does not settle

- **No current was measured.** Every figure in section 4 is documented-elsewhere
  or estimated. A USB power meter on the upstream cable would close the
  `HARDWARE.md` item that has been open since the start, and would also give the
  receiver question a real answer rather than an argument.
- **The receiver question is not answered by this phase.** A shared 5 V supply
  with more headroom than a laptop port makes it *worth re-asking*, but the
  receiver hangs off the Fruit Jam's own host port, behind `USB_HOST_5V_POWER`
  and the CH334F, and that path's limit is unchanged by anything upstream. So
  one-cable power does not by itself explain or fix `36B0:3002`, and no claim is
  made that it will.
- **Battery power is untouched.** Priority 6 still owns the single cell, the
  charger with load sharing, the switch, and the regulated feeds.
