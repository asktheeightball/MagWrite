# Third-Party Notices

## `bciuca/magtag-partial-refresh-driver`

- Upstream: <https://github.com/bciuca/magtag-partial-refresh-driver>
- Incorporated commit: `61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`
- Upstream copyright: Copyright (c) 2026, BC
  (<https://github.com/bciuca>)
- Licence: GNU General Public License v3.0 or later
- Incorporated verbatim:
  - `magtag/uc8151.py`, from upstream `uc8151.py`
- SHA-256:
  - `uc8151.py`:
    `A534B79DA5FC220EFBA5C61EE48048B54BAD3725CEFEC6D3BD7109233D75176E`

The upstream driver states that `uc8151.py` is a port of Jean-Marc Zingg's
GPL-3.0 `GxEPD2_290_T5D`, with the partial-refresh waveform corroborated
against Pimoroni Ltd's MIT-licensed Badger 2040 UC8151 driver. All upstream
SPDX, copyright, derivation, scope, and safety notices are preserved.

## MagWrite modifications

The upstream file above is unmodified. MagWrite adds separate
GPL-3.0-or-later integration code:

- fail-closed compatibility, controller, activation, and explicit-test-mode
  gates;
- a lazy-import adapter that prevents pin or SPI access before those gates;
- explicit differential-state invalidation after power-off or timeout;
- a bounded one-full-plus-20-partial test runner;
- a persistent one-time execution guard;
- structured timing diagnostics and host mocks.

These additions do not imply that upstream authors wrote, reviewed, or
endorsed the MagWrite modifications.

## Distribution and corresponding source

MagWrite is distributed as a GPL-3.0-or-later combined work. The full licence
text is in `LICENSE`. Anyone conveying MagWrite, modified device firmware, or
object-code forms must comply with GPLv3, preserve notices, identify
modifications, and provide the complete Corresponding Source required to build,
install, run, and modify the covered work. The public repository source is the
preferred source form; distributors remain responsible for ensuring source
availability for their conveyance method and required duration.

This notice is an engineering record, not legal advice.
