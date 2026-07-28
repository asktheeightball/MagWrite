"""A bounded, line-oriented editor with no display dependencies."""


class EditorLimit(Exception):
    pass


class LineEditor:
    def __init__(self, max_lines=64, max_chars=8192):
        if max_lines < 1 or max_chars < 1:
            raise ValueError("limits must be positive")
        self.max_lines = max_lines
        self.max_chars = max_chars
        self.lines = [""]
        self.row = 0
        self.column = 0
        self.revision = 0
        self.accepted_events = 0

    @property
    def text(self):
        return "\n".join(self.lines)

    def _changed(self):
        self.revision += 1
        self.accepted_events += 1

    def apply(self, event):
        kind = event.kind
        if kind == "insert":
            if len(self.text) >= self.max_chars:
                raise EditorLimit("character limit reached")
            line = self.lines[self.row]
            self.lines[self.row] = line[:self.column] + event.value + line[self.column:]
            self.column += len(event.value)
        elif kind == "enter":
            if len(self.lines) >= self.max_lines or len(self.text) >= self.max_chars:
                raise EditorLimit("line limit reached")
            line = self.lines[self.row]
            self.lines[self.row] = line[:self.column]
            self.lines.insert(self.row + 1, line[self.column:])
            self.row += 1
            self.column = 0
        elif kind == "backspace":
            if self.column:
                line = self.lines[self.row]
                self.lines[self.row] = line[:self.column - 1] + line[self.column:]
                self.column -= 1
            elif self.row:
                previous_length = len(self.lines[self.row - 1])
                self.lines[self.row - 1] += self.lines.pop(self.row)
                self.row -= 1
                self.column = previous_length
            else:
                self.accepted_events += 1
                return False
        elif kind == "delete":
            line = self.lines[self.row]
            if self.column < len(line):
                self.lines[self.row] = line[:self.column] + line[self.column + 1:]
            elif self.row + 1 < len(self.lines):
                self.lines[self.row] += self.lines.pop(self.row + 1)
            else:
                self.accepted_events += 1
                return False
        elif kind == "left":
            if self.column:
                self.column -= 1
            elif self.row:
                self.row -= 1
                self.column = len(self.lines[self.row])
        elif kind == "right":
            if self.column < len(self.lines[self.row]):
                self.column += 1
            elif self.row + 1 < len(self.lines):
                self.row += 1
                self.column = 0
        elif kind == "home":
            self.column = 0
        elif kind == "end":
            self.column = len(self.lines[self.row])
        else:
            raise ValueError("unknown event kind: " + kind)
        self._changed()
        return True
