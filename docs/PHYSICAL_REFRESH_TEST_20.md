# Controlled 20-Update Physical Refresh Test

Status: **PASS**

Run date: 2026-07-28, America/Toronto.

## Fixed configuration

- Hardware identity: original MagTag, `WFT0290CZ10 LW`
- Compatibility decision: `COMPATIBLE`
- Controller: `UC8151D`
- CircuitPython: `9.1.1`
- Upstream:
  `https://github.com/bciuca/magtag-partial-refresh-driver`
- Upstream commit: `61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`
- Initial refresh: one full refresh that seeds OLD and NEW RAM
- Controlled updates: exactly 20 differential partial refreshes
- Physical activation default: disabled
- Explicit mode: `UC8151_20_UPDATE`

## Files to copy

```text
magtag/hardware_test_boot.py       -> /boot.py
magtag/hardware_refresh_test.py    -> /code.py
magtag/config.py                   -> /config.py
magtag/hardware_identity.py        -> /hardware_identity.py
magtag/hardware_gate.py            -> /hardware_gate.py
magtag/uc8151.py                   -> /uc8151.py
magtag/magwrite/                   -> /magwrite/
```

No external CircuitPython library is required.

## Activation conditions

All four must be true:

```python
HARDWARE_COMPATIBILITY_DECISION = "COMPATIBLE"
DISPLAY_CONTROLLER = "UC8151D"
ENABLE_PHYSICAL_DISPLAY = True
PHYSICAL_TEST_MODE = "UC8151_20_UPDATE"
```

The first armed boot writes `/magwrite_refresh_test_20.started` before display
initialization. The file is never automatically removed. Successful completion
also writes `/magwrite_refresh_test_20.complete`. Either file blocks another
run after autoreload or reboot; deliberate removal is required to re-arm.

## Controller state

The full seed writes the current framebuffer to both OLD (`0x10`) and NEW
(`0x13`) RAM. Each partial refresh writes NEW and relies on controller-managed
NEW-to-OLD state for the next differential update. Power-off, reinitialization,
or timeout invalidates that state and forces the next refresh to be full. The
test does not power off between controlled updates.

## Results

- Date: 2026-07-28
- Device backup:
  `C:\tmp\MagWrite-CIRCUITPY-backup-20260728-physical20` (74 items)
- Exact files copied:
  `/boot.py`, `/code.py`, `/config.py`, `/hardware_identity.py`,
  `/hardware_gate.py`, `/uc8151.py`, and `/magwrite/*.py`, using the mappings
  above
- Upstream driver SHA-256:
  `A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E`
- Initial full-refresh duration: **3,324 ms**
- Partial timings, ms:
  `718, 718, 718, 718, 716, 718, 718, 719, 720, 718, 718, 718, 718, 718, 718, 719, 718, 718, 718, 718`
- Partial minimum/maximum/mean: **716 / 720 / 718 ms**
- Completed partial updates: **20**
- Final displayed revision: **20**
- Final document revision: **20**
- Timeout count: **0**
- Persistent guards:
  `/magwrite_refresh_test_20.started` and
  `/magwrite_refresh_test_20.complete`
- Activation after run:
  `ENABLE_PHYSICAL_DISPLAY = False`,
  `PHYSICAL_TEST_MODE = "DISABLED"`
- Ghosting: no obvious retained test-pattern elements in the final photograph
- Incomplete erasure: not observed in the final photograph
- Pixel condition: no obvious dead or weak pixel region at the supplied
  photograph's resolution
- Border artefacts: no unexpected border artefact observed
- Unexpected full-screen flashes: **none observed by the user during the run**
- Photographs: final update-20 frame preserved as
  `docs/PHYSICAL_REFRESH_TEST_20_FINAL.png`; intermediate full-seed/update-5/
  update-10 photographs were not captured
- Raw serial diagnostics:
  `docs/PHYSICAL_REFRESH_TEST_20_SERIAL.jsonl`

The serial record proves one full seed followed by exactly 20 completed partial
refresh commands with no timeouts. The user physically observed no flashing.
The supplied final photograph clearly shows `UPDATE 20 / 20`, the expected
filled rectangle and final marker, stable borders, and no obvious incomplete
erasure or pixel defect at the image's resolution.

Conclusion: **PASS**
