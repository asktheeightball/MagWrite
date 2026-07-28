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
3       1     Type (1 HELLO, 2 VIEWPORT, 3 END_OF_SCENARIO, 4 END_OF_TEST)
4       4     Sequence
8       4     Document/view revision
12      2     Payload length (0..192)
14      N     Payload
14+N    4     IEEE CRC-32 of bytes 0 through 13+N
```

CRC-32 uses polynomial `0xEDB88320`, initial value `0xFFFFFFFF`, reflected
input/output processing, and final XOR `0xFFFFFFFF`. The `123456789` check
vector is `0xCBF43926`. Maximum frame size is 210 bytes. The incremental
parser accumulator is capped at 512 bytes, safely holding a maximum 210-byte
frame remainder plus one 256-byte hardware read. It searches for the `MW` prefix after
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
1     visible line count (1..3)
repeat line count:
  1   line length (0..28)
  N   line
```

The cursor column may equal the selected line length (the insertion cell after
the final character). Oversized or malformed payloads are rejected; they are
never silently truncated. The Fruit Jam pre-windows long text and the MagTag
does not edit, scroll, persist, or reinterpret it.

`HELLO` is bounded ASCII application/test metadata.
`END_OF_SCENARIO` is the one-byte scenario id followed by the eight-hex-digit
CRC-32 of that scenario's final VIEWPORT payload.
`END_OF_TEST` is ASCII `final_revision;viewport_count;final_viewport_crc32`.

The deterministic run contains 17 frames: one HELLO, eleven VIEWPORTs, four
END_OF_SCENARIO frames, and one END_OF_TEST. Sequence numbers are 1..17 and
VIEWPORT revisions are 1..11.

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
