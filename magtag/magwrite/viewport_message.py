"""Bounded semantic viewport payload used by the display-only MagTag."""

from magwrite.uart_protocol import crc32

MAX_TITLE = 20
MAX_STATUS = 20
# Raised from three to five for the multiline editor, and from five by twenty-
# eight to six by forty-eight when the UI moved to ``terminalio.FONT``: the
# built-in font's 6 px cell is what the panel actually fits, and the pair is
# derived in ``magwrite/viewport_renderer.capacity`` rather than chosen here. A
# host test asserts these two against it and against the Fruit Jam's layout.
#
# Worst case payload is 4 + 20 + 1 + 20 + 1 + 6 * (1 + 48) = 340 bytes, which is
# what raised the protocol maximum from 192 to 384. Every earlier frame -- three
# lines or five, 28 columns or fewer -- is still a valid frame.
MAX_LINES = 6
MAX_LINE_CHARS = 48


def _ascii(value, limit, label):
    try:
        data = value.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(label + " must be ASCII")
    if len(data) > limit:
        raise ValueError(label + " exceeds maximum")
    return data


class ViewportMessage:
    def __init__(self, revision, scenario_id, title, lines, cursor_row, cursor_column, status):
        if not (1 <= scenario_id <= 255):
            raise ValueError("invalid scenario")
        if not (1 <= len(lines) <= MAX_LINES):
            raise ValueError("invalid line count")
        if not (0 <= cursor_row < len(lines)):
            raise ValueError("invalid cursor row")
        if not (0 <= cursor_column <= len(lines[cursor_row])):
            raise ValueError("invalid cursor column")
        self.revision = revision
        self.scenario_id = scenario_id
        self.title = title
        self.lines = tuple(lines)
        self.cursor_row = cursor_row
        self.cursor_column = cursor_column
        self.status = status
        self.encode()

    def encode(self):
        title = _ascii(self.title, MAX_TITLE, "title")
        status = _ascii(self.status, MAX_STATUS, "status")
        encoded_lines = [_ascii(line, MAX_LINE_CHARS, "line") for line in self.lines]
        out = bytearray((self.scenario_id, self.cursor_row, self.cursor_column, len(title)))
        out.extend(title)
        out.append(len(status))
        out.extend(status)
        out.append(len(encoded_lines))
        for line in encoded_lines:
            out.append(len(line))
            out.extend(line)
        return bytes(out)

    def digest(self):
        return "%08X" % crc32(self.encode())

    @classmethod
    def decode(cls, revision, payload):
        try:
            scenario, row, column, title_size = payload[0:4]
            at = 4
            title = payload[at : at + title_size].decode("ascii")
            at += title_size
            status_size = payload[at]
            at += 1
            status = payload[at : at + status_size].decode("ascii")
            at += status_size
            count = payload[at]
            at += 1
            lines = []
            for _ in range(count):
                size = payload[at]
                at += 1
                lines.append(payload[at : at + size].decode("ascii"))
                at += size
            if at != len(payload):
                raise ValueError("trailing viewport bytes")
            return cls(revision, scenario, title, lines, row, column, status)
        except (IndexError, UnicodeError):
            raise ValueError("malformed viewport payload")
