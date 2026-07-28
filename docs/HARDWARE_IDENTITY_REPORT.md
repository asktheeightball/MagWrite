# MagTag Hardware Identity Report

## Inspection

- Date: 2026-07-28
- Repository: `asktheeightball/MagWrite`
- Physical device: MagTag connected as the `CIRCUITPY` removable volume at
  `E:\`; USB serial interface enumerated as `COM10`
- Compatibility decision: **`COMPATIBLE`**
- Confidence: **high**

No display refresh, device-file write, factory reset, or hardware acceptance
test was performed.

## Exact `boot_out.txt`

Captured read-only from `E:\boot_out.txt`:

```text
Adafruit CircuitPython 9.1.1 on 2024-07-22; Adafruit MagTag with ESP32S2
Board ID:adafruit_magtag_2.9_grayscale
UID:C7FD1A005DEA
```

This confirms CircuitPython 9.1.1, its 2024-07-22 build date, the generic
`adafruit_magtag_2.9_grayscale` board build, and ESP32-S2. It does not identify
the display controller.

## Filesystem and USB evidence

Read-only host observations:

```json
{"volume":"CIRCUITPY","drive":"E:\\","type":"Removable","filesystem":"FAT","total_bytes":963072,"free_bytes":792576}
{"usb_serial_port":"COM10","usb_serial_name":"USB Serial Device","uid":"C7FD1A005DEA"}
```

The volume contained an existing user `code.py`, `secrets.py`, token file,
library directory, and bitmap directory. Their contents were not inspected or
modified. The existing program was not interrupted.

### Runtime diagnostic output

Not captured. Running a new script would have required interrupting or replacing
the existing device program. A read-only, structured diagnostic is provided at
`tools/magtag_identity_diagnostic.py`; it performs no display refresh and no
filesystem write. Its output remains pending.

The generic board ID must not be treated as controller evidence.

## Physical markings

Three photographs supplied on 2026-07-28 show the full front, full rear PCB,
display connector, and display flex.

Observed directly:

- orange display flex marking: **`WFT0290CZ10`**;
- second flex line: **`LW`**;
- original-style MagTag rear layout with ESP32-S2 module, USB-C, Reset and
  Boot0 switches, four standoffs, display connector, battery connector, and
  MagTag/Adafruit silkscreen;
- front is the 296x128 grayscale MagTag display with four buttons;
- display is operating under CircuitPython 9.1.1 and shows the existing weather
  application.

No `SSD1680`, `EAAMFGN`, 2025-edition, `FPC-A005`, or `FPC-7519rev.b` marking is
visible.

## Authoritative comparison

Adafruit's current MagTag guide states:

- the display changed on **2025-07-22** from the discontinued ILI0373-family
  hardware to SSD1680;
- the 2025 SSD1680 edition requires CircuitPython 10 or later and does not work
  with CircuitPython 9.2.x or earlier;
- the original display maps to the `GxEPD2_290_T5` /
  `ThinkInk_290_Grayscale4_T5` family;
- the 2025 display maps to `ThinkInk_290_Grayscale4_EAAMFGN`.
- Adafruit's product page identifies its 2.9-inch 296x128 panel as UC8151D, and
  Adafruit staff documented a physically checked `WFT0290CZ10 LW` panel as
  UC8151D with the T5 driver type.

Sources:

- [Adafruit MagTag overview and revision history](https://learn.adafruit.com/adafruit-magtag?view=all)
- [Adafruit MagTag display connector and variant information](https://learn.adafruit.com/adafruit-magtag/pinouts)
- [Adafruit MagTag downloads and original/2025 factory images](https://learn.adafruit.com/adafruit-magtag/downloads)
- [Adafruit 2.9-inch 296x128 UC8151D panel](https://www.adafruit.com/product/4262)
- [Adafruit staff verification of `WFT0290CZ10 LW` as UC8151D](https://forums.adafruit.com/viewtopic.php?t=192790)

### Evidence classification

| Evidence | Classification | Meaning |
|---|---|---|
| ESP32-S2 and generic MagTag board ID | Confirmed | Identifies the board family, not the display controller |
| CircuitPython 9.1.1 built in July 2024 | Strongly indicated | Consistent with a pre-2025 device, but firmware can be installed independently of physical revision |
| Existing files dated July/August 2024 | Strongly indicated | Consistent with use before the 2025 hardware change, but timestamps are not controller identification |
| Runtime controller metadata | Inconclusive | Not captured; it may not expose the controller in this build |
| `WFT0290CZ10 LW` flex marking | Confirmed | Matches the panel marking Adafruit physically verified as UC8151D/T5 |
| Original MagTag physical layout | Confirmed | Matches the pre-2025 board and contradicts no observed feature |
| SSD1680 identity | Contradicted | No 2025/SSD1680-family marking; photographed panel marking is documented as UC8151D |
| UC8151D/T5 identity | Confirmed | Physical flex marking plus Adafruit's panel verification positively identifies the supported family |

## Conclusion

The photographed `WFT0290CZ10 LW` flex marking positively identifies the
UC8151D/T5-family panel when compared with Adafruit's documented physical
verification. The full device evidence is consistent: original MagTag layout,
CircuitPython 9.1.1 from 2024, and a functioning 296x128 grayscale display.

**Decision: `COMPATIBLE`.**

This decision establishes hardware identity only. `ENABLE_PHYSICAL_DISPLAY`
remains `False`, no display driver has been incorporated, and no partial-refresh
or acceptance test has been run.

## Remaining uncertainty

- whether runtime metadata exposes a useful discriminator;
- the exact controller silicon revision beyond the documented UC8151D/T5
  family association;
- actual compatibility with the research implementation, which remains
  unverified until the separately authorized controlled hardware test;
- refresh timing, ghosting, pixel condition, and safe full-refresh cadence.
