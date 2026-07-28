# MagWrite Keyboard Transport Protocol

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