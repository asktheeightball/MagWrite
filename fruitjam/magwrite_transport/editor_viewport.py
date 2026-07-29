"""Fruit Jam viewport builder: the MagTag never wraps, scrolls, or windows.

The Fruit Jam decides the visible visual rows, the cursor cell, the title, the
status text, and the revision display. The result is a complete semantic
viewport that the MagTag may only bounds-check and render.

The payload is a pure function of editor state, so identical editor state always
produces an identical payload and CRC-32. That is what lets the final displayed
revision and hash be reconciled exactly against the host simulation.
"""

from magwrite_transport.deterministic_viewports import encode_viewport
from magwrite_transport.editor_layout import Layout

EDITOR_TITLE = "MAGWRITE"


class EditorViewport:
    """Builds the bounded semantic viewport for a multiline editor."""

    def __init__(self, layout=None, title=EDITOR_TITLE):
        self.layout = layout or Layout()
        self.title = title

    @property
    def columns(self):
        return self.layout.width

    @property
    def rows(self):
        return self.layout.height

    def window(self, editor):
        return self.layout.window(editor.lines, editor.row, editor.column)

    def title_text(self, editor):
        """Title plus the authoritative logical cursor position."""
        return "%s L%02d C%02d" % (
            self.title, (editor.row + 1) % 100, editor.column % 100,
        )

    def status_text(self, editor, window):
        """Document revision, viewport revision, and window position."""
        return "D%03d V%03d R%02d/%02d" % (
            editor.document_revision % 1000,
            editor.viewport_revision % 1000,
            (window["top"] + window["cursor_row"] + 1) % 100,
            window["total_rows"] % 100,
        )

    def payload(self, editor, scenario_id):
        """Encode the complete semantic viewport for this editor state."""
        window = self.window(editor)
        lines = window["lines"]
        if not lines:
            lines = ("",)
        return encode_viewport(
            scenario_id,
            self.title_text(editor),
            lines,
            window["cursor_row"],
            window["cursor_column"],
            self.status_text(editor, window),
        )
