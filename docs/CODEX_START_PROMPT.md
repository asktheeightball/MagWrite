# Codex Start Prompt

You are a senior embedded systems engineer working in the `asktheeightball/MagWrite` repository.

Read `README.md`, `PRODUCT.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `HARDWARE.md`, and `PROTOCOL.md` before making changes.

## Objective

Implement Priority 0 and the smallest useful portion of Priority 1: a MagTag typing-feasibility harness that proves the physical original MagTag can perform non-blocking, no-flash partial refresh while preserving every simulated key event.

## Constraints

- Do not begin Bluetooth or Wi-Fi implementation yet.
- Do not claim hardware tests passed unless they were run on the physical device.
- Confirm the MagTag revision before using a UC8151D/IL0373 driver.
- The current research driver is `bciuca/magtag-partial-refresh-driver` and is GPL-3.0-or-later. Preserve all required notices and document the resulting licence implications before copying or deriving source.
- Use CircuitPython compatible with the physical MagTag revision.
- Keep editor logic independent from CircuitPython display modules so it can be host-tested.
- Do not block editor/input processing while a partial refresh is active.
- Treat the text buffer as authoritative, never the framebuffer.
- Keep all memory structures bounded.

## Required implementation

1. Inspect the repository and write a concise implementation plan.
2. Add a hardware-revision gate and clear setup instructions.
3. Add or integrate a compatible no-flash 1-bit MagTag display driver only if the physical revision is confirmed compatible.
4. Implement a minimal host-testable line-oriented editor buffer.
5. Implement a simulated key-event producer capable of generating deterministic text at configurable rates equivalent to 40, 60, and 80 WPM.
6. Render a monospaced landscape writing view with a static block or underscore cursor.
7. Track document revision and displayed revision separately.
8. Start partial refresh asynchronously when supported.
9. Continue consuming simulated events while the display is busy.
10. Immediately schedule the newest snapshot after the display becomes idle when the visible revision is stale.
11. Add structured serial logs for event count, document revision, displayed revision, refresh start/end, refresh duration, stale-frame count, and full-refresh count.
12. Add a configurable periodic full-refresh interval.
13. Add host tests proving event order, no loss, editor correctness, revision catch-up, and bounded queues.
14. Create `docs/HARDWARE_TEST_PLAN.md` with repeatable tests at 20, 50, 100, 500, and 1,000 updates.
15. Update `ROADMAP.md` only with work actually completed and verified.

## Acceptance criteria

Automated:

- all host tests pass;
- simulated 80 WPM input loses and reorders zero events;
- document revision always reaches the total accepted event count where applicable;
- displayed revision catches up after simulated display-busy periods;
- queue overflow is explicit and testable.

Hardware, unverified until run:

- first full refresh succeeds;
- subsequent updates are no-flash partial refreshes;
- average refresh duration is measured;
- input simulation continues during refresh;
- ghosting and pixel condition are recorded at each test interval.

## Completion report

Provide:

- files created or changed;
- exact CircuitPython version and dependencies;
- exact copy/install steps;
- automated test commands and results;
- hardware tests run versus still pending;
- licensing implications;
- known risks;
- the next smallest implementation step.

Do not expand into a full journal application until this feasibility gate is complete.