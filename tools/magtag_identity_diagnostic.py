"""Read-only CircuitPython identity diagnostic.

Run from the serial REPL only after stopping the current program. This script
does not call display.refresh() and does not write to the device filesystem.
"""

try:
    import json
except ImportError:
    import ujson as json


DISPLAY_NAME_PARTS = ("DISPLAY", "EPD", "EINK")


def emit(event, **fields):
    fields["event"] = event
    print(json.dumps(fields, separators=(",", ":")))


def collect():
    try:
        import board
        import microcontroller
        import os
        import supervisor
    except ImportError as error:
        emit("identity_error", reason="CircuitPython required", detail=str(error))
        return False

    uname = os.uname()
    emit(
        "runtime",
        board_id=getattr(board, "board_id", None),
        sysname=getattr(uname, "sysname", None),
        nodename=getattr(uname, "nodename", None),
        release=getattr(uname, "release", None),
        version=getattr(uname, "version", None),
        machine=getattr(uname, "machine", None),
        run_reason=str(getattr(supervisor.runtime, "run_reason", None)),
    )

    cpu = microcontroller.cpu
    uid = getattr(cpu, "uid", b"")
    emit(
        "microcontroller",
        uid="".join("%02X" % byte for byte in uid),
        frequency=getattr(cpu, "frequency", None),
        temperature=getattr(cpu, "temperature", None),
        voltage=getattr(cpu, "voltage", None),
    )

    pin_names = []
    for name in dir(board):
        if any(part in name.upper() for part in DISPLAY_NAME_PARTS):
            pin_names.append(name)
    emit("display_pins", names=pin_names)

    display = getattr(board, "DISPLAY", None)
    emit(
        "display_object",
        present=display is not None,
        type=type(display).__name__ if display is not None else None,
        width=getattr(display, "width", None),
        height=getattr(display, "height", None),
        rotation=getattr(display, "rotation", None),
        busy=getattr(display, "busy", None),
    )

    stats = os.statvfs("/")
    block_size = stats[0]
    emit(
        "filesystem",
        block_size=block_size,
        total_bytes=block_size * stats[2],
        free_bytes=block_size * stats[3],
    )
    emit("identity_complete", display_refreshed=False, files_written=False)
    return True


if __name__ == "__main__":
    collect()
