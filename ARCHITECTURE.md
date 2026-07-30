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
MAIN_MENU --Enter--> EDITOR --Esc--> SAVE_STATUS --Enter--> MAIN_MENU
    |    |                                |
    |   Enter (Drafts)                   Esc --> EDITOR
    |    v
    |  DRAFTS --Enter--> EDITOR
    |    |
   Esc  Esc --> MAIN_MENU
    v
  EXIT                    any fault --> ERROR --Enter--> MAIN_MENU
```

The rules that keep it safe:

- **one editor for the life of the session.** The shell never constructs,
  clears, or reloads it, so no transition can lose unsaved work — nothing is
  closed. Leaving the editor additionally forces a checkpoint on the way out;
- **no new keys.** Up, Down, and Enter are already normalized editor events, and
  the finish gesture already existed. Under the shell it means *back*, and at the
  root it is still the clean stop;
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
- normalized button-event transmission.

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

```text
MagTag physical button
        |
        v
local debounce and event sequencing
        |
        v
BUTTON_EVENT over return UART
        |
        v
Fruit Jam application mapping
        |
        +-- menu/document action
        +-- page or scroll navigation
        +-- save/status
        +-- confirm/dismiss
        |
        v
new authoritative state and viewport
```

The protocol should support bounded press, release, and deliberate long-press events. Button queue overflow, duplicates, and stale events must be explicit. Display acknowledgements and button events share the return transport without blocking each other.

## Runtime model

### Fruit Jam cooperative loop

1. Drain all currently available keyboard or synthetic input events within a bounded budget.
2. Apply them to the authoritative editor.
3. Drain available MagTag UART status and button-event bytes.
4. Parse complete return frames within a bounded budget.
5. Apply valid button events and shell control gestures to Fruit Jam-owned
   workflow state. Normalized keyboard events are routed at stage 2: to the
   authoritative editor, or consumed by the shell screen that owns the panel.
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

Every indicator character is present in the MagTag's proven 3×5 glyph table, and
a host test asserts it. The indicator is drawn on the panel, so "a character"
means "a character this panel can draw".

## Power model

Bench development may continue with separate USB power where required for safe diagnostics. The finished prototype must use one protected battery, one power-path charger, one charging input, and a measured regulated distribution path for Fruit Jam, MagTag, storage, and any USB receiver.

Do not connect two independent charger circuits to one shared battery.

## Portability

The editor, input normalization, protocol, buttons, and storage layers must remain host-testable and must not import display hardware modules. The display adapter must remain replaceable so the writing engine can later run on another partial-refresh panel or controller.