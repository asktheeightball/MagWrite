"""An in-memory filesystem that can lose power in the middle of a write.

This is the instrument the V1.2 recovery tests are built on, and it exists
because the alternative is unpacceptable: a recovery path verified only by
pulling a real power lead gets tested a handful of times, by hand, on the cases
somebody thought of. Here every interruption point is addressable, repeatable,
and cheap.

Two failure modes are modelled, and the difference between them matters:

``PowerCut``
    The board stopped. Bytes already handed to the filesystem may be there, in
    part or in whole, and control **never returns** to the code that was writing.
    So this raises an exception that is deliberately *not* an ``OSError``: a
    store that "handled" a power cut would be modelling something that cannot
    happen, and the test would prove nothing.

``OSError``
    The filesystem refused. Control does return, the store is expected to notice,
    record it, and keep the editor running.

``free_bytes`` returns ``None`` by default, matching a platform that cannot
report capacity, so the store's behaviour under unknown free space is the
default case rather than an afterthought.
"""


class PowerCut(Exception):
    """Power was lost mid-write. Not an OSError; nothing catches this."""


class FakeFileSystem:
    def __init__(self, free=None):
        self.files = {}
        self.directories = set()
        self.free = free
        # Set to (path, bytes_to_land) to cut power during the next write to that
        # path. ``bytes_to_land`` may exceed the payload, meaning the write landed
        # whole and power was lost immediately afterwards.
        self.cut = None
        # Paths whose next write raises OSError instead.
        self.refuse = set()
        self.appends = 0
        self.writes = 0
        self.syncs = 0
        self.renames = 0
        self.removes = 0

    # ---------------------------------------------------------------- controls

    def cut_power_during(self, path, after_bytes):
        """Arrange for the next write to ``path`` to land ``after_bytes``."""
        self.cut = (path, after_bytes)

    def refuse_writes_to(self, path):
        self.refuse.add(path)

    def snapshot(self):
        """Copy the whole volume, as a power loss would leave it on the card."""
        clone = FakeFileSystem(self.free)
        clone.directories = set(self.directories)
        for path, data in self.files.items():
            clone.files[path] = bytes(data)
        return clone

    # ------------------------------------------------------------------ layout

    def exists(self, path):
        return path in self.files or path in self.directories

    def makedirs(self, path):
        parts = [part for part in path.split("/") if part]
        walked = ""
        for part in parts:
            walked = walked + "/" + part
            self.directories.add(walked)

    # ------------------------------------------------------------------- files

    def read(self, path):
        data = self.files.get(path)
        return None if data is None else bytes(data)

    def _apply(self, path, data, existing):
        if path in self.refuse:
            raise OSError("write refused: " + path)
        if self.free is not None and self.free < len(data):
            raise OSError("no space left on device")
        if self.cut is not None and self.cut[0] == path:
            landed = self.cut[1]
            self.cut = None
            self.files[path] = existing + data[:landed]
            raise PowerCut("power lost after %d bytes of %s" % (landed, path))
        self.files[path] = existing + data
        if self.free is not None:
            self.free -= len(data)
        self.syncs += 1

    def append(self, path, data):
        self.appends += 1
        self._apply(path, data, self.files.get(path, b"") or b"")

    def write(self, path, data):
        self.writes += 1
        self._apply(path, data, b"")

    def remove(self, path):
        self.removes += 1
        if path in self.refuse:
            raise OSError("remove refused: " + path)
        self.files.pop(path, None)

    def rename(self, src, dst):
        self.renames += 1
        if src not in self.files:
            raise OSError("no such file: " + src)
        if dst in self.files:
            # FAT semantics: rename cannot overwrite. The store must clear the
            # target first, and this is what proves it does.
            raise OSError("target exists: " + dst)
        self.files[dst] = self.files.pop(src)

    def free_bytes(self):
        return self.free
