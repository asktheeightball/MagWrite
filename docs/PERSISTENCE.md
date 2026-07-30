# MagWrite Persistence and Recovery

V1.2. One document, on the microSD card, that survives forced power loss.

Status: **host-verified. Not yet physically confirmed.** See
[Physical confirmation still owed](#physical-confirmation-still-owed).

## What acknowledged means

The acknowledged revision is `editor.document_revision` — the latest revision the
**Fruit Jam editor** accepted. It is not the MagTag's displayed revision.

This is the decision the rest of the design rests on. A display acknowledgement
tells you a refresh finished; it says nothing about whether the words survive a
power cut, it can lag by a full refresh, and a display fault can block it
indefinitely. Persistence that waited on it would silently stop saving whenever
the panel stalled — the exact failure this phase exists to make impossible.

```text
editor accepts an edit  ---> durability   (journal, checkpoint, save state)
MagTag finishes refresh ---> pacing       (when the next frame may be sent)
```

The two never meet. Persistence is testable with no transport in the picture,
and a dead panel costs visibility, never words.

## Layout

```text
/sd/magwrite/documents/active.md         plain text, readable on any computer
/sd/magwrite/documents/active.prev.md    the previous plain-text mirror
/sd/magwrite/documents/active.new.md     a mirror being written
/sd/magwrite/recovery/active.log         append-only journal of snapshots
/sd/magwrite/recovery/checkpoint.log     append-only checkpoint records
```

**The recovery logs are authoritative.** `active.md` is a mirror, maintained so
the writer's work is a real file on a real card that opens in any editor. It is
never what recovery trusts.

That split is what keeps the design small. Making the `.md` file authoritative
needs either a metadata header inside it — which stops it being a plain-text
document — or a sidecar, which reintroduces the two-file atomicity problem the
append-only log already solves. The document is bounded at 512 characters, so
mirroring it costs a few hundred bytes and buys a recovery path containing
exactly one kind of write: an append that either lands whole or is rejected by
its own CRC.

## Snapshots, not deltas

A journal record is the **whole document**, plus the cursor and the revision.

A delta journal would record editor operations and replay them, which means a
second implementation of what BACKSPACE, ENTER, and a refused edit mean. Two
models of editor semantics that must agree forever is the standard way a recovery
format ends up unable to reproduce the document it recorded. With snapshots,
recovery is "keep the last record that validates" — no replay engine, and no
agreement with the editor beyond the text itself.

The cursor travels with the text, so recovery restores a *session*, not just a
file.

## Record format

```text
MWJ1 <seq> <revision> <row> <column> <length> <crc8hex> <escaped-text>\n
```

`length` is the byte length of the escaped text and `crc8hex` is its CRC-32. A
record cut short by power loss therefore fails three independent ways:

1. the line has no terminating newline;
2. the escaped text is shorter than `length`;
3. the CRC does not match.

The first is what a truncated final record actually looks like on FAT, and it is
checked before parsing, so a half-written line is never even split into fields.

Escaping is total and reversible: the editor admits printable ASCII 32–126 plus
the line breaks it inserts, so only backslash and newline need escaping. The
inverse is scanned left to right rather than done with two `replace` calls,
because the naive inverse turns the escaped form of a literal `\n` into a real
line break.

"Newest" means the last record in **file order** that validates, not the highest
sequence number. The journal is append-only, so file order is time order, and
trusting a sequence field over the file's own structure would let one corrupt
header resurrect a stale document.

## The checkpoint sequence, and every way it can be interrupted

1. append the newest snapshot to `checkpoint.log` and sync;
2. truncate `active.log`;
3. rewrite the mirror: write `active.new.md`, rotate `active.md` to
   `active.prev.md`, rename `active.new.md` to `active.md`.

| Power lost | What survives | Cost |
| --- | --- | --- |
| during (1) | the journal, intact; the partial checkpoint record is rejected | nothing |
| between (1) and (2) | the same snapshot in both logs, resolved by revision | nothing |
| during (2) | same as above | nothing |
| during (3) | both logs; the mirror is stale or split across three names | one rewrite |

**There is deliberately no window in which the newest acknowledged snapshot
exists in neither log.** That is the whole safety argument, and it is why the
ordering above is not rearranged for convenience: the checkpoint record becomes
durable *before* the journal that also holds that state is discarded.

FAT `rename` cannot overwrite, so each mirror step clears its target first. Every
step is individually survivable precisely because the mirror is not authoritative.

## Policy: when, as opposed to how

`document_store` knows how to write durably. `persistence` knows when. They fail
differently and are tested differently — the store against simulated power loss,
the policy against a clock.

Two tiers, because they cost different amounts.

**Journalling** is one bounded append, so it happens often:

| Trigger | Value | Why |
| --- | --- | --- |
| a pause | 1.0 s | stopping is when unsaved work is most exposed |
| revisions | 12 | roughly ten characters at a normal speed |
| age | 2.0 s | the exposure a writer who never pauses is asked to accept |

Five seconds was the first age bound and it is too generous: half a sentence is a
real amount of work to lose, and the write that would have prevented it is a
single append.

**Checkpointing** promotes the snapshot, discards the journal, and rewrites the
mirror, so it prefers a gap:

| Trigger | Value | Why |
| --- | --- | --- |
| records + a pause | 24, 3.0 s | worth compacting, taken when the writer stops |
| records, regardless | 48 | an unbroken burst must not grow the journal forever |
| age | 120 s | a quiet writer still gets a fresh mirror |
| manual save | Ctrl-S | whatever every threshold says |
| clean stop | — | the one moment a checkpoint is unambiguously worth its cost |

At most one storage operation runs per loop iteration while writing. The single
iteration on which a clean stop is detected adds the final checkpoint on top of
whatever stage 7 already did, which is deliberate: the queue is empty by then, so
it captures the complete final document rather than a state part-way through it.

`persistence.py` is the single home for every persistence timing constant, as
`pacing.py` is for display timing and `keyboard_repeat.py` is for keyboard
timing. `config.py` may only mirror it, and a host test asserts they agree.

## Manual save

Ctrl-S. Chosen over a dedicated key because it is the gesture a writer already
has in their fingers, and unlike Escape or a function key it is reachable on a
40% keyboard without an Fn layer that drops the device off USB.

Adding it also closed a real defect. Held Ctrl previously did nothing to
translation, so **Ctrl-S inserted a literal `s` into the authoritative
document** — the reflex every writer has for "save" silently corrupted the thing
being saved. Held Ctrl now means the key is a command: recognised combinations
become controls, unrecognised ones are counted as unsupported, and neither
produces a character.

Repeated presses collapse into one checkpoint of the newest state. Three Ctrl-S
presses mean "save now", not "save three times".

## Degraded modes

A card that is missing, unformatted, or unreadable is a **reported state, never a
refusal and never a crash**. The editor runs, the writer keeps typing, and the
panel shows `x`.

| Status | Meaning |
| --- | --- |
| `MOUNTED` | a FAT filesystem is mounted and writable |
| `NO_CARD` | no card responded; the slot is empty or the card is dead |
| `UNMOUNTABLE` | a card responded but carries no usable FAT filesystem |
| `NOT_CONFIGURED` | the board does not expose the configured pin aliases |
| `NOT_ENABLED` | persistence is switched off in config |
| `FAILED` | something else, reported verbatim |

`NO_CARD` and `UNMOUNTABLE` are kept apart deliberately: one means check whether
the card is seated, the other means format it.

The one outcome that is not allowed is a silent one. **The system must never
report that it is saving when it is not.**

## How this is tested

`FakeFileSystem` cuts power at a chosen byte offset of a chosen write. It raises
`PowerCut`, which is deliberately *not* an `OSError`: a store that "handled" a
power cut would be modelling something that cannot happen. The volume is then
re-opened exactly as the board would re-open it after reset.

Coverage includes each checkpoint window individually, a sweep that cuts power at
**every byte offset** of a journal append and asserts the recovered document is
always either the newest snapshot or the last durable one, and a full live
session killed mid-word and resumed from the card through the real editor,
viewport, and transport code.

Every hardware module is injected, so mount detection — empty slot, unformatted
card, wrong pin alias, missing SD driver — is exercised on CPython.

## Physical confirmation still owed

Two things are host-verified and not yet proved on hardware.

**The microSD pin aliases.** `config.SD_CS_PIN_ALIAS` defaults to `"SD_CS"` with
the board's shared `SPI()` bus, which is the normal Fruit Jam wiring, but no
alias in this repository has been read off the board in hand. This follows the
same rule as the UART pins: an unconfirmed alias is a guess. A wrong guess is not
a crash — bring-up reports `NOT_CONFIGURED` together with the `SD`-prefixed names
the board actually exposes, which is one readable diagnostic line rather than a
debugging session.

**The V1.2 exit condition itself.** "A writing session survives forced power loss
with the final acknowledged edit recovered" is a claim about hardware. The host
suite proves the logic; only pulling power from the real board proves the claim.
