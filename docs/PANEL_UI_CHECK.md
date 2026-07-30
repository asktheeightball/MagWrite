# MagTag font and button footer — physical check

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

Like the V1.6 standalone check, this one runs with no console on either board, so
the panel is the only instrument and the operator's observation is the only
record. Nothing here measures a timing, a refresh count, or a character total,
and nothing claims one. Photographs of the panel are the one artefact worth
keeping, because every question above is a question about an image.
