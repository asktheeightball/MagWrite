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
   without changing the supply again.
2. Had the direct feed been available, the Fruit Jam's ~500 mA 5V pin would sit
   *under* the worst-case budget once a keyboard and a receiver are counted, and
   the MagTag's 200 mA connector path would be the tighter limit still. The
   arrangement was not only unsupported; it was also short of headroom.

## 5. The arrangement that is supported

One 5 V source, one upstream cable, two short USB-C cables — one into each
board's own USB-C port.

```text
                 5 V source
            (charger, or the PC)
                     |
                     |  one USB-C cable
                     v
        powered hub / 2-port supply
             |              |
    USB-C    |              |    USB-C
             v              v
        Fruit Jam       MagTag
             |              ^
             |  A0 TX ------+ D10 RX
             |  A1 RX <-----+ A1 TX
             +---- GND -----+
       (red/power conductor left disconnected and insulated)
```

Why this is the smallest safe thing rather than a retreat:

- each board keeps its **documented** power input, its own switch, its own input
  protection, and its own regulator;
- **both boards are sinks.** Nothing sources current into the shared node, so
  there is no source-against-source condition anywhere in the rig;
- the UART is untouched — same three conductors, same 115200 baud, same
  insulated red;
- ground was already common through the UART, and stays exactly as common;
- it adds no soldering, no new part on either board, and nothing to undo before
  the battery revision.

### Requirements

- **Supply:** 5 V, ≥1 A, ≥1.5 A preferred.
- **Distribution:** a **powered hub with per-port current limiting** is preferred
  over a passive splitter. With per-port limiting, a fault on one board does not
  drag the other's rail down; with a passive splitter, it does.
- **Fuse:** none to add inline. Each board's USB input protection plus the hub's
  per-port limit is the protection, and inserting a fuse in a USB-C cable is not
  a modification worth making to a rig with no unfused node.
- **Cables:** short, and known-good for power. A marginal cable shows up here as
  a brownout under refresh, not as an obvious failure.

### Two configurations, same wiring

| | Upstream | What you get |
| --- | --- | --- |
| **Development** | one USB-C cable from the **PC** to a powered data hub | both boards powered, both serial consoles, both CIRCUITPY volumes host-writable |
| **Standalone bench** | one USB-C cable from a **wall charger** to the hub | both boards powered, no host, no consoles |

Moving between them is one cable at the upstream end. Nothing on either board
changes, and no configuration file changes.

## 6. Both USB cables must not be connected at once

Each board has **one** USB-C port, and in this arrangement that port is already
occupied by the hub. So the rule is easy to keep and easy to state:

> **One USB-C connection per board, always.** Never plug a board into the PC
> while the hub is also feeding it, and never connect the two boards' 5 V or
> VBUS rails with a wire — including through the red conductor of a 3-pin JST
> cable.

Neither board's power-path design has been shown to make two simultaneous
sources safe. The MagTag documents power-path behaviour only for USB against a
**battery**, not USB against another board's regulator, and the Fruit Jam
documents no power-path behaviour on its 5V pin at all. Absent that proof, two
sources stay forbidden.

## 7. Reset procedure

Unchanged, and the existing ordering rule still governs:

1. power the rig up from the single upstream cable;
2. if a session ended abnormally, **restart the MagTag first** and wait for
   `dev_display_ready`, then the Fruit Jam — see
   [DEVELOPMENT_RUNTIME.md](DEVELOPMENT_RUNTIME.md);
3. to restart both, pull the **upstream** cable, wait for both boards to go dark,
   and reconnect. That is a simultaneous cold start, which the MagTag ordering
   rule tolerates because neither board is mid-session;
4. do not pull a single downstream cable to reset one board while the other is
   mid-frame. That is the interrupted-session case, and it costs a MagTag
   restart.

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
