"""Pure 1-bit landscape view composition."""


class TextSnapshot:
    __slots__ = ("revision", "rows")

    def __init__(self, revision, rows):
        self.revision = revision
        self.rows = rows


class LandscapeRenderer:
    def __init__(self, columns=36, rows=7, cursor="_"):
        if columns < 2 or rows < 1:
            raise ValueError("invalid viewport")
        self.columns = columns
        self.row_count = rows
        self.cursor = cursor

    def snapshot(self, editor):
        first = max(0, editor.row - self.row_count + 1)
        visible = []
        for row_index in range(first, min(len(editor.lines), first + self.row_count)):
            line = editor.lines[row_index]
            if row_index == editor.row:
                line = line[:editor.column] + self.cursor + line[editor.column:]
            visible.append(line[:self.columns].ljust(self.columns))
        while len(visible) < self.row_count:
            visible.append(" " * self.columns)
        return TextSnapshot(editor.revision, tuple(visible))
