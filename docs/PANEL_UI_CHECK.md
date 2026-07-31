# MagTag font and button footer — physical check

> **RUN 2026-07-31 — ALL SEVEN ITEMS PASSED.** The final configuration is
> `terminalio.FONT`, native scale 1, a 6×12 cell, **48 columns by 6 content
> rows**. The operator confirmed every item on the panel and the standalone cold
> boot recovered the document. One blocker was found and fixed first — see
> "What the check found" at the end. Evidence:
> [FRUITJAM_V17_UI_SERIAL.jsonl](FRUITJAM_V17_UI_SERIAL.jsonl).

The smallest check that settles V1.7. Not a harness: no guard, no remount, no
PASS/FAIL verdict written by a board. It runs the shipped configuration and
reports what the panel looks like.

Everything V1.7 changed is something a person looks at, so a host test can prove
the geometry is consistent and cannot prove any of what matters here. What
matters here is whether the text is comfortable to read, whether four labels sit
over the four buttons they name, and whether an arrow reads as an arrow on
e-paper.

## Configuration under test

The shipped configuration, unmodified — the same one-cable rig as
[STANDALONE_CHECK.md](STANDALONE_CHECK.md). Nothing is armed and no flag is set.

```text
5 V supply, ≥1.5 A ──► one USB-C cable ──► Fruit Jam
                                             │
                                             ├── USB-A ──► wired USB keyboard
                                             │
                                             └── USB-A ──► USB-A-to-USB-C ──► MagTag
```

## Before the cable is connected

1. **Deploy both boards while they are still reachable, MagTag first** — its
   USB-C is about to be occupied by the Fruit Jam, so this is the last moment its
   `CIRCUITPY` is host-writable.
2. **Do not edit either `config.py`.** The shipped defaults are what is under
   test.
3. Disconnect both boards from the PC and power the device from the charger.

## Procedure

Steps 1–3 are answered by looking at the first screen that appears; the rest need
the device driven for a minute.

1. **The built-in font is used throughout.** Every screen — startup, menu,
   drafts, editor, and the status field — is in the same monospace face, with
   real lowercase letterforms rather than the old 3×5 approximations. Nothing on
   any screen is drawn in the old table's shapes.
2. **The scale is comfortable to read** at the distance the device is actually
   used from. Scale 1 is what shipped, on the reasoning that the built-in font's
   6 px advance is exactly what the previous font drew at scale 2 — so this
   should read no smaller than V1.6 did, and should read *better*. If it does
   not, say so: the fix is a layout change, not a tweak, because a larger integer
   scale costs rows and columns.
3. **Editor and menu content fit.** No line runs off the right edge, no row is
   clipped at the top or bottom, the title and status do not collide, and the
   cursor underline sits under its own row rather than touching the row below.
   Type past the right edge of a line and confirm it wraps at 48 columns; fill
   the panel and confirm six rows are visible.
4. **`MENU`, ▲, ▼, and `SELECT` sit over the correct buttons.** Read left to
   right along the bezel: `MENU` over A, ▲ over B, ▼ over C, `SELECT` over D.
   Each label should be centred on its button, not merely near it.
5. **The arrows render clearly** as up and down arrows — a solid triangle over a
   stem — and are not mistakable for a letter.
6. **All four buttons still do the right thing.** A opens the menu and leaves the
   editor; B and C move the selection one item per press; D opens the selected
   item. Nothing a button does may have changed.
7. **No regression.** Startup reaches the recovered document, the previous
   document and mode come back, typing works, Escape saves silently and returns
   to the menu, the reopened text is intact, and a power cycle recovers the same
   document. Confirm the footer is present and clean on **partial** refreshes as
   well as the first full one — it is drawn identically every frame, so a partial
   refresh should leave it untouched with no ghosting or doubling.

## What a failure means

- **Step 2 fails** — the layout is recomputed at the next integer scale and the
  column and row counts fall out of it. It is not a config change; both boards'
  capacity constants and the protocol payload bound follow the font.
- **Step 4 fails with the labels reversed** — the panel's left-to-right order is
  the mirror of the bezel's. One line, `button_footer.FOOTER_ACTIONS`, reversed.
- **Step 5 fails** — the arrow geometry is in `button_footer.draw_arrow` and
  costs nine rectangles; making it larger or heavier is local.
- **Step 6 or 7 fails** — that is a regression rather than a UI question, and it
  blocks the milestone.

## Evidence

Every question above is a question about an image, so the operator's observation
is the only answer to items 1 through 4 and 7. Unlike the V1.6 standalone check,
though, the first pass was run with the upstream cable in the PC rather than the
charger — the same one-cable rig with a console attached — so the *mechanical*
half of items 5 and 6 has a record rather than only a recollection:
[FRUITJAM_V17_UI_SERIAL.jsonl](FRUITJAM_V17_UI_SERIAL.jsonl). The second pass,
the standalone cold boot, has no console by design and no record, exactly as V1.6
had none.

## Result — 2026-07-31 — PASSED

All seven items passed, with the operator reporting no faults and the capture
showing none.

What the console recorded during the session, none of which contradicts anything
observed:

| | |
| --- | --- |
| Buttons | 4 pressed, 4 applied, ordinals 1–4, **zero** duplicates, drops, or unknown actions |
| Actions exercised | `MENU` left the editor, `UP` moved the selection, `MENU` **at the main menu did nothing and did not end the session**, `SELECT` opened Journal |
| Typing | 46 HID reports → 23 normalized events → 23 applied, none lost |
| Document | `NOTE 5` recovered at 30 characters, grew to 53, 3 checkpoints and 4 journal appends |
| Silent save | `shell_left_editor` → `CHECKPOINTED` / `SAVED`, straight to the menu |
| Refreshes | 1 full at 3,470 ms, 7 partial averaging **898 ms** |
| Reconciliation | 8 viewports sent, 20 superseded, all 8 displayed and hash-matched |
| Faults | none of any kind |

**The wider panel cost no refresh time.** 898 ms average against V1.6's 924 ms
over 24 partial refreshes, on roughly double the text. The glyph-row cache was
added on a host measurement that the naive blit was 4.3× the old table's work;
this is the panel saying that concern is closed.

### What the check found

**One blocker, in the product path, and not in the UI.** The first attempt showed
`STARTING` and then `WAITING` and never reached a document, because the Fruit Jam
was not running at all: `dev_runtime.py` re-asserts the protocol constants as a
literal and was still demanding the old 192-byte payload maximum, so it raised
`protocol constants do not match the verified wire format` and dropped to the
REPL within nine seconds. The MagTag was behaving correctly throughout — it was
waiting for a board that was never going to speak.

The whole host suite, `compileall`, the UART validator, and the compatibility
sweep had all passed, and **none of them could have caught it**: the file imports
`board` and cannot be imported on the host. That is the same defect class
`host-tests/test_dev_runtime.py` was written for, so the fix ships with the
static assertion that closes it. Fixed, deployed, and re-checked in the same
session.
