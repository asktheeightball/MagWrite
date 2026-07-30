# MagWrite Modes — Journal, Quick Note, Drafts, and Recent

V1.4. The four writing modes, built on the shell and on persistence.

Status: **implemented, host-verified, and physically verified on 2026-07-30** by
a deliberately minimal bench run. Six of the nine exit criteria below were
observed on hardware; the three that were not are named explicitly at the end.

Two changes ship together here, and the order matters: the document bound was
raised first, because a mode that opens a document you cannot write a page into
is not worth building.

## Part one — the document bound

### What was wrong

| Bound | V1.3 | V1.4 |
| --- | --- | --- |
| `MAX_DOCUMENT_CHARS` | 512 | **8192** |
| `MAX_LINE_CHARS` | 96 | **1024** |
| `MAX_DOCUMENT_LINES` | 32 | **512** |

The V1.3 numbers were sized for a transport experiment and are wrong for a
writing tool. The binding one was not the document limit or the line count — it
was `MAX_LINE_CHARS`. **The editor word-wraps, so a paragraph is one logical
line**, and 96 characters is about a sentence and a half. The V1.3 bench session
hit `document line capacity reached` four times in ordinary prose. That is
recorded in `ROADMAP.md` as a bounded failure recovering correctly, which it was;
it is also a device refusing the fifth sentence of a paragraph.

### Why a character bound

Requirement 2 of this phase, and the right answer anyway. A character bound is
the one a writer can predict, and it is the one that actually governs cost:
every byte of the document is multiplied through the storage path, because a
journal record is a whole snapshot.

8192 characters is roughly 1,400 words — a journal entry, a scene, or a short
essay, whole.

`MAX_DOCUMENT_LINES` is now a structural safety bound rather than a writing one.
8192 characters of prose is nowhere near 512 paragraphs; the line count is
reachable only by holding Enter, and reaching it is refused as cleanly as any
other bound.

### Why not larger, and why no rewrite was needed

Requirement 5 says do not introduce file-backed editing unless the current design
truly cannot support a practical document size. It can, and the two costs are
both bounded:

- **journal records.** A record is the escaped document, so the worst case is
  `2 × MAX_DOCUMENT_CHARS` plus a header. `journal.MAX_RECORD_BYTES` is now
  *derived* from the editor's constant rather than written down beside it. The
  two drifting apart would mean a document the editor accepts and the journal
  refuses to encode — a document that saves until it doesn't;
- **layout.** `Layout.locate` runs per keystroke and is linear in the characters
  *before the cursor*. `Layout.rows` is linear in the whole document but runs
  only when a viewport is built, which pacing already holds to roughly one a
  second. What crosses the UART is unchanged: a five-row window is the same size
  whatever is behind it.

`document_store.RESERVE_BYTES` went from 32 KB to 128 KB to match, so "refuse
before exhaustion" does not degrade into "refuse during exhaustion" exactly when
the document is at its largest.

Another order of magnitude *would* need a different architecture. That is the
line, and it has not been crossed.

### Recorded, not chased

An 8 KB document journaled every twelve revisions writes appreciably more per
session than a 512-byte one did — a few megabytes over a long session, which is
nothing to a 946 MB card but is a real amount of SPI time per append. The
per-append cost has not been measured on hardware. It belongs to the physical
run, and it is in the deferred backlog.

## Part two — the four modes

### The one rule

Each mode is a *choice of document*, and that is all a mode is. Every one of them
resolves to the same two operations:

```text
index.record / index.touch      which document, and that it was opened now
store.select(document_id)       point the proven store at it and recover it
```

No mode owns a document format, a record format, a recovery rule, a renderer, a
transport, or a pacing policy. One editor, one storage format, one recovery
system, one shell, one renderer, one UART, one pacing path.

### What each one does

**Journal** — append-oriented. Opens the newest journal entry with the cursor at
the end of the writer's last words, so sitting down and typing continues the
entry rather than starting a page. When fewer than 512 characters remain, the
next numbered entry is started instead.

*Dating is deferred, and deliberately.* The prototype has no RTC and no network,
so the device cannot know today's date. The choice was between numbering entries
honestly and stamping them with a date derived from `time.monotonic`, which would
be a fabricated date printed next to a writer's own words. Entries are numbered.
When a time source exists, `library._journal_title` is the one function that
changes and the rollover rule becomes a date comparison. `PRODUCT.md` asks for
"dated journal entry creation" and this does not yet deliver it; that is stated
rather than papered over.

**Quick Note** — always a new, empty document, opened immediately. The only mode
that never asks a question, because the entire value of it is the interval
between deciding to write something down and being able to.

**Drafts** — the working set, most recently opened first, one document a row on a
five-row panel with the window following the selection. The only item that shows
a screen, because it is the only one whose answer the device cannot know.

**Recent** — the document with the highest open ordinal, which is the one that
was open last.

### Kinds are properties of documents, not of menus

A document's **kind** is `JOURNAL`, `NOTE`, or `DRAFT`. Drafts and Recent are
*ways of reaching* a document; a note opened through Drafts is still a note.

This is the answer to the one gap V1.3 recorded and handed forward: a restored
session did not restore its mode, because the mode was derived from whatever the
menu happened to be pointing at. It now arrives with the document, because the
kind is recorded in the catalogue alongside it. Nothing extra is persisted to
achieve that — the catalogue already had to exist for Drafts and Recent.

## The catalogue

```text
/sd/magwrite/index.log                  append-only catalogue
/sd/magwrite/documents/<id>.md          plain text, readable on any computer
/sd/magwrite/documents/<id>.prev.md     the previous plain-text mirror
/sd/magwrite/documents/<id>.new.md      a mirror being written
/sd/magwrite/recovery/<id>.log          append-only journal of snapshots
/sd/magwrite/recovery/<id>.ckpt.log     append-only checkpoint records
```

One record:

```text
MWX1 <seq> <opened> <kind> <id> <length> <crc8hex> <escaped-title>\n
```

The same discipline as the recovery journal, for the same reason: three
independent corruption defences — a missing newline, a short body, a failed CRC —
and file order is time order.

**`opened` is the whole of "last-opened ordering" and "which document is
active".** The highest `opened` in the catalogue *is* the active document. There
is deliberately no second file holding a pointer, and therefore no second file
that can disagree with this one after a power cut. An "active document" pointer
stored separately from the catalogue is the two-file atomicity problem in a new
hat, and this design already refused it once.

Later records win per id, so renaming a document, changing its kind, and
re-opening it are all one append rather than an edit. The log is compacted past
its bound, keeping the newest record per id, written aside and renamed exactly as
the checkpoint log is.

The catalogue is bounded at 64 documents. Past that, creating a new one is
refused cleanly, named, and recoverable — an unbounded catalogue on a
microcontroller is a bug that takes a few months to appear.

### What a truncated tail costs

One append. A new document's catalogue record is written **before** any of its
text is, so the record a power cut can lose is always the record for an *empty*
document. Losing the entry for a document that has words in it is not a state
this ordering can reach.

## Migration — the document a writer already has

A card written by V1.2 or V1.3 must come back with its words, its cursor, its
revision, and its journal, and this build must not move, rename, or rewrite any
of them.

`active` is a legal id, and it is the one the existing files already use. So
`documents/active.md` and `recovery/active.log` are *already correct* under the
per-document naming and are not touched. The one file that does not fit is
`recovery/checkpoint.log`, whose per-id name would be `active.ckpt.log`.

It is not renamed. **A rename is a write, and writing to somebody's only copy in
order to upgrade it is how upgrades lose documents.** It is read at its old name
whenever the new one does not yet exist. The first checkpoint this build takes
writes the new file, which then wins on every subsequent open because it holds
the newer record. The old file is never touched and never deleted.

Migration is therefore exactly **one catalogue append**, recording `active` as a
`DRAFT` titled `DRAFT`, and it makes that document the active one — so a writer
who upgrades mid-draft comes back to their draft.

## Switching documents, and the V1.3 invariant

V1.3's rule was: one `MultilineEditor` for the life of the session, never
constructed, cleared, or reloaded, so no transition can lose unsaved work —
nothing is closed.

V1.4 has more than one document, so something has to change contents. The rule is
kept and made precise rather than dropped:

- there is still exactly **one editor** for the life of the session;
- the **shell still never touches it**. The shell may not open a card, so it does
  not: it records a bounded request, and the session performs it;
- a switch is a **handover, not a close**, and it is ordered:

```text
1. checkpoint the outgoing document        durable before anything is rebound
2. library chooses, store selects          which document, and recover it
3. editor.open_document(...)               validated against the same bounds
4. shell.opened(id, kind, title)           only now is the shell told
```

Step 1 is unconditional. A threshold that has not been reached is not a reason to
hand a document over with work only in RAM. Every failure between 2 and 4 becomes
a recoverable error screen with the outgoing document already durable behind it.

The request is serviced in the same loop iteration the keystroke was routed in,
before any frame is built, so a mode never puts a stale document on the panel for
even one refresh.

### Revisions across a switch

`document_revision` is a **session-monotonic** counter. It does not restart at
the incoming document's stored revision, because the acknowledgement tracker and
the save state both assume it never goes backwards within a session.

Per-document recency still works: a document's stored revision is the highest
ever written to it, and continuing from a session counter can only make the next
record higher. "Higher wins" stays true inside every document's own log.

One visible consequence, and it errs in the only direction this indicator is
allowed to err in: for the moment after a switch the save state reads `UNSAVED`,
until the first autosave lands. What is on the card *is* durable, but it is
durable at the stored revision and this session's counter is already past it.
The system never reports that it is saving when it is not.

## Without a card

`library` is `None` on a degraded card, and that is a first-class state, on
exactly the terms `persistence` and `shell` already are. The shell's four items
then route into the one document precisely as they did in V1.3, the panel shows
`x`, and the writer is told rather than misled. Every viewport payload the V1.3
physical runs measured stays reproducible.

## How this is tested

`host-tests/test_document_bounds.py` — 42 tests. Documents far longer than 32
lines; scrolling at the beginning, the middle, and the end; editing at the very
edge of the bound; and clean refusal at the real limit, where every refusal is
asserted to leave the text, the cursor, both revisions, and the recovered
document exactly as they were. No test uses a literal bound — every size is
derived from the editor's own constants, so they keep testing the property the
next time the bounds move.

`host-tests/test_library.py` — 82 tests across four layers: the `MWX1` record
against every corruption a power cut produces; the catalogue driven directly,
including compaction and a truncated tail; the library against a real store on a
filesystem that can lose power at a chosen byte; and the whole thing through the
real session, editor, shell, renderer, and transport — two modes captured in one
session, a restart that brings back the document *and* its mode, and a forced
power loss that recovers both.

Migration is asserted file-by-file: after adopting a legacy card, every
pre-existing file must be byte-identical and the only new one must be
`index.log`.

## Exit criteria for physical verification

The V1.4 exit is a real writing session that starts in the shell, captures in two
different modes, and recovers correctly after a forced power loss. On the bench
that means:

| # | Criterion | 2026-07-30 |
| --- | --- | --- |
| 1 | the main menu renders and all four items open what they say they open | **partial** — menu rendered and navigated; only Quick Note and Drafts were opened |
| 2 | Quick Note produces a new empty document every time | **met** — `n0001` / `NOTE 1`, `kind: NOTE`, opened at 0 characters |
| 3 | Journal continues the previous entry with the cursor at the end of it | **not run** |
| 4 | Drafts lists what exists, scrolls, and opens the selected document | **partial** — listed and opened both documents; two entries do not fill a five-row panel, so scrolling was not exercised |
| 5 | Recent returns to the document that was open last | **not run** as a menu item, though the restart proved the same ordinal rule |
| 6 | leaving a document for another checkpoints the first one first | **met** — all four switches emitted `document_checkpointed` `manual: true` `SAVED` for the outgoing document before `shell_document_opened` |
| 7 | a paragraph of real prose is accepted where V1.3 refused it | **met** — 134 characters onto one logical line, `cursor_column: 133`, no refusal anywhere in the run |
| 8 | a forced power loss recovers the words, the document identity, and the mode | **not run** — scoped out; a clean restart did restore all three |
| 9 | the boards stay host-writable and no guard is claimed | **met** — `guard_written: false`, `filesystem_remounted: false`, `restartable: true` |

Evidence: `docs/FRUITJAM_V14_BENCH_SERIAL.jsonl`,
`docs/MAGTAG_V14_BENCH_SERIAL.jsonl`, and the pre-migration
`docs/V14_PREFLIGHT_DOCUMENT_BACKUP.md`. The full account is in `ROADMAP.md`.

**Criteria 3, 5, and 8 remain unverified on hardware.** They are not claimed and
should be picked up by the next run that has a reason to be on the bench.

### One correction to the account above

"plain text, readable on any computer" is not currently true *while a session is
live*. CircuitPython 10.2.1 exposes the microSD to the USB host as a third mass
storage LUN and auto-mounts it at `/sd`, so the host holds a cached view of a
volume the board is writing underneath it; every non-empty file then reads as
corrupt from the host while the board reads all of them cleanly. The text on the
card is fine and portable — the host's view of it, mid-session, is not.

See `docs/DEVELOPMENT_RUNTIME.md` for the bring-up order — **restart the MagTag
first** after any interrupted session. That rule bit a third time during this
run, from restarting the Fruit Jam by autoreload without restarting the MagTag.
