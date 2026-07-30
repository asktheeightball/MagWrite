# Minimum standalone workflow — physical check

The smallest check that settles whether V1.6 delivers what
[STANDALONE.md](STANDALONE.md) describes. Not a harness: no guard, no remount, no
PASS/FAIL verdict written by a board. It runs the shipped configuration and
reports what happened.

The intended finished behaviour is one sentence long: **MagWrite is a basic
standalone writing machine, from one power cable, with no development PC.**

## Configuration under test

The shipped configuration, unmodified. Nothing is armed and no flag is set.

```text
5 V supply, ≥1.5 A ──► one USB-C cable ──► Fruit Jam
                                             │
                                             ├── USB-A ──► wired USB keyboard
                                             │
                                             └── USB-A ──► USB-A-to-USB-C ──► MagTag
```

UART unchanged: Fruit Jam `A0` TX → MagTag `D10` RX, MagTag `A1` TX → Fruit Jam
`A1` RX, common ground, 115200 baud, **red/power conductor disconnected and
insulated**.

**Neither board is connected to the PC.** That is the point of the check: there
is no console on either board, no host-visible `CIRCUITPY`, and no way to
intervene. Everything the check needs to see is on the panel.

## Before the cable is connected

1. **Deploy both boards while they are still reachable**, and deploy the MagTag
   first — its USB-C is about to be occupied by the Fruit Jam, so this is the
   last moment its `CIRCUITPY` is host-writable. Copy the current `magtag/` and
   `fruitjam/` payloads.
2. **Do not edit either `config.py`.** The shipped defaults are what is under
   test. If a board's config has been hand-armed for a harness, that board is not
   in the configuration this check is about.
3. **Confirm by eye** that the UART cable carries only TX, RX, and ground, and
   that the red conductor is still disconnected and insulated at both ends.
4. Confirm both board power switches are ON.
5. Disconnect both boards from the PC.

## Procedure

1. Power the device through the Fruit Jam's USB-C input.
2. Confirm it **starts without intervention** — no reset, no order, nothing
   pressed. Expect `MAGWRITE / STARTING` on the panel within a second or two, and
   the document or menu within about ten.
3. Confirm the previous document and its mode recover — the words are there, the
   title names the document, and the cursor is where it was.
4. Use the MagTag buttons to reach the menu (**A**) and select a document
   (**B**/**C** to move, **D** to open).
5. Type a short paragraph.
6. Leave the editor (**A**, or Escape) and confirm it returns **directly** to the
   menu — no save screen, no second press.
7. Reopen the document and confirm the text is intact.
8. Remove power.
9. Restore power and confirm the same document recovers automatically.
10. Repeat once with **the keyboard disconnected at startup**. Confirm the device
    still reaches the menu, that the menu says `NO KEYBOARD - PLUG ONE IN`, and
    that the buttons still navigate. Then connect the keyboard and confirm
    writing becomes available **without rebooting** — the notice clears and
    typing reaches the document.

Throughout: watch for unexplained resets, a panel that stops updating, and
anything hot to the touch.

## What would fail it

- either board failing to start, or needing a reset, a start order, or any
  operator action;
- a panel that shows nothing at all during the boot window;
- a restored document that comes back short, altered, or empty;
- leaving the editor losing the paragraph, or landing anywhere but the menu;
- the second power cycle recovering a different document, or none;
- the keyboard-disconnected start failing to reach a usable menu;
- a keyboard connected after startup never being picked up — this is the
  specific defect V1.6 fixed, and step 10 is the reason the check exists;
- the device ending its own session for any reason: a `STOPPED` screen, a frozen
  panel, or a device that stops responding to buttons;
- anything hot to the touch.

## What this check deliberately does not cover

- **the 30-minute session** named in the roadmap's exit criterion. This check is
  minutes long. Removing the run-length bounds makes a long session possible; it
  is not evidence that one has been run;
- **current, thermal, or battery behaviour.** There is still no meter on the
  bench;
- **the wireless receiver.** Untouched, and still blocked on hardware;
- **rename, archive, or dated journal entries.** Not delivered, and named as not
  delivered in `PRIORITY.md`;
- **sleep, wake, and shutdown.** There is no sleep state and no shutdown
  sequence; the device is on while it has power. See `STANDALONE.md`.

## Result

**NOT YET RUN.** V1.6 is host-verified only, across 1,185 host tests including 49
new ones written for exactly the failures above. No claim of physical
verification is made and none may be recorded here until this check has been
performed on the bench.
