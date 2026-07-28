# Physical Refresh Test: 50 Updates

Status: **PASS**

This independent run uses one fresh full seed followed by exactly 50 partial
updates in mode `REFRESH_50`. Checkpoints are 0, 10, 20, 30, 40, and 50.

- Hardware: original MagTag 2.9, UC8151D, compatibility `COMPATIBLE`
- CircuitPython: 9.1.1
- Driver: `bciuca/magtag-partial-refresh-driver` commit
  `61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437`
- Start guard: `/magwrite_refresh_test_50.started`
- Completion guard: `/magwrite_refresh_test_50.complete`
- Reviewed-pass signal: `/magwrite_refresh_test_50.pass`
- Activation before execution: disabled / `DISABLED`
- Result and timing: first attempt stopped at index 0 before display refresh;
  the deterministic pattern referenced a missing `C` glyph. No timing exists.
- Stop evidence: `/magwrite_refresh_test_50.started` was created; no completion
  guard was created. The guard is preserved and no automatic retry was made.
- Authorized rerun: full seed completed in 3,324 ms with no timeout or reported
  busy anomaly. Execution is paused at checkpoint 0 pending visual inspection.
- Checkpoint 0: photograph saved as
  `PHYSICAL_REFRESH_TEST_50_INITIAL.png`; visually clean.
- Checkpoint 10: user confirmed good; no photograph supplied.
- Checkpoint 20: user confirmed good; no photograph supplied.
- Checkpoint 30: user confirmed good; no photograph supplied.
- Checkpoint 40: user confirmed good; no photograph supplied.
- Checkpoint 50: user confirmed the final frame good, including no unexpected
  flashing, severe ghosting, transition defect, border corruption, heating, or
  power instability; no final photograph was supplied.

## Successful rerun result

- Date/time completed: 2026-07-28 12:57 EDT
- Initial full refresh: 3,324 ms
- Partial updates: 50/50
- Partial minimum/maximum: 716/719 ms
- Partial mean/median: 717.5/718.0 ms
- Population standard deviation: 0.8 ms
- First-to-final-ten timing drift: -0.6 ms
- Timeouts and busy anomalies: 0
- Stop conditions: none
- Final displayed pattern revision: 50
- Completion guard: `/magwrite_refresh_test_50.complete`, present
- Activation after run: `False` / `DISABLED`, restored and hash-verified
- Photographs: `PHYSICAL_REFRESH_TEST_50_INITIAL.png`; intermediate and final
  photographs were not supplied and are not fabricated.

Conclusion: **PASS**. Timing remained stable and the user visually approved
every checkpoint. This supports proceeding to the independent 100-update run
after creation of the explicit reviewed-pass signal. It does not establish a
production full-refresh cadence or long-term panel lifetime.

Files to copy are `config.py`, `hardware_test_boot.py`,
`hardware_characterization_test.py` as `/code.py`, `uc8151.py`, and the
`magwrite` package. Stop conditions and explicit guard reset procedure are in
`docs/HARDWARE_TEST_PLAN.md`.
