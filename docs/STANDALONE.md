# MagWrite Standalone

The device a writer switches on. One USB-C cable into the Fruit Jam, and
everything else is the device's problem.

This is the **default** from V1.6. Nothing is armed, no flag is set, no console
is attached, no volume is mounted on a PC, and no board is reset in any
particular order. `docs/DEVELOPMENT_RUNTIME.md` describes the same runtime on a
bench with two consoles, which is now the thing you have to opt into.

## The flow this delivers

1. Connect one USB-C cable to the Fruit Jam.
2. The Fruit Jam powers the MagTag from one of its USB-A host ports.
3. Both boards start by themselves.
4. The previous document and its mode come back.
5. The four MagTag buttons reach the menu.
6. Journal, Quick Note, Drafts, or Recent opens a document.
7. The keyboard writes into it.
8. Leaving the editor checkpoints silently and returns to the menu.
9. Power comes out. There is no shutdown.

## What is on the panel, and when

A device with no console has to say what it is doing on the only screen it has.

| While | The panel shows | Drawn by |
| --- | --- | --- |
| the panel has just initialised | `MAGWRITE / STARTING` | the MagTag, locally |
| the writer board has said nothing for 15 s | `WAITING FOR THE WRITER BOARD` | the MagTag, locally |
| the card is being mounted and the document restored | still the starting screen — this all happens inside that window | — |
| there is no keyboard | `NO KEYBOARD - PLUG ONE IN` on the menu, and `k` in the status field of every frame | the Fruit Jam |
| there is no card | `x` in the status field, as since V1.2 | the Fruit Jam |
| the stored document cannot be opened | the reason, on the recoverable error screen | the Fruit Jam |
| a fault the link cannot report | the reason, plus `DISCONNECT POWER, RETRY` | the MagTag, locally |

The MagTag's two startup screens are the only thing it ever draws that the Fruit
Jam did not send it, and they are the narrowest exception the design allows:
they carry no document, no cursor, no revision, and no state the Fruit Jam owns,
and they are never drawn again once a viewport has arrived. They exist because
for the first several seconds of a standalone start the MagTag is the only board
that *can* speak — the link the Fruit Jam would report its progress on is the
link that is not up yet.

Fifteen seconds, because a measured cold boot took 9.05 s. An ordinary start
never draws the second screen; seeing it means something is worth checking.

## What the standalone profile changes

One block in `fruitjam/dev_runtime.py`, and nothing else. The appliance is not a
reduced build of the bench rig — it is the same editor, shell, storage,
transport, and buttons.

| | Development | Standalone |
| --- | --- | --- |
| Idle timeout | 1800 s | **none** |
| Session timeout | 7200 s | **none** |
| Keyboard event bound | 100,000 | **none** |
| Viewport / protocol frame bounds | 100,000 / 200,000 | **none** |
| Back at the main menu | the clean stop | **nothing** |
| Keyboard open attempts | unbounded, one per second | unbounded, one per second |
| A keyboard that cannot be opened | degraded, reported | degraded, reported |

Every bound removed is one that existed to end a **run**. A writer who pauses to
think has not gone idle in any sense worth ending a session over; a device that
has been powered since Tuesday has not overrun; a document that took 200,000
keystrokes is a manuscript. Every bound that protects **memory** is unchanged and
still enforced: the input queue, the acknowledgement tracker, the button inbox,
the status outbox, the USB poll budget, the input drain budget, the document
bounds, and the catalogue bound.

**There is no stop.** Escape at the main menu used to end the session, drain, and
leave a `STOPPED` screen that nothing but the reset button could move off — one
keystroke that switches the device off and no keystroke that switches it back on.
The MagTag's menu button has never been able to do that, deliberately; V1.6 makes
the keyboard agree with the bezel. Power is the stop.

## Failing safely

The rule is one sentence: **startup trouble must never cost somebody their work.**

- **No card.** The editor runs, the panel shows `x`, nothing is persisted, and
  the writer is told rather than misled. Unchanged since V1.2.
- **No keyboard.** The menu says so and the buttons still work. The device keeps
  looking, once a second, for as long as it has power — so a keyboard plugged in
  afterwards is picked up with no reset. Before V1.6 it gave up after thirty
  seconds and latched, which meant a device switched on before its keyboard never
  saw that keyboard at all.
- **A device on the port that is not a keyboard** — a hub, an incompatible
  receiver. Reported, counted, and retried. Not a stop.
- **The stored document cannot be opened.** The card is not touched. Writes are
  *held* for the rest of the session, because the editor would otherwise be empty
  at revision 0 while the store still held the real document, and the next
  checkpoint due on age would write the empty one over it. The shell opens at the
  menu with the reason on the recoverable error screen; SELECT dismisses it, and
  opening any document from Drafts releases the hold.
- **Typing before the panel answers.** Keystrokes are queued during the wait and
  applied the moment it comes up. What no longer happens is the session *ending*
  when the 64-event queue fills — losing the tail of a sentence typed at a blank
  panel is a small cost; a device that switches itself off because somebody was
  keen is not. The drop is counted and named once.

## Activation

Both boards ship ready. These are the settings, for reference rather than for
editing.

Fruit Jam, `fruitjam/config.py`:

```python
ENABLE_STANDALONE = True
STANDALONE_MODE = "FRUITJAM_STANDALONE"
```

MagTag, `magtag/config.py`:

```python
ENABLE_PHYSICAL_DISPLAY = True
PHYSICAL_TEST_MODE = "MAGTAG_STANDALONE"
ENABLE_UART_RECEIVER = True
ENABLE_UART_STATUS_TX = True
ENABLE_STANDALONE = True
STANDALONE_DISPLAY_MODE = "MAGTAG_STANDALONE"
```

### This is not a weakening of the fail-closed gate

Every guarded harness still ships disabled and still has to be armed by name, and
an armed harness still wins — `fruitjam/code.py` and `magtag/code.py` check all of
them before falling through to the standalone branch. The MagTag's compatibility
decision is still checked first and still refuses an unconfirmed or incompatible
board. Host tests assert each of those.

What changed is what the flags *mean*. `ENABLE_PHYSICAL_DISPLAY = False` was the
right default for a board that might be the wrong MagTag; on a finished device it
said "this writing appliance may not use its screen". `MAGTAG_STANDALONE` is
deliberately **absent** from the boot remount tuple in `hardware_test_boot.py`,
exactly as `MAGTAG_DEV_DISPLAY` is: the runtime writes no guard, so it needs no
writable filesystem, and CIRCUITPY stays under the host's control.

## Deployment

Copy the repository files for each board onto its CIRCUITPY volume:

```text
fruitjam/  ->  Fruit Jam CIRCUITPY   (code.py, boot.py, config.py, dev_runtime.py, magwrite_transport/)
magtag/    ->  MagTag CIRCUITPY      (code.py, config.py, dev_display_runtime.py, uc8151.py, magwrite/)
```

Then disconnect both from the PC and power the Fruit Jam. Nothing else is
required, and there is no start order — see `docs/BENCH_POWER.md` for why the
hardware cannot have one.

**A board's hand-armed `config.py` is never overwritten.** If a board has been
deliberately set up for a harness, leave its config alone.

## The names, and why they were kept

The entry points are still `fruitjam/dev_runtime.py` and
`magtag/dev_display_runtime.py`, and they still log `dev_runtime_ready`,
`dev_display_ready`, and the rest. That is a decision rather than an oversight.
Those event names are the vocabulary every physical evidence file in this
repository is written in, and renaming them would make the record harder to read
in exchange for a tidier filename. What the console says instead is which profile
it is running: `"profile": "STANDALONE"` or `"profile": "DEVELOPMENT"`, in the
ready line, the session summary, and the stopped record.

## Diagnostics, if a console is attached

Everything in `docs/DEVELOPMENT_RUNTIME.md`, plus:

| Event | Means |
| --- | --- |
| `dev_runtime_ready` with `"profile": "STANDALONE"` | the appliance started |
| `"stop_from": "NOWHERE"` | the back gesture cannot end this session |
| `"idle_timeout_seconds": null` | the run-length bounds are removed |
| `live_keyboard_state` | a keyboard was claimed or lost; `indicator` is what the panel now draws |
| `usb_keyboard_open_failed` with `"fatal": false` | something on the port could not be driven; still looking |
| `live_input_dropped_waiting_for_display` | typed faster than the boot; the queue was full |
| `live_document_restore_refused` | the stored document would not load; the card was not touched |
| `document_writes_held` / `document_writes_released` | writing was suspended, then resumed by an open |
| `display_startup_screen` | the MagTag drew one of its own two screens |

## What this does not do

It does not sleep, wake, or shut down. There is no sleep state, no wake source,
and no shutdown sequence — the device is on while it has power and off when it
does not, and every editor exit checkpoints, so removing power is safe at any
moment. Power management belongs to the battery phase, where there is something
to manage.

It does not make a 30-minute unattended claim. Removing the timeouts makes a long
session *possible*; it is not evidence that one has been run.
