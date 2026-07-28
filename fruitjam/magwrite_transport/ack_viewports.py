"""Bounded deterministic scenarios for the bidirectional acknowledgement gate."""

from magwrite_transport.deterministic_viewports import encode_viewport
from magwrite_transport.protocol import END_OF_TEST, HELLO, VIEWPORT, crc32

MAX_ACK_VIEWPORT_FRAMES = 6
MAX_ACK_TOTAL_INPUT_FRAMES = 8


def ack_test_messages():
    messages = [(HELLO, 0, b"FRUITJAM-ACK/1")]
    views = (
        (2, ("ACK LINK ONLINE", "STATUS HELLO OK", "SCENARIO 2"), 2, 10),
        (3, ("THE", "", ""), 0, 3),
        (3, ("THE QUICK", "", ""), 0, 9),
        (3, ("THE QUICK BROWN", "JUMPS", ""), 1, 5),
        (3, ("THE QUICK BROWN FOX", "JUMPS OVER", "LAZY DOG"), 2, 8),
        (4, ("< FIVE DOZEN LIQUOR JUGS", "CURSOR AT J", "ACK COMPLETE >"), 1, 10),
    )
    final_hash = 0
    for revision, (scenario, lines, row, column) in enumerate(views, 1):
        payload = encode_viewport(
            scenario, "UART ACK TEST", lines, row, column,
            "ACK REV %02d" % revision,
        )
        final_hash = crc32(payload)
        messages.append((VIEWPORT, revision, payload))
    messages.append((
        END_OF_TEST,
        len(views),
        ("%d;%d;%08X" % (len(views), len(views), final_hash)).encode("ascii"),
    ))
    return tuple(messages)
