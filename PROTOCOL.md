# MagWrite Keyboard Transport Protocol

## Wired viewport feasibility protocol (implemented, physical status PASS)

This separate version-1 protocol proves a one-way Fruit Jam-to-MagTag display
boundary. It carries complete semantic viewports, not key events, and does not
replace the later acknowledged keyboard protocol described below.

All integers are unsigned, big-endian:

```text
Offset  Size  Field
0       2     Magic 0x4D57 ("MW")
2       1     Version (1)
3       1     Type (see message types below)
4       4     Sequence
8       4     Document/view revision
12      2     Payload length (0..384)
14      N     Payload
14+N    4     IEEE CRC-32 of bytes 0 through 13+N
```

CRC-32 uses polynomial `0xEDB88320`, initial value `0xFFFFFFFF`, reflected
input/output processing, and final XOR `0xFFFFFFFF`. The `123456789` check
vector is `0xCBF43926`. Maximum frame size is 402 bytes. The incremental
parser accumulator is capped at 1024 bytes, safely holding a maximum 402-byte
frame remainder plus one 512-byte hardware read. It searches for the `MW` prefix after
noise or rejection and explicitly counts invalid version, type, length, CRC,
and buffer-overflow events.

### VIEWPORT payload

Only ASCII is supported by this feasibility run.

```text
Size  Field
1     scenario id (1..255)
1     cursor row
1     cursor column
1     title length (0..20)
N     title
1     status length (0..20)
N     status
1     visible line count (1..6)
repeat line count:
  1   line length (0..48)
  N   line
```

The visible line ceiling was three for the one-way and acknowledgement runs,
five for the multiline editor, and six from V1.7 — when the MagTag UI moved to
CircuitPython's built-in `terminalio.FONT` and the panel's real capacity became
**48 columns by 6 rows**. Worst case payload is
`4 + 20 + 1 + 20 + 1 + 6 * (1 + 48) = 340` bytes, which is what raised the
payload maximum from 192 to 384 and the parser accumulator from 512 to 1024.
The frame format, CRC, and framing rules are untouched, and widening a bound
accepts every frame the narrower one did — so three-line and five-line frames
from every earlier proven run remain valid.

The panel geometry is **derived, not declared**: `viewport_renderer.capacity()`
computes it from the bounding box the font itself reports. The line and row
ceilings above are what that derivation currently produces with the 6×12
built-in font, mirrored into the Fruit Jam's `editor_layout` constants because
the two boards share no import. A host test asserts every copy against the
derivation.

The cursor column may equal the selected line length (the insertion cell after
the final character). Oversized or malformed payloads are rejected; they are
never silently truncated. The Fruit Jam pre-windows long text and the MagTag
does not edit, scroll, persist, or reinterpret it.

`HELLO` is bounded ASCII application/test metadata.

**`HELLO` is the one frame that may restart the input sequence numbering, and
only before the MagTag has displayed anything** — nothing accepted, pending, in
flight, or about to start. A handshake is the beginning of a count rather than a
continuation of one. Once a viewport has been accepted, sequence discipline is
absolute again: a repeated or reversed number is a fault and a gap is a fault.

This exists because one-cable bench power made a start order impossible. The
MagTag is powered from a Fruit Jam USB-A host port, which carries no 5 V while
the Fruit Jam is in reset, so both boards cold boot together and the Fruit Jam
retries its handshake while the panel initialises. The Fruit Jam never restarts
its own numbering between those attempts — each takes the next number — so this
rule covers the *other* direction of the same window: either board restarting
before a session has begun. It is not a licence to renumber a live session.
`END_OF_SCENARIO` is the one-byte scenario id followed by the eight-hex-digit
CRC-32 of that scenario's final VIEWPORT payload.
`END_OF_TEST` is ASCII `final_revision;viewport_count;final_viewport_crc32`.

The deterministic run contains 17 frames: one HELLO, eleven VIEWPORTs, four
END_OF_SCENARIO frames, and one END_OF_TEST. Sequence numbers are 1..17 and
VIEWPORT revisions are 1..11.

### Bidirectional status extension (implemented, host verified; physical NOT RUN)

The return path uses the same version-1 frame and CRC:

```text
1 HELLO; 2 VIEWPORT; 3 END_OF_SCENARIO; 4 END_OF_TEST
5 STATUS_HELLO; 6 FRAME_ACCEPTED; 7 REFRESH_STARTED
8 REFRESH_COMPLETED; 9 DISPLAY_CAUGHT_UP; 10 FRAME_REJECTED
11 DISPLAY_ERROR; 12 TEST_COMPLETE; 13 BUTTON_EVENT
```

The header revision identifies the affected viewport. Status payloads are
bounded and big-endian:

```text
STATUS_HELLO       u8 protocol, u8 app, u32 displayed, u8 ready flags,
                   u8 test-id length, ASCII test-id (maximum 24)
FRAME_ACCEPTED     u32 received sequence, u32 pending revision, u8 superseded
REFRESH_STARTED    u32 viewport sequence, u8 mode (0 partial, 1 full),
                   u32 latest received, u32 previous displayed
REFRESH_COMPLETED  u32 viewport sequence, u32 duration ms,
                   u32 latest received, u8 stale
DISPLAY_CAUGHT_UP  u32 displayed, u32 latest received, u32 viewport CRC32
FRAME_REJECTED     u32 received sequence, u32 received revision, u8 code,
                   u32 displayed, bounded ASCII reason (maximum 32)
DISPLAY_ERROR      u8 code, u32 in-flight, u32 latest, u32 displayed,
                   bounded ASCII reason (maximum 32)
TEST_COMPLETE      u32 displayed, u32 viewport CRC32, five u16 counts:
                   accepted, rendered, superseded, refresh, error
BUTTON_EVENT       u8 action code, u32 press ordinal, u32 pressed ms
```

`FRAME_ACCEPTED` never means displayed. `REFRESH_COMPLETED` is emitted only
after panel busy is idle. `DISPLAY_CAUGHT_UP` requires no in-flight refresh,
no pending viewport, and displayed revision equal to latest accepted revision.
Status queues and acknowledgement histories are bounded; overflow is fatal and
the physical harness never retries automatically.

The one exception, and it is confined to the handshake: while `STATUS_HELLO` is
still outstanding the Fruit Jam retries rather than failing, re-baselining the
return channel's sequence numbering and rebuilding its parser on each attempt, so
a MagTag that boots late and numbers its first reply 1 is heard rather than
counted stale. Nothing has been transmitted or displayed at that point. Once the
session is live, every bound above is fatal exactly as before.

### BUTTON_EVENT (implemented, host verified; PHYSICALLY VERIFIED 2026-07-30)

Added in V1.5, and deliberately not given a channel of its own. It is the same
version-1 frame, the same CRC-32, and the same MagTag-to-Fruit Jam sequence
numbering as every acknowledgement above, which is what gives it gap detection
and duplicate rejection without inventing either.

Action codes are fixed: `1 MENU`, `2 UP`, `3 DOWN`, `4 SELECT`. They are
**normalized actions, not button identities** — the MagTag never reports which
physical switch closed, and never reports what the action should do. The header
revision carries the MagTag's currently displayed revision and is informational.

`ordinal` is the MagTag's own monotonic count of accepted presses, starting at
one, and is separate from the frame sequence because the frame sequence counts
every status frame. The Fruit Jam refuses any ordinal at or below the highest one
it has accepted, so a frame redelivered after a resynchronisation cannot move a
selection twice.

Rules:

- the MagTag debounces locally by **stability**, not by a press lockout: a
  reading must hold for the debounce interval before it is believed, on both
  edges, so release chatter cannot read as a second press;
- one press produces exactly one event; a held button never repeats;
- the same action is refused twice inside a minimum interval close to one panel
  refresh;
- button frames share the bounded status outbox with acknowledgements, with
  headroom reserved for the acknowledgements an in-flight refresh is about to
  need. A press that would eat into that headroom is dropped and counted;
- the Fruit Jam's inbox is bounded and drops the **oldest** on overflow, because
  a backlog is stale intention;
- an unrecognised action code is refused and counted, never guessed.

Verified on hardware 2026-07-30: 9 presses produced 9 frames and 9 applied
actions, with no bounce rejected, no repeat suppressed, no frame dropped, no
duplicate ordinal, and no unknown action code — while the acknowledgement stream
sharing the outbox reconciled all 16 viewports without a CRC failure. See
`ROADMAP.md`, V1.5.

The acknowledgement run is eight input frames: HELLO, six VIEWPORTs
(revisions 1..6), and END_OF_TEST. Revisions 2..5 form the supersession burst.
Ceilings are 50 viewports, 100 frames per direction, one initial full refresh,
and 30 partial refreshes.

### Multiline editor integration (implemented, host verified; physical NOT RUN)

The integrated editor run reuses this protocol unchanged apart from the
five-line viewport ceiling above. The Fruit Jam sends HELLO, one VIEWPORT per
transmitted editor state, and one END_OF_TEST; the MagTag returns the same
status set. Because the editor keeps typing while the panel is busy, the Fruit
Jam may transmit a newer revision before an older catch-up arrives. The
acknowledgement tracker therefore accepts an intermediate `DISPLAY_CAUGHT_UP`
only under an explicit opt-in, and still refuses any catch-up above the latest
transmitted revision, any catch-up before refresh completion, and any hash
mismatch. Ceilings are 75 viewports, 150 frames per direction, one initial full
refresh, and 40 partial refreshes.

## Status

Draft protocol for the LOLIN32 Lite keyboard bridge and MagTag application. Field sizes may change during implementation, but versioning and reliability requirements are mandatory.

## Transport

Version 1 uses a persistent TCP connection over a private local Wi-Fi network.

TCP provides ordered byte delivery, but the application protocol still uses sequence numbers and acknowledgements so reconnect replay and duplicate suppression are deterministic.

## Frame format

All integers are unsigned and big-endian.

```text
Offset  Size  Field
0       2     Magic: 0x4D57 ("MW")
2       1     Protocol version
3       1     Message type
4       2     Payload length
6       4     Sequence number
10      N     Payload
10+N    2     CRC-16 over header and payload
```

Maximum payload length must be bounded and documented in code.

## Message types

### Bridge to MagTag

- `HELLO`: bridge firmware version, capabilities, keyboard state
- `KEY_EVENT`: normalized key event
- `STATUS`: connection, pairing, queue depth, overflow count
- `HEARTBEAT`: liveness and last acknowledged sequence

### MagTag to bridge

- `HELLO_ACK`: accepted protocol version and MagTag capabilities
- `ACK`: highest contiguous accepted event sequence
- `COMMAND`: pair, forget bond, clear queue, request status
- `HEARTBEAT_ACK`: liveness response

## Normalized key event

```text
Field             Size
HID usage code    2
Unicode codepoint 4
Modifier mask     1
Event flags       1
Reserved          2
```

Modifier bits:

- bit 0: Shift
- bit 1: Control
- bit 2: Alt
- bit 3: GUI/Command
- bit 4: Caps Lock active

Event flags:

- bit 0: key down
- bit 1: key up
- bit 2: repeat
- bit 3: semantic/non-character key

Non-character keys retain their HID usage code and use Unicode codepoint zero.

## Reliability rules

- The bridge assigns one sequence number to each deliverable key event.
- The MagTag applies each sequence once.
- Duplicate events are acknowledged but not re-applied.
- Sequence gaps cause the MagTag to request replay or reconnect.
- The bridge retains unacknowledged events in a bounded queue.
- Queue overflow is never silent and must be displayed on the MagTag.
- On reconnect, both sides exchange the last accepted/acknowledged sequence.
- The protocol must tolerate sequence-number rollover.

## Security and networking

Version 1 is intended for an offline private network. Credentials must not be committed to source control. Configuration should be stored in a local ignored file or device settings.

Encryption and authenticated pairing between bridge and MagTag are deferred until the feasibility harness is stable, but the protocol design should leave room for a session nonce and message authentication.
