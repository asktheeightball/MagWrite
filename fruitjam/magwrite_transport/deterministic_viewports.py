"""Deterministic bounded physical viewport stream."""

from magwrite_transport.protocol import END_OF_SCENARIO, END_OF_TEST, HELLO, VIEWPORT, crc32

MAX_TOTAL_FRAMES = 50
MAX_VIEWPORT_FRAMES = 40
# Raised from three to five so a multiline editor fits a usable writing window.
# Worst case payload is 4 + 20 title + 1 + 20 status + 1 + 5 * (1 + 28) = 191
# bytes, still inside the fixed 192-byte protocol maximum. Three-line frames
# from the earlier proven runs remain valid.
MAX_VIEWPORT_LINES = 5


def encode_viewport(scenario, title, lines, row, column, status):
    fields = [title.encode("ascii"), status.encode("ascii")]
    if (
        len(fields[0]) > 20 or len(fields[1]) > 20
        or not (1 <= len(lines) <= MAX_VIEWPORT_LINES)
    ):
        raise ValueError("viewport bounds")
    out = bytearray((scenario, row, column, len(fields[0])))
    out.extend(fields[0])
    out.append(len(fields[1]))
    out.extend(fields[1])
    out.append(len(lines))
    for line in lines:
        data = line.encode("ascii")
        if len(data) > 28:
            raise ValueError("line bounds")
        out.append(len(data))
        out.extend(data)
    return bytes(out)


def deterministic_messages():
    messages = [(HELLO, 0, b"FRUITJAM-UART/1;296x128;MAX=192")]
    revision = 0
    last_viewport_hash = None
    scenarios = (
        (1, (("MAGWRITE UART", "FRUIT JAM ONLINE", "FRAME 01"),)),
        (2, (
            ("THE", "", ""), ("THE QUICK", "", ""), ("THE QUICK BROWN", "", ""),
            ("THE QUICK BROWN FOX", "JUMPS", ""),
            ("THE QUICK BROWN FOX", "JUMPS OVER THE", ""),
            ("THE QUICK BROWN FOX", "JUMPS OVER THE", "LAZY DOG"),
        )),
        (3, (("MAGWRITE RECEIVES", "COMPLETE VIEWPORTS", "NOT KEYSTROKES"),)),
        (4, (
            ("< BOX WITH FIVE DOZEN", "LIQUOR J", "FRAME 09 >"),
            ("< WITH FIVE DOZEN LIQUOR", "JUG", "FRAME 10 >"),
            ("< FIVE DOZEN LIQUOR JUGS", "CURSOR AT J", "FRAME 11 >"),
        )),
    )
    for scenario, views in scenarios:
        for lines in views:
            revision += 1
            column = lines[-2].find("J") if scenario == 4 else len(lines[-1])
            row = 1 if scenario == 4 else 2
            payload = encode_viewport(
                scenario, "UART VIEWPORT", lines, row, max(0, column), "REV %02d" % revision
            )
            last_viewport_hash = "%08X" % crc32(payload)
            messages.append((VIEWPORT, revision, payload))
        messages.append((END_OF_SCENARIO, revision,
                         bytes((scenario,)) + last_viewport_hash.encode("ascii")))
    viewport_count = sum(1 for kind, _, _ in messages if kind == VIEWPORT)
    messages.append((END_OF_TEST, revision,
                     ("%d;%d;%s" % (revision, viewport_count, last_viewport_hash)).encode("ascii")))
    return tuple(messages)
