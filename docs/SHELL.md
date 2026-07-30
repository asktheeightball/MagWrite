# The MagWrite Shell — V1.3, revised in V1.5

The application shell the writing modes live in. It comes after persistence
because a shell that cannot reliably open and save a document is a menu, not a
product.

This document carries the design and the reasoning. `ROADMAP.md` carries the
requirement map; `docs/PERSISTENCE.md` carries the durability argument the shell
depends on and does not repeat.

## What the shell is

One host-safe state machine, `fruitjam/magwrite_transport/shell.py`, that decides
**where the writer is** and **where input goes**. It holds no editor, no
document, no store, no clock, and no transport.

That is the whole design. The editor already owns the document, the cursor, and
both revisions; persistence already owns durability. A shell that reached into
either would become a second author of state that has to agree with the first
forever, and the two would eventually disagree at the worst possible moment.

```text
                        Enter / SELECT
              +---------------------------------+
              |                                 v
       +-------------+                   +-------------+
       |  MAIN MENU  | <---------------- |   EDITOR    |
       +-------------+   Esc / MENU      +-------------+
        |    ^   |       (checkpoints first)
        |    |   | Enter (Drafts)
        |    |   v
        |    |  +-------------+
        |    +--|   DRAFTS    |--- Enter / SELECT ---> EDITOR
        |       +-------------+
        |  Esc            any fault
        v                    |
      EXIT                   v
                       +-----------+   Enter / SELECT / MENU
                       |   ERROR   | -----------------------> MAIN MENU
                       +-----------+
```

> **V1.5 removed the Save/Status screen.** Leaving the editor used to go
> *through* it, with the menu drawn underneath and a second Enter needed to reach
> the menu. The forced checkpoint that screen existed to guarantee is unchanged
> and still unconditional; the screen, the extra keypress, and the frame in the
> way are gone. See *Leaving the editor* below.

`EXIT` is not a screen the writer navigates; it is the terminal state the session
reads to begin its ordinary drain-and-stop. It is in the same closed set so that
"where is the writer" always has exactly one answer.

## Navigation, and why it needed no new keys

| Gesture | MagTag button | Meaning |
| --- | --- | --- |
| Up / Down | **B** / **C** | move the selection (clamped, not wrapped) |
| Enter | **D** (select) | open the selected item; dismiss the error screen |
| Escape (or Keyboard Application) | **A** (menu) | **back** — leave the current state toward its parent |
| Ctrl-S | — | manual save, unchanged, at any time |

Up, Down, and Enter are already normalized editor events, so the menu reads the
same `InputEvent` stream the document does. Escape and Application were already
the finish control, with physical evidence behind them from V1.1.

So the shell adds **no keymap entry at all**. That was a requirement of the phase
and it is also the right design: a writing device with a private set of menu keys
is a device with two keyboards.

Back has one meaning everywhere — leave the current state toward its parent — and
at the root that is the clean stop the runtime always had, on the development
profile. This is the one behavioural change the shell makes to an existing
gesture, and it is what makes Escape safe to press inside a document. On the
standalone appliance the root has no parent and no stop; see below.

## Leaving the editor — V1.5

**Esc checkpoints the document and goes straight to the main menu.** One gesture,
no confirmation, no intermediate screen, and nothing on the panel between the
writer and the menu they asked for.

The checkpoint is unchanged and still unconditional, and it still happens for the
reason it always did: leaving the editor is the moment the writer is most likely
to walk away from the desk, and it is exactly when unsaved work is most exposed.
What changed is that the save happens **silently, in the background of the
gesture**, and — importantly — *before* the transition, so the destination can
depend on the result:

| Result | Where the writer lands |
| --- | --- |
| checkpointed | the main menu |
| no card to checkpoint to | the main menu, indicator `x` |
| the write actually failed | the error screen, with the reason |

### Why the screen went

The V1.3 argument for it was that *a screen every exit passes through makes the
checkpoint unconditional*. That was true of the checkpoint and it is still true —
but it was never an argument for the screen. The checkpoint is unconditional
because the code performs it unconditionally, not because a frame was drawn
afterwards.

What the screen actually did was report a result the writer had no decision to
make about, and charge them a keypress for reading it. Worse, it did so at the
one moment they had already expressed an intention — *take me out of this
document* — so it read as an obstacle rather than as information. The menu being
drawn underneath it made that unmistakable: the device knew where they were
going and stopped them anyway.

A save state that nobody has to act on belongs where a fact like that belongs:
the **one-character indicator in the status field of every ordinary frame**,
which has been there since V1.2 and is preserved exactly. The one save outcome a
writer can act on is a save that *failed*, and that reaches the error screen this
shell already had — which is a screen worth interrupting for, and the only one.

A card-less bench is deliberately **not** an error. It is the degraded mode the
panel has been drawing as `x` since V1.2; putting an error screen in front of
every exit on a bench with no card would recreate the interruption exactly.

## The four buttons — V1.5

The MagTag's four front buttons are the **primary** shell controls. The keyboard
keeps every shell key it had, as a fallback, but nothing in the intended product
flow requires it: a writer navigates with their thumbs and types with their
hands, and a device that needs a keyboard to answer its own menu is a device
with two control surfaces.

| Button | Action | In the menu | In a list | In the editor |
| --- | --- | --- | --- | --- |
| A | `MENU` | nothing | back to the menu | checkpoint, then the menu |
| B | `UP` | move up | move up | ignored |
| C | `DOWN` | move down | move down | ignored |
| D | `SELECT` | open the item | open the document | ignored |

Four decisions worth writing down.

**The MagTag sends actions, not buttons.** `UP`, not `B`. A raw identity would
force the Fruit Jam to know the panel's physical layout; a semantic one like
"next journal entry" would be the display board deciding product behaviour. *The
writer asked to move down* is the narrowest honest thing the MagTag knows, and it
is exactly what it says.

**No button reaches the document.** In the editor everything except A is counted
and discarded — including Up and Down, which could plausibly have moved the
cursor. A control surface that can alter a draft is one that can alter it from
inside a bag, and the buttons are on the outside of the device.

**A at the menu does nothing.** It is a *take me to the menu* button, not a back
button, so it cannot walk off the root and end the session. Escape still can on
the bench, because a writer who pressed Escape twice at the root meant it and a
thumb on a bezel did not.

**V1.6 finishes that thought for the appliance.** `Shell(allow_exit=False)` — the
standalone default — makes Escape at the root do what A has always done there:
nothing, counted as `shell_exits_refused`. The V1.5 reasoning was never really
about the bezel; it was about what a *stop* means on a device with one power
cable, which is a session that ends, drains, draws `STOPPED`, and cannot be
restarted by any key. One keystroke that switches the device off and none that
switches it back on. Escape still leaves every other state, so it is not a dead
key — only the root has nothing above it.

**Buttons and keys meet at the same handler.** `Shell.button` maps its three
movement actions onto the editor event kinds the keyboard already produces and
calls the identical per-state code. There is one definition of what Down means in
the Drafts list, and it cannot drift.

## Why no transition can lose unsaved work

Because no transition touches the document.

There is exactly one `MultilineEditor` for the life of the session. The shell
never constructs, clears, reloads, or truncates it; it changes what is drawn and
where input is routed. Leaving the editor cannot discard unsaved work for the
same reason closing a lid cannot: nothing was closed. That is as true of the
V1.5 one-gesture exit as it was of the two-step one — removing a screen removed
a frame, not a guarantee.

That is a structural guarantee rather than a policy one, which matters because a
policy can be forgotten by the next change and a missing line of code cannot be.
The forced checkpoint on the way out is the belt to that suspenders: the words are
durable as well as present.

For this phase all four menu items route into that same single document, which is
the scope the phase was given. The mode is carried anyway, and drawn in the
document's title, because a menu that gives no sign of which item was chosen is a
menu that is lying about having four items. It is also the seam V1.4 attaches its
per-mode policy to.

> **V1.4 update.** The four items now open four different things, so something
> has to change the editor's contents. The invariant is kept and made precise
> rather than dropped: there is still exactly one editor, the shell still never
> touches it, and a document switch is a **handover, not a close** — the outgoing
> document is checkpointed *before* anything is rebound. The shell may not open a
> card, so it records a bounded request and the session performs it in the same
> loop iteration, before any frame is built. See `docs/MODES.md`.

## Failing closed

Requirement: an invalid transition must show a recoverable error state rather
than crash or discard work.

Every entry point funnels through one private `_transition`, and anything it
cannot make sense of becomes `ERROR` with a recorded reason. `Shell.route`,
`Shell.back`, and `Shell.enter` do not raise. A shell that can crash the loop is a
shell that can lose the document sitting in RAM behind it, which is the one
outcome no menu is worth.

The error screen says `WORK IS KEPT`, because that is true and because it is the
first thing the writer will want to know.

One real behaviour changed here, and it is an improvement rather than a
formality. Reaching the document bound used to raise `LiveSessionError` and end
the session outright. The refused edit changes nothing, so the document is
intact; it is now shown on the error screen and the writer goes back to it. With
no shell present the old behaviour is unchanged.

## Restart and power loss

The opening state is **derived** from what the card returned, not stored:

- a recovered document with a revision above zero ⇒ open in the `EDITOR`, with
  the document and cursor restored;
- anything else ⇒ open at the `MAIN MENU`.

Persisting the shell state would mean a second file that has to stay in step with
the journal through a power cut — the two-file atomicity problem the storage
design already refused once, for a fact that can be derived correctly without it.
There is nothing to keep in step here: a recovered document means the writer was
writing, so the shell opens where their words are rather than making them find
their way back through a menu.

The **mode** was not restored with the state in V1.3 — `shell_restored` reported
`JOURNAL` after a session that ended in `RECENT`, as the 2026-07-30 bench run
shows. It was cosmetic then, because all four items routed into the one document,
and it followed from the same refusal: the mode was not derivable from what the
card returned, so restoring it would have needed the second file this section
just declined.

> **V1.4 update — this is closed.** It took the first of the two options this
> section named: the mode became a property of the recovered document, which is
> where it belongs. A document has a **kind** — `JOURNAL`, `NOTE`, or `DRAFT` —
> recorded in the catalogue alongside its identity and title, and the kind comes
> back with the words. Crucially this needed *no* second file to keep in step:
> the catalogue already had to exist for Drafts and Recent, and it is the same
> append-only, CRC-protected discipline as the recovery journal, with its own
> highest open ordinal standing in for the "active document" pointer this design
> would otherwise have had to invent. The *state* is still derived, exactly as
> above.

## Drawing: the same renderer, the same pacing

A shell screen is a semantic viewport like any other. It goes out through the
same `encode_viewport`, the same bounded payload, the same CRC-32, the same
acknowledgement tracking, and the same adaptive pacer the document uses. The
MagTag cannot tell a menu from a document and must not be able to: it draws the
lines it is given and interprets nothing.

There is deliberately no new display timing. A menu that redrew on its own
schedule would be a second pacing policy, and two pacing policies on one panel is
how a display ends up refreshing twice for one change.

Two consequences worth writing down:

- **The editor still owns both revisions.** A shell screen changing is visible
  state the editor does not own, so it advances `viewport_revision` through the
  same single door the save indicator uses, `editor.note_visible_change()`.
  Without that, two different payloads would go out under one revision number and
  the acknowledgement tracker would be reconciling frames that are not the same
  frame.
- **Every character must have a glyph.** `shell_viewport.SAFE_CHARACTERS` is
  asserted against the MagTag's real 3×5 table by a host test, and anything else
  is replaced. This is a fixed defect, not a habit: the first save indicator used
  `=` and `*`, which have no glyph, and the renderer raised `KeyError` on the
  first frame that carried one. Error text is the obvious repeat of that mistake,
  because it is the one string on the device that comes from an exception rather
  than a literal — which is also why `NO_CARD` is drawn as `NO CARD`. The
  underscore has no glyph.

The shell uses scenario id 7, distinct from the editor's 6, so a shell frame is
never mistaken for a document frame in a capture or a later reconciliation.

## The session wiring

`shell` is optional on `LiveTypingSession` on exactly the terms `persistence` is,
and for the same reason: with it absent every stage behaves as it did for the
runs that produced the existing physical evidence, so those payloads and CRC-32s
stay reproducible. `ENABLE_SHELL = False` in `config.py` reproduces V1.2 exactly.

With it present, three things change and nothing else does:

1. input is *routed* rather than assumed to belong to the editor;
2. the shell may put its own screen on the panel;
3. the finish gesture means back, and only the shell reaching `EXIT` ends the
   session.

The loop order follows the architecture's, with the shell at stage 5 — workflow
state, applied after input and durability and before any frame is built, so the
screen that goes out is the one the writer just asked for.

The finish gesture is serviced only when the input queue is empty, for the same
reason the pre-shell stop was: every keystroke pressed before the gesture is
already in the authoritative document, so leaving the editor can never outrun the
writing it is leaving. Repeated presses within one iteration collapse to one
action, exactly as manual save does — on a panel that trails by a second or more,
an accidental double press must not silently skip a level.

## What this phase is not

- no document browser — *added in V1.4 as the Drafts list, which is the one menu
  item whose answer the device cannot know for the writer*;
- no per-mode storage format, and no per-mode recovery rules — *still true in
  V1.4, and stated there as the rule rather than as a deferral*;
- no MagTag button work — the shell is keyboard-only by requirement, and the
  buttons remain a later phase that maps onto the same signals. *Delivered in
  V1.5, and onto exactly those signals: `Shell.button` adds no new meaning, it
  reaches the handlers the keyboard already reached*;
- no new certification harness. The development runtime already brings the shell
  up and logs every transition.

## Physical bench plan — run 2026-07-30, all twelve criteria met

The run is recorded in full in `ROADMAP.md`; the captures are
`docs/FRUITJAM_V13_SHELL_SERIAL.jsonl` and
`docs/MAGTAG_V13_SHELL_SERIAL.jsonl`. What follows is the plan as written, kept
because it is what the run was judged against, with the three places reality
departed from it noted inline.

Not a certification harness, and nothing here claims a guard, remounts a
filesystem, or writes an evidence file. It is the ordinary development runtime,
which already brings the shell up and logs every transition. Full operating
instructions are in `docs/DEVELOPMENT_RUNTIME.md`; this is only what V1.3's exit
criterion requires the run to show.

**Deploy.** Copy `fruitjam/` to the Fruit Jam's `CIRCUITPY` and `magtag/` to the
MagTag's, exactly as for V1.2 — no new files on the board beyond `shell.py` and
`shell_viewport.py`, which live in the existing `magwrite_transport` package.
Identify each board by UID before copying; the two `CIRCUITPY` drives are not
distinguishable by letter.

**Enable.** MagTag first, then Fruit Jam, per `docs/DEVELOPMENT_RUNTIME.md`.
`ENABLE_SHELL` is already `True` in the shipped `config.py`; nothing else
changes from the V1.2 session.

**Never write to a board's serial port while a one-shot harness is armed.** None
is armed here, but the rule stands: restart with the reset button.

What the run has to show, in order:

1. `dev_runtime_ready` carries `shell_state: MAIN_MENU` and
   `stop_from: MAIN_MENU`, and the panel draws the four menu items with `>` on
   Journal;

   *On the day it carried `shell_state: EDITOR`, because the card still held the
   V1.2 document and the opening state is derived from what recovery returned.
   That is this design working, not failing — the plan was written as though the
   card would be empty, which on a bench that has already run V1.2 it never is.
   The menu was reached with Escape then Enter instead, and requirement 9 was
   evidenced at boot for free.*
2. Down, Down, Enter opens Drafts — `shell_selection_moved` twice,
   `shell_mode_entered`, `shell_transition` to `EDITOR` — and the document title
   reads `DRAFTS L01 C00`;
3. typing behaves exactly as it did in V1.2: `live_event_processed` per
   keystroke, the panel trailing and catching up, the save indicator moving
   `u` → `r` → `s`;
4. Escape reaches the save screen, `shell_left_editor` and
   `document_checkpointed` are logged, and the panel names the state in words;

   *V1.5 removed the save screen. Escape now logs `shell_left_editor` with
   `save_action: CHECKPOINTED` and the panel draws the main menu next.*
5. Escape again returns to the same document with the cursor where it was, and
   the text is unchanged — this is the requirement-8 observation and the one to
   watch most closely;

   *V1.5: Enter re-opens it instead, and the observation is the same one — the
   text and the cursor are unchanged.*
6. Escape, Enter, Enter re-enters the editor from the menu with the document
   still intact. Repeat the whole cycle at least three times: the exit criterion
   is *repeatedly*, and a state machine that survives one round trip and not
   four is the failure worth finding;

   *V1.5: Escape, Enter.*
7. pull the USB cable mid-session, then restart: `document_recovery`,
   `live_document_restored`, and `shell_restored` with `state: EDITOR` — the
   board comes back into the document, not the menu;

   *Recovery came from `source: JOURNAL` rather than the tidy `CHECKPOINT` a
   clean stop leaves, which is the harder of the two and the reason this step is
   a cable pull rather than a reset. Restart the **MagTag** first afterwards: it
   is still holding parser state from the session that was cut off, and will
   refuse the next handshake. See `docs/DEVELOPMENT_RUNTIME.md`.*
8. Escape, Enter, Escape from the recovered document is the clean stop:
   `dev_runtime_session_summary` then `dev_runtime_stopped`.

   *V1.5: Escape, Escape.*

9. *The plan as first written had no step for the recoverable error state, which
   left the one requirement that cannot be argued from the host suite alone
   untested — the whole point of failing closed is what the hardware does when it
   happens. Added on the day: press Enter about thirty-three times. The document
   line bound is 32, the refused edit produces `live_event_rejected` then
   `shell_fault`, and the panel shows `MAGWRITE ERROR` with `WORK IS KEPT`. Enter
   returns to the menu with the document intact. It was reached four times and
   the session survived every one.*

Capture both consoles with `tools/capture_serial.py`, which is read-only, and
flush the captures before reading them — a buffered capture has faked a hardware
fault in this project once already.

Record the outcome in `ROADMAP.md` and `PRIORITY.md` whichever way it goes. A
failed physical run is evidence; a physical claim made from the host suite is
not.

## Physical bench check of the V1.5 revisions — run 2026-07-30, PASSED

The smallest check that settles the two things V1.5 changed. Six steps, all
passed, zero faults. Evidence: `docs/FRUITJAM_V15_BENCH_SERIAL.jsonl` and
`docs/MAGTAG_V15_BENCH_SERIAL.jsonl`; the full account is in `ROADMAP.md`.

1. **The one-gesture exit is real.** Escape from the editor produced one
   `document_checkpointed`, one `shell_left_editor` carrying
   `save_action: "CHECKPOINTED"` and `save_state: "SAVED"`, and one
   `shell_transition` `EDITOR` → `MAIN_MENU`. No screen appeared on the panel
   between the two, and no second keypress was asked for or given.
2. **The buttons are the primary controls.** Up, down, select, and back to the
   menu were each driven from the MagTag: `UP` and `DOWN` moved the selection one
   item per press, `SELECT` opened `RECENT` into the editor, and `MENU`
   checkpointed and returned — silently, on the same path Escape takes.
3. **Nothing arrived twice.** 9 presses, 9 frames sent with no bounce or repeat
   suppressed at the MagTag, and 9 received, accepted, and applied at the Fruit
   Jam with no duplicate, drop, or unknown action. All three suppression points
   were quiet because there was nothing for them to suppress.
4. **No button reached the document.** The three presses made inside the editor
   were applied `EDITOR` → `EDITOR`, counted as `shell_buttons_ignored: 3`, and
   generated no editor event at all; the character count never moved. Button A at
   the main menu did not end the session.
5. **No text was lost** across leaving the editor and reopening it, on a document
   recovered from a previous session rather than a fresh one.

## Diagnostics

`shell_transition`, `shell_mode_entered`, `shell_selection_moved`,
`shell_left_editor`, `shell_fault`, `shell_fault_repeated`, `shell_restored`.
The session summary carries `shell_state`, `shell_mode`, `shell_selection`,
`shell_entries`, `shell_backs`, `shell_faults`, `shell_ignored_events`,
`shell_error_reason`, `shell_routed_events`, and `finish_requests_serviced`.

V1.5 adds `shell_button_applied` on the Fruit Jam and `dev_display_button_pressed`
on the MagTag, so a press can be followed across the wire from the contact to the
transition it caused. `shell_left_editor` gained `save_action` and `save_state`,
which is how a silent checkpoint stays auditable now that it draws no screen. The
summary gains `shell_button_actions`, `shell_buttons_ignored`,
`shell_save_state`, `editor_exit_save_failures`, `button_frames_received`,
`button_actions_applied`, and the `ButtonInbox` counters —
`button_events_received`, `_accepted`, `_applied`, `_duplicate`, `_unknown`, and
`_dropped`.
