# MagWrite Architecture

## System overview

```text
USB HID keyboard
        |
        v
Adafruit Fruit Jam
        +-- authoritative multiline editor
        +-- cursor, wrapping, and viewport state
        +-- microSD document and recovery storage
        +-- keyboard input normalization
        +-- MagTag button-event interpretation
        |
        | bidirectional 3.3 V UART
        v
Original Adafruit MagTag
        +-- e-paper rendering and refresh scheduling
        +-- frame acceptance and display acknowledgements
        +-- four-button event capture
```

The Fruit Jam is the authoritative application controller. The MagTag is a display terminal and input surface, not a second editor.

Direct USB HID on the Fruit Jam is the preferred keyboard path. The LOLIN32 Bluetooth bridge is deferred and remains an optional adapter only for a Bluetooth-only keyboard that cannot use USB or a receiver.

The microSD card is a separate filesystem from CIRCUITPY, so mounting it needs
no `storage.remount`. The development runtime keeps its defining property: the
host retains the drive, autoreload stays on, and saving a file restarts the
board.

## Proven transport boundary

The Fruit Jam and MagTag communicate through a versioned, bounded, CRC-protected binary protocol over UART.

```text
Fruit Jam board.A0 TX  ---> MagTag board.D10 RX
Fruit Jam board.A1 RX  <--- MagTag board.A1 TX
Fruit Jam GND          <--> MagTag GND
```

The physical bidirectional gate passed on 2026-07-28 at 115200 baud. The system has physically verified:

- complete semantic viewport transmission;
- bounded parsing and reset-noise resynchronization;
- frame acceptance acknowledgement;
- physical refresh-start acknowledgement;
- physical refresh-completion acknowledgement;
- displayed-revision catch-up;
- final revision and viewport-hash reconciliation;
- stale viewport coalescing without falsely reporting skipped revisions as displayed.

## Current editor boundary

```text
USB HID or deterministic input source
        |
        v
device layout (per-keyboard usage compatibility, standard HID by default)
        |
        v
InputAdapter boundary (normalized InputEvent)
        |
        v
bounded event queue, explicit overflow
        |
        v
MagWrite shell (routing only: to the editor, or consumed by a screen)
        |
        v
Fruit Jam authoritative multiline editor
        +-- document text and line structure
        +-- cursor row/column and preferred visual column
        +-- document_revision
        |
        v
layout and viewport builder
        +-- wrapping and hard wrapping
        +-- vertical scrolling
        +-- viewport_revision
        |
        v
adaptive send pacing (when to transmit; never what)
        |
        v
bidirectional UART transport
        |
        v
MagTag display-only terminal
        +-- frame acceptance
        +-- refresh state
        +-- displayed revision
        +-- bounded errors
```

The MagTag performs no editing, wrapping, scrolling, persistence, or document interpretation. It validates bounded viewport payloads and renders them.

### Keyboard layout compatibility

`hid_keymap` implements HID Usage Page 0x07 as specified and does not bend for
any particular keyboard. Devices that do not follow the specification are
accommodated separately, in `keyboard_layout`, as a named and bounded usage
remap selected from the USB descriptor the backend already reports.

The rules are deliberately narrow:

- an unrecognised keyboard always gets `STANDARD`, which remaps nothing, so the
  default path is unchanged and fail-safe;
- a device only gets a remap if its vendor and product identifiers match a
  recorded entry, and every entry carries the measured evidence behind it;
- remapping applies at translation only. Held keys, press and release tracking,
  and repeat ownership all keep the raw usage the keyboard sent, so a remap can
  never desynchronise a release from its press;
- no layout may redefine a FINISH usage, Caps Lock, or an editing key;
- a misspelled layout name fails closed at construction, not mid-run.

Held Ctrl means the key is a **command and never contributes a character**. A
recognised combination becomes a control — Ctrl-S is manual save — and an
unrecognised one is counted as unsupported. Before this rule existed, Ctrl-S
inserted a literal `s`, so the reflex every writer has for "save" silently
corrupted the document at the moment they believed they were protecting it.

## Application shell

Added in V1.3; `docs/SHELL.md` carries the design and the reasoning.

One host-safe state machine above the editor, and the only owner of application
state. It holds no editor, no document, no store, no clock, and no transport: it
decides where the writer is and where input goes.

```text
MAIN_MENU --Enter/SELECT--> EDITOR --Esc/MENU--> MAIN_MENU
    |    |                                (checkpoints silently first)
    |   Enter (Drafts)
    |    v
    |  DRAFTS --Enter/SELECT--> EDITOR
    |    |
   Esc  Esc/MENU --> MAIN_MENU
    v
  EXIT                    any fault --> ERROR --Enter/SELECT--> MAIN_MENU
```

V1.5 removed the `SAVE_STATUS` screen that used to sit between the editor and the
menu. The checkpoint it existed to force is unchanged and still unconditional; it
now runs silently inside the gesture, *before* the transition, so a save that
actually failed reaches `ERROR` instead of the menu. A missing card is not a
failure — it is the reported degraded mode the indicator already shows.

The rules that keep it safe:

- **one editor for the life of the session.** The shell never constructs,
  clears, or reloads it, so no transition can lose unsaved work — nothing is
  closed. Leaving the editor additionally forces a checkpoint on the way out;
- **no new keys.** Up, Down, and Enter are already normalized editor events, and
  the finish gesture already existed. Under the shell it means *back*, and at the
  root it is still the clean stop. The four MagTag buttons added in V1.5 add no
  new meaning either: they map onto those same signals and reach the same
  per-state handlers, so there is one definition of each and it cannot drift;
- **the editor still owns both revisions.** A shell screen is visible state the
  editor does not own, so it advances `viewport_revision` through the same single
  door the save indicator uses;
- **one renderer and one pacing policy.** A shell screen is a semantic viewport
  like any other and goes out through the proven encoder, transport,
  acknowledgement, and pacing path. The MagTag cannot tell a menu from a document;
- **fail closed.** Every transition funnels through one door, and anything it
  cannot make sense of becomes a recoverable error screen. The shell does not
  raise.

### Modes

Added in V1.4; `docs/MODES.md` carries the design and the reasoning.

Each of the four menu items is a *choice of document*, and that is all a mode is.
Every one resolves to the same two operations — record the open in the catalogue,
and point the proven store at that document id. No mode owns a document format,
a record format, a recovery rule, a renderer, a transport, or a pacing policy.

The shell may not touch a card, so it does not: it records at most one bounded
request and the session performs it, in the same loop iteration, before any frame
is built. A document switch is a **handover, not a close** — the outgoing
document is checkpointed before anything is rebound, and there is still exactly
one `MultilineEditor` for the life of the session.

A document's **kind** — `JOURNAL`, `NOTE`, or `DRAFT` — is a property of the
document, not of the menu item it was reached through. That is what makes a
restored session restore its mode, which V1.3 could not do.

## Responsibility boundaries

### Fruit Jam application

The Fruit Jam owns:

- USB HID keyboard discovery and input normalization;
- normalized semantic input events;
- bounded input-event buffering;
- application shell state, mode, and input routing;
- authoritative document text and line structure;
- editor commands and cursor position;
- wrapping, scrolling, and viewport construction;
- document and viewport revisions;
- acknowledgement tracking and timeout policy;
- microSD autosave, checkpoints, and recovery;
- the document catalogue: identity, kind, title, and last-opened ordering;
- which document each mode opens, and making the outgoing one durable first;
- document metadata and application workflow;
- interpretation of MagTag button events;
- battery, keyboard, storage, and save-state indicators.

The Fruit Jam does not treat the physical display as authoritative.

### MagTag display terminal

The MagTag owns:

- viewport frame validation;
- latest-frame coalescing;
- framebuffer rendering;
- full and partial refresh scheduling;
- physical busy-state observation;
- displayed revision and display errors;
- local button scanning and debounce;
- normalized button-event transmission;
- the persistent button footer, which names the four bezel actions and carries
  no state the Fruit Jam owns.

The MagTag does not independently:

- edit document text;
- move the authoritative cursor;
- decide wrapping or scrolling;
- save or open documents;
- interpret button meaning;
- own application menus or workflow state.

### Optional future Bluetooth adapter

A LOLIN32 bridge may be added later only for Bluetooth-only keyboards.

If used, it owns:

- BLE or Bluetooth Classic keyboard discovery, pairing, and reconnect;
- HID report parsing;
- modifier and repeat state;
- normalized key-event delivery into the existing Fruit Jam `InputAdapter`.

It never owns the document, viewport, storage, or display state.

## MagTag button-event path

Implemented in V1.5. The four front buttons are the **primary** shell controls;
the keyboard keeps its shell keys as a fallback.

```text
MagTag physical button
        |
        v
stability debounce, per-action minimum interval, press ordinal
        |
        v
BUTTON_EVENT over the return UART, sharing the acknowledgement channel
        |
        v
Fruit Jam ButtonInbox: unknown code refused, ordinal duplicate refused,
                       bounded queue, oldest dropped
        |
        v
Shell.button, at loop stage 6
        |
        +-- MENU    back to the main menu (from the editor: checkpoint first)
        +-- UP      move the selection
        +-- DOWN    move the selection
        +-- SELECT  open the selected item; dismiss the error screen
        |
        v
new authoritative state and viewport
```

The MagTag transmits **normalized actions, never button identities and never
meanings**: `UP`, not `B`, and not "next journal entry". A raw identity would
force the Fruit Jam to know the panel's physical layout; a meaning would be the
display board deciding product behaviour. Every question of what an action does
is answered on the Fruit Jam, which owns shell and document state.

Press and release are the modelled events; deliberate long-press is not
implemented and is not needed by any current action. Button queue overflow,
duplicates, and unknown codes are explicit and counted on both boards. Display
acknowledgements and button events share the return transport without blocking
each other: they use one bounded outbox, and headroom is reserved in it for the
acknowledgements an in-flight refresh is about to need, so a press can never
stall the panel.

Two rules the button path does not share with the keyboard:

- **no button reaches the document.** In the editor everything except `MENU` is
  counted and discarded, including `UP` and `DOWN`. A control surface that can
  alter a draft is one that can alter it from inside a bag;
- **`MENU` at the main menu does nothing.** It is a *go to the menu* control, not
  a back control, so it cannot walk off the root and end the session. On the
  bench profile Escape still can; on the standalone appliance it does not either,
  because a device with one power cable has no stop to take.

## Runtime model

### Runtime profiles

There is one runtime per board, in one of two profiles, chosen from `config` at
start. The profiles are not two builds: the editor, shell, storage, transport,
buttons, viewport builder, protocol, and pacing are identical, and a profile
decides only the bounds that would end a *run*.

| | `DEVELOPMENT` | `STANDALONE` |
| --- | --- | --- |
| Selected by | `ENABLE_DEV_RUNTIME`, opt-in | the shipped default |
| Idle / session timeout | 1800 s / 7200 s | none |
| Keyboard event bound | 100,000 | none |
| Viewport / protocol frame bounds | 100,000 / 200,000 | none |
| Back gesture at the main menu | the clean stop | nothing |

The standalone profile removes no bound that protects **memory**. The input
queue, the acknowledgement tracker, the button inbox, the status outbox, the USB
poll budget, the input drain budget, the document bounds, and the catalogue bound
are unchanged and still enforced, because an unbounded counter on a
microcontroller is still a bug. What it removes is the four bounds that exist to
end a session and the one gesture that ends one, none of which has a meaning on a
device whose only stop is the power cable.

The development profile is checked first, so a board deliberately armed for the
bench is never quietly handed the appliance, and standalone is the fall-through,
which is what makes it the default. Every guarded harness is checked before
either and still wins.

### Startup states

A device with no console can only report on its panel, and for the first seconds
of a start the panel belongs to the board that has not spoken yet. So each board
reports what it alone can see:

| State | Where it is shown |
| --- | --- |
| the panel has started | MagTag, locally |
| nothing has arrived on the link | MagTag, locally, after a fixed patience |
| a fault the link cannot carry | MagTag, locally |
| no card | Fruit Jam, one status character, since V1.2 |
| no keyboard | Fruit Jam, one status character and one menu row |
| the stored document would not open | Fruit Jam, the recoverable error screen |

The MagTag's local screens are the only exception to *the MagTag renders only
what it is given*, and it is deliberately the narrowest one that answers the
requirement. They carry no document, no cursor, no revision, and no state the
Fruit Jam owns; they are numbered revision 0, which the protocol already reads as
"nothing has been displayed"; they are acknowledged to nobody; and they are never
drawn again once a viewport has arrived. The board remains display-only. It is
allowed to say that it is alive, and nothing else.

The display is constructed before the UART for the same reason: a construction
failure the panel could report is a failure nobody sees if the panel does not
exist yet.

### Fruit Jam cooperative loop

1. Drain all currently available keyboard or synthetic input events within a bounded budget.
2. Apply them to the authoritative editor.
3. Drain available MagTag UART status and button-event bytes.
4. Parse complete return frames within a bounded budget.
5. Apply valid button events and shell control gestures to Fruit Jam-owned
   workflow state, both only with an empty input queue, so leaving the editor can
   never outrun the writing it is leaving. Leaving the editor checkpoints first
   and routes on the result. Normalized keyboard events are routed at stage 2: to
   the authoritative editor, or consumed by the shell screen that owns the panel.
6. Update acknowledgement state.
7. Run autosave, checkpoint, and manual-save work when due — at most one storage
   operation per iteration while writing, and always before the viewport stages,
   so durability never waits on a display refresh. The single iteration on which
   a clean stop is detected adds one final checkpoint, which is the one moment a
   checkpoint is unambiguously worth its cost.
8. Build only the newest required semantic viewport.
9. Coalesce obsolete unsent viewport states.
10. Send at most one newest pending viewport according to the bounded policy.
11. Check timeouts and emit bounded diagnostics.
12. Yield cooperatively.

Before this loop begins there is one phase with different rules: the display
handshake. Until the MagTag answers, stages 8 to 11 are replaced by a retry — the
handshake is re-sent at a fixed interval, indefinitely, and every timeout and
integrity bound is held back. Both boards necessarily cold boot together under
one-cable power, because the MagTag is powered from a Fruit Jam host port that is
dead while the Fruit Jam is in reset, so a first handshake arriving before the
panel is listening is the ordinary case rather than a fault. Input is still
polled, the document is not touched, and the session and idle clocks start when
the panel answers.

Input polled during that phase is queued and not drained, because there is
nowhere to show it. The queue holds about 32 keystrokes, and a writer who fills
it — typing a sentence into a device that is still booting — has the **overflow**
dropped and counted rather than the session ended. Everything already queued is
applied the moment the panel answers.

### MagTag cooperative loop

1. Drain available Fruit Jam UART bytes.
2. Parse complete viewport frames within a bounded budget.
3. Coalesce pending viewports to the newest valid revision.
4. Poll display busy state.
5. Mark completed physical refreshes and emit acknowledgements.
6. Scan and debounce physical buttons.
7. Queue bounded button events.
8. Start at most one new display refresh.
9. Transmit bounded status and button frames without blocking receive or display polling.
10. Yield cooperatively.

## Display strategy

The experimental UC8151D driver provides one-bit differential no-flash refresh but not true rectangular windowing. The entire framebuffer is transmitted, while unchanged pixels receive no visible drive.

Initial policy:

- first frame: full refresh;
- active typing: coalesced partial refreshes;
- refresh when the display is idle and the visible revision is stale;
- no blinking cursor;
- periodic full refresh according to measured ghosting and wear;
- full refresh on document open and explicit user command;
- preserve OLD/NEW differential state by avoiding panel power-off during an active writing session.

The production full-refresh interval remains configurable and must be based on later wear testing.

### Panel typography and layout — V1.7

The UI draws with **CircuitPython's built-in `terminalio.FONT`** — Terminus, a
6×12 monospace cell — at **native scale 1**, and with nothing else. Editor text,
menus, titles, the startup and waiting screens, status, error text, and the
button footer all go through the one path in `magtag/magwrite/font.py`.

It replaced a 3×5 bitmap table maintained by hand in
`magtag/magwrite/test_pattern.py`. That table worked, and it cost something every
time: each new apostrophe, semicolon, and the whole lowercase alphabet was an act
of type design, a character with no entry raised `KeyError` on the first frame
carrying it, and the sanitizers on both boards existed largely to prevent that.
The built-in font ships with the firmware, covers printable ASCII and beyond, and
costs no flash and no maintenance. The old table is **kept, not deleted**: the
one-shot hardware harnesses that produced this project's physical evidence still
draw with it, and re-rendering a proven harness would change what those runs
measured.

Scale 1 is not a compromise. The built-in font's 6 px advance is exactly what the
old table drew at scale 2, so the apparent size is what the bench already read
comfortably — two pixels taller, with real letterforms. No larger integer scale
fits a usable number of rows on a 128 px panel, and non-integer scaling and
simulated bold are both refused: this is a 1-bit panel, and both produce mush.

**Nothing about the geometry is written down.** `viewport_renderer.geometry()`
asks the font for its own bounding box and derives the row pitch, the row count,
and the column count from it. With the 6×12 built-in font that is:

| Band | y | Height |
| --- | --- | --- |
| Title and right-aligned status | 2 | 12 |
| Header rule | 16 | 1 |
| Body rows 0–5, 14 px pitch | 19 | 6 × 12 |
| Cursor underline | row + 12 | 2 |
| Footer rule | 112 | 1 |
| Button footer | 115 | 12 |

giving **48 columns by 6 rows**, against 28 by 5 before. The cursor underline
lives in the 2 px leading between rows, so it costs no height and can never
overlap the row below. The last body row ends at y=102, ten pixels clear of the
footer rule.

That capacity is the one number the two boards must agree on, and they share no
import: the Fruit Jam wraps to `editor_layout.VIEWPORT_COLUMNS/ROWS`, the MagTag
derives it, and a host test asserts every copy against the derivation. Six rows
by 48 columns is what raised the protocol payload maximum from 192 to 384 bytes;
see `PROTOCOL.md`.

### The button footer — V1.7

A strip above the four bezel buttons, on every screen, naming what each one does:
`MENU`, ▲, ▼, `SELECT`, centred on the four quarter-centres of the panel's long
axis. The mapping is unchanged — A `MENU`, B `UP`, C `DOWN`, D `SELECT` — and so
is every button's behaviour; what changed is that the panel now says so.

It knows nothing. Four fixed labels for the four fixed normalized actions this
board already sends, drawn locally rather than transmitted as viewport lines: a
label the Fruit Jam had to send on every frame would be payload spent repeating
itself forever, and a chance for the two boards to disagree about the bezel. It
carries no state, so it is identical on every screen and a partial refresh never
has to redraw it — a host test asserts that identity pixel for pixel.

The arrows are filled triangles drawn from display primitives, not text. The
built-in font has no arrow glyph in the printable-ASCII range both boards
restrict themselves to, and `^` and `v` are a caret and a letter — readable as
arrows only by someone already told they are arrows.

### Adaptive send pacing

*When* the Fruit Jam transmits a viewport is decided in one place,
`fruitjam/magwrite_transport/pacing.py`. It is the single home for every display
timing constant, so no two code paths can disagree about a send interval. It
decides only *when*; coalescing to the newest state, revision numbering,
hashing, acknowledgement, and the fail-closed ceilings stay where they are.

Three gates apply to the newest pending viewport, in order:

1. **busy** — never transmit while the MagTag has an unfinished refresh. At
   most one viewport is in flight, so a refresh is never started while the panel
   is working, and what goes out next is the newest state at the moment the
   panel came free rather than something queued while it was busy;
2. **coalescing** — a pending change must have existed for a short window
   before it may be sent, so a single keypress can never earn its own frame;
3. **interval** — the floor depends on what the writer is doing. Onset sends as
   soon as coalescing allows; a writer who has paused gets a short floor of
   roughly one partial refresh; a writer still typing gets the longer sustained
   floor that fits the authorised refresh budget.

The values are derived from measured panel behaviour, recorded in the module
alongside the constants they justify.

## Storage model

Documents on the microSD card, on the Fruit Jam. Implemented in V1.2 for one
document and generalised to many in V1.4; `docs/PERSISTENCE.md` carries the
durability and recovery argument, `docs/MODES.md` the catalogue.

```text
/sd/magwrite/index.log                   append-only catalogue
/sd/magwrite/documents/<id>.md           plain text, readable on any computer
/sd/magwrite/documents/<id>.prev.md      the previous plain-text mirror
/sd/magwrite/documents/<id>.new.md       a mirror being written
/sd/magwrite/recovery/<id>.log           append-only journal of snapshots
/sd/magwrite/recovery/<id>.ckpt.log      append-only checkpoint records
```

**The recovery logs are authoritative.** `documents/<id>.md` is a plain-text
mirror kept for the writer and for any computer the card is later plugged into;
recovery never trusts it. Making the `.md` file authoritative would require
either a metadata header inside it, which stops it being a plain-text document,
or a sidecar, which reintroduces the two-file atomicity problem an append-only
log already solves.

The catalogue is the same append-only discipline applied to metadata: identity,
kind, title, and a monotonic open ordinal. The **highest ordinal is the active
document**, so there is no separate pointer file that could disagree with the
catalogue after a power cut.

`active` is a legal id and is the one V1.2 and V1.3 already wrote, so a card from
an earlier build is adopted by appending one catalogue record. Nothing the writer
owns is moved, renamed, or rewritten.

Journal records are **full document snapshots, not deltas**. The document is
bounded, so a snapshot has a fixed worst case in bytes; a delta journal would
need a replay engine that separately models what BACKSPACE and ENTER mean, and
two models of editor semantics that must agree forever is how a recovery format
ends up unable to reproduce the document it recorded. That argument gets stronger
as the document grows, not weaker — a longer history is more replay to be wrong
about.

### Document bounds

| Bound | Value | What it is for |
| --- | --- | --- |
| `MAX_DOCUMENT_CHARS` | 8192 | the practical limit, roughly 1,400 words |
| `MAX_LINE_CHARS` | 1024 | a long paragraph; the editor wraps, so a paragraph is one logical line |
| `MAX_DOCUMENT_LINES` | 512 | structural, not a writing bound |

Raised in V1.4 from 512/96/32, which were sized for a transport experiment. The
binding one was the *line* bound: the V1.3 bench session refused ordinary prose
four times because 96 characters is about a sentence and a half. `config.py`
mirrors these and `journal.MAX_RECORD_BYTES` is derived from the character bound,
so no two places can disagree about how large a document may be.

Storage rules, as implemented:

- apply edits in RAM immediately;
- append a full snapshot after a pause, a revision threshold, or a bounded age;
- promote the newest snapshot to a checkpoint, then discard the journal, then
  rewrite the mirror — in that order, so no window exists in which the newest
  acknowledged snapshot is in neither log;
- preserve the previous checkpoint through compaction;
- tolerate a truncated final recovery record, detected three independent ways;
- reserve free space and refuse writes before exhaustion;
- never let a storage failure stop the writer: it degrades to a reported state,
  never to a refusal or a crash.

### The acknowledged revision

**Acknowledged means accepted by the Fruit Jam editor — `document_revision` —
not displayed by the MagTag.**

A display acknowledgement says a refresh finished. It says nothing about whether
the words survive a power cut, it can lag by a full refresh, and it can be
blocked indefinitely by a display fault. If persistence waited for it, a stalled
panel would silently stop saving. So the two are deliberately decoupled:

- display acknowledgements govern **pacing** — when a frame may be sent;
- editor acceptance governs **durability** — when a snapshot must be written.

### Save state

One save state, computed as a pure function of acknowledged, journaled, and
checkpointed revisions, drawn as one character in the viewport status line:

| State | Indicator | Meaning |
| --- | --- | --- |
| `SAVED` | `s` | everything accepted is in a checkpoint |
| `RECOVERABLE` | `r` | in the journal, so a power loss recovers it |
| `UNSAVED` | `u` | the newest edits are in RAM only |
| `ERROR` | `!` | a write was refused or failed |
| `NO_CARD` | `x` | no card, so nothing is being persisted |

`RECOVERABLE` is a real distinction rather than a shade of `SAVED`: it is where a
writer spends nearly all their time, and it is what the journal exists to
provide. `NO_CARD` is always shown — a writing tool that silently stops
persisting is worse than one that refuses to start.

Every indicator character is drawn by the MagTag's font, and a host test asserts
it. The indicator is drawn on the panel, so "a character" means "a character this
panel can draw". That alphabet is printable ASCII from V1.7, when the UI moved to
`terminalio.FONT`; it was a hand-maintained 3×5 table before, which is why the
first attempt at these indicators used `=` and `*` and raised `KeyError` on the
first frame that carried one.

### Keyboard state

One further status character, on identical terms: `k` when no keyboard is
claimed, nothing when one is. Both indicators together fit the fixed twenty-byte
status field exactly, which is why each is one character and why neither is drawn
when it has nothing to report.

The main menu additionally spells it out on a spare row below the four menu
items — which are never displaced — because a writer who has just connected one cable and
cannot type needs to know whether the device is broken or merely waiting.

An absent keyboard is a **degraded mode**, never a stop. The device keeps looking
at a bounded rate for as long as it has power, so a keyboard connected afterwards
is picked up with no reset, and something attached that cannot be driven as a
boot keyboard is reported and retried rather than fatal.

### Startup must never cost the writer their work

The storage layer already refuses to write past a reserve and already survives a
power cut at any byte. One further rule belongs to startup specifically: **a
document that cannot be loaded must not be overwritten in the attempt to recover
from it.**

An editor that refuses a stored document leaves itself empty at revision 0 while
the store still holds the real one, and the ordinary autosave policy would
promote that empty editor at the next threshold. So a refused restore *holds*
every write for the session. Nothing on the card is read again, written, renamed,
or removed; the writer lands on the recoverable error screen with the reason; and
the hold is released only when a document has actually been opened.

## Power model

Bench development may continue with separate USB power where required for safe diagnostics. The finished prototype must use one protected battery, one power-path charger, one charging input, and a measured regulated distribution path for Fruit Jam, MagTag, storage, and any USB receiver.

Do not connect two independent charger circuits to one shared battery.

## Portability

The editor, input normalization, protocol, buttons, and storage layers must remain host-testable and must not import display hardware modules. The display adapter must remain replaceable so the writing engine can later run on another partial-refresh panel or controller.