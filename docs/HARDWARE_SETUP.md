# MagTag Hardware Setup Gate

No physical display driver is currently included. The repository fails closed
until the exact board and panel controller are recorded. Host tests do not
confirm hardware compatibility.

## Required revision check

1. Disconnect power and photograph the front, rear, product label, and visible
   display flex/board markings.
2. Record the purchase date and source.
3. Connect by USB and save the complete `boot_out.txt` from `CIRCUITPY`.
4. Compare the board against Adafruit's original 2.9-inch MagTag documentation.
   Do not infer the controller from display dimensions alone.
5. Establish from markings or authoritative documentation that the controller
   is UC8151D/IL0373-compatible. If it is the 2025 SSD1680 edition, stop: the
   research driver is not approved for that panel.
6. Add the evidence and decision to `docs/HARDWARE_IDENTITY_REPORT.md`. Keep
   `magtag/hardware_identity.py` synchronized with that report, then change
   these values in `magtag/config.py` only after a `COMPATIBLE` decision:

```python
HARDWARE_COMPATIBILITY_DECISION = "COMPATIBLE"
MAGTAG_REVISION = "ORIGINAL_MAGTAG_2.9"
DISPLAY_CONTROLLER = "UC8151D"  # or "IL0373", matching the evidence
ENABLE_PHYSICAL_DISPLAY = True
```

The gate accepting those values is necessary but is not proof that the panel
is compatible.

## Fixed software baseline

- Adafruit CircuitPython **9.1.1** for `adafruit_magtag_2.9_grayscale`
- No external CircuitPython libraries are needed by the checked-in
  display-independent core.
- A physical display adapter is deliberately not included pending the revision
  check and licensing decision.

Install `adafruit-circuitpython-adafruit_magtag_2.9_grayscale-en_US-9.1.1.uf2`
using Adafruit's normal UF2 bootloader procedure. After the board restarts as
`CIRCUITPY`, copy these paths to the drive:

```text
magtag/code.py              -> /code.py
magtag/config.py            -> /config.py
magtag/hardware_gate.py     -> /hardware_gate.py
magtag/magwrite/            -> /magwrite/
```

With the repository's default configuration, boot must stop with a revision
gate error. That is the expected safe result.

For additional runtime evidence without refreshing the display, copy
`tools/magtag_identity_diagnostic.py` only after preserving the existing device
files, stop the current program from the serial console, and run the diagnostic
from the REPL. Capture every JSON line, then remove the temporary copy. Do not
replace an existing `code.py`.

## GPL driver decision

The research source `bciuca/magtag-partial-refresh-driver` is
GPL-3.0-or-later. No source from it has been copied, translated, or derived in
this change. Before incorporating it:

1. choose a GPL-3.0-compatible licence for the combined distributed program;
2. preserve upstream copyright and licence notices;
3. include the GPL text and corresponding source for distributed binaries;
4. identify local modifications and retain source availability obligations;
5. review whether any linked CircuitPython libraries introduce additional
   notice requirements.

This is an engineering summary, not legal advice. Until that decision and the
hardware confirmation are recorded, the next adapter must remain out of tree.
