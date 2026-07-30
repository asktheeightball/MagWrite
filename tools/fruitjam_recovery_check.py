"""Read-only recovery verification for the Fruit Jam, run on the board.

    >>> import fruitjam_recovery_check

Opens the already-mounted card with the shipped ``DocumentStore`` and reports
what recovery would return. It does not mount anything, claim any pin, write any
file, or start a session, so it can be run after a forced power loss without
disturbing the evidence it is reading.

Running the real store rather than re-reading the files by hand is the point: a
transcription of a record into a host shell proves the transcription. This proves
the code that will actually restore the document.
"""

try:
    import json
except ImportError:
    import ujson as json

from magwrite_transport.document_store import DocumentStore
from magwrite_transport.sd_storage import RealFileSystem

ROOT = "/sd/magwrite"


def emit(event, **fields):
    fields["event"] = event
    print(json.dumps(fields, separators=(",", ":")))


emit("recovery_check_started", root=ROOT)

store = DocumentStore(RealFileSystem(root="/sd"), root=ROOT)
recovery = store.open()

emit("recovery_check_result", **recovery.summary())

snapshot = recovery.snapshot
if snapshot is None:
    emit("recovery_check_empty")
else:
    # The text is emitted escaped, so a multiline document survives being read
    # off a console log without the log's own line breaks corrupting it.
    emit("recovery_check_document",
         revision=snapshot.revision,
         cursor_row=snapshot.row,
         cursor_column=snapshot.column,
         characters=len(snapshot.text),
         lines=len(snapshot.text.split("\n")),
         text_escaped=snapshot.text.replace("\\", "\\\\").replace("\n", "\\n"))

emit("recovery_check_complete")
