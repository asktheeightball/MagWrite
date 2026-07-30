"""microSD detection, mounting, and the real filesystem backend.

Host-safe, because every hardware module is *injected* rather than imported.
Nothing here does ``import board`` or ``import sdcardio`` at module scope, so the
detection logic -- including every failure branch -- is exercised on CPython with
fakes. That matters more here than anywhere else in the tree: the interesting
cases are a missing card, an unformatted card, and a card that fails mid-mount,
and none of those are convenient to produce on a bench.

Detection is fail-closed and, above all, *loud*
-----------------------------------------------

There is exactly one thing this module must never do: report success it does not
have. A writing tool that appears to save and does not is worse than one that
refuses to start, so every outcome below is an explicit named status carried into
the session summary and the save-state indicator.

``MOUNTED``         a FAT filesystem is mounted and writable
``NO_CARD``         no card responded; the slot is empty or the card is dead
``UNMOUNTABLE``     a card responded but carries no usable FAT filesystem
``NOT_CONFIGURED``  the board does not expose the configured pin aliases
``NOT_ENABLED``     persistence is switched off in config
``FAILED``          something else went wrong, reported verbatim

Only ``MOUNTED`` produces a store. Every other status runs the editor with
persistence disabled and ``NO_CARD`` on the panel.

Why the pin aliases are configuration
-------------------------------------

The same rule the UART pins follow: a pin alias is only trusted once it has been
physically confirmed on the board in hand. Rather than guess a name and fail with
an ``AttributeError`` deep inside construction, ``resolve_pins`` checks the board
module up front and, when an alias is missing, reports the ``SD``-prefixed names
the board *does* expose. That turns a wrong guess into one readable diagnostic
line instead of a debugging session.
"""

import os

MOUNTED = "MOUNTED"
NO_CARD = "NO_CARD"
UNMOUNTABLE = "UNMOUNTABLE"
NOT_CONFIGURED = "NOT_CONFIGURED"
NOT_ENABLED = "NOT_ENABLED"
FAILED = "FAILED"

STATUSES = (MOUNTED, NO_CARD, UNMOUNTABLE, NOT_CONFIGURED, NOT_ENABLED, FAILED)

DEFAULT_MOUNT_POINT = "/sd"


class MountResult:
    """The outcome of one detection attempt. Never a bare boolean."""

    __slots__ = ("status", "detail", "mount_point", "filesystem")

    def __init__(self, status, detail=None, mount_point=None, filesystem=None):
        if status not in STATUSES:
            raise ValueError("unknown mount status: " + str(status))
        self.status = status
        self.detail = detail
        self.mount_point = mount_point
        self.filesystem = filesystem

    @property
    def mounted(self):
        return self.status == MOUNTED

    def summary(self):
        return {
            "storage_status": self.status,
            "storage_detail": self.detail,
            "mount_point": self.mount_point,
        }


def board_sd_aliases(board_module):
    """Return the ``SD``-prefixed pin names this board actually exposes."""
    return tuple(
        sorted(name for name in dir(board_module) if name.startswith("SD"))
    )


def already_mounted(storage_module, mount_point):
    """Return the filesystem already mounted at ``mount_point``, or ``None``.

    A mount point that resolves to the *root* filesystem is not a mount: it is an
    ordinary directory sitting on CIRCUITPY, which is exactly what ``/sd`` looks
    like before a card is attached. Only a filesystem distinct from the root
    counts, so an empty ``/sd`` directory is never mistaken for a mounted card.
    """
    getmount = getattr(storage_module, "getmount", None)
    if getmount is None:
        return None
    try:
        mounted = getmount(mount_point)
        root = getmount("/")
    except (OSError, AttributeError):
        return None
    if mounted is None or mounted is root:
        return None
    return mounted


def resolve_pins(board_module, aliases):
    """Return the resolved pin objects, or raise ``AttributeError`` naming them.

    ``aliases`` maps a role to a board attribute name. A ``None`` alias means the
    role is not used, which is how an optional card-detect pin is expressed.
    """
    resolved = {}
    missing = []
    for role in sorted(aliases):
        alias = aliases[role]
        if alias is None:
            continue
        if not hasattr(board_module, alias):
            missing.append("%s=%s" % (role, alias))
            continue
        resolved[role] = getattr(board_module, alias)
    if missing:
        raise AttributeError(
            "board does not expose %s; available SD aliases: %s"
            % (", ".join(missing), ", ".join(board_sd_aliases(board_module)) or "none")
        )
    return resolved


def mount(
    board_module, sdcardio, storage_module, busio=None, digitalio=None,
    cs_alias="SD_CS", sck_alias=None, mosi_alias=None, miso_alias=None,
    card_detect_alias=None, mount_point=DEFAULT_MOUNT_POINT, baudrate=None,
    log=None,
):
    """Detect and mount the microSD card. Returns a :class:`MountResult`.

    When ``sck_alias`` is not given the board's shared ``SPI()`` bus is used,
    which is the normal path; explicit aliases exist for a board that wires the
    card to a dedicated bus.
    """
    def report(record):
        if log is not None:
            log(record)

    # A mount survives a soft reboot, and with it the SPI bus and chip-select the
    # card is on. Without this check the *second* start -- which on the
    # development runtime means every time a file is saved -- fails with
    # "SD_SCK in use" and reports NO_CARD while a perfectly good card sits
    # mounted at that very path. Adopting the existing mount is both correct and
    # the only behaviour that keeps the runtime restartable.
    existing = already_mounted(storage_module, mount_point)
    if existing is not None:
        report({"event": "sd_already_mounted", "mount_point": mount_point})
        return MountResult(
            MOUNTED, "adopted a filesystem already mounted at " + mount_point,
            mount_point, existing,
        )

    aliases = {
        "cs": cs_alias, "sck": sck_alias, "mosi": mosi_alias,
        "miso": miso_alias, "card_detect": card_detect_alias,
    }
    try:
        pins = resolve_pins(board_module, aliases)
    except AttributeError as error:
        detail = str(error)
        report({"event": "sd_not_configured", "detail": detail})
        return MountResult(NOT_CONFIGURED, detail)

    # An optional card-detect line turns "empty slot" from an inference into an
    # observation, so it is used when the board has one.
    if "card_detect" in pins and digitalio is not None:
        try:
            present = _card_present(pins["card_detect"], digitalio)
        except Exception as error:  # noqa: BLE001 - degrade, do not crash
            report({"event": "sd_card_detect_unreadable", "detail": str(error)})
        else:
            if not present:
                report({"event": "sd_absent", "source": "card_detect"})
                return MountResult(NO_CARD, "card-detect reports an empty slot")

    try:
        if sck_alias is None:
            spi = board_module.SPI()
        else:
            spi = busio.SPI(pins["sck"], MOSI=pins["mosi"], MISO=pins["miso"])
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        detail = "spi unavailable: " + str(error)
        report({"event": "sd_spi_failed", "detail": detail})
        return MountResult(FAILED, detail)

    try:
        if baudrate is None:
            card = sdcardio.SDCard(spi, pins["cs"])
        else:
            card = sdcardio.SDCard(spi, pins["cs"], baudrate)
    except OSError as error:
        # sdcardio raises OSError for an empty slot and for a card that will not
        # initialise. Both mean the same thing to the writer: nothing to save to.
        detail = "no card responded: " + str(error)
        report({"event": "sd_absent", "source": "sdcardio", "detail": detail})
        return MountResult(NO_CARD, detail)
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        detail = "card initialisation failed: " + str(error)
        report({"event": "sd_init_failed", "detail": detail})
        return MountResult(FAILED, detail)

    try:
        filesystem = storage_module.VfsFat(card)
        storage_module.mount(filesystem, mount_point)
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        # The card answered, so this is a filesystem problem, not an absent card.
        # Keeping the two apart is what lets the operator be told to format the
        # card rather than to check whether it is seated.
        detail = "cannot mount a FAT filesystem: " + str(error)
        report({"event": "sd_unmountable", "detail": detail,
                "mount_point": mount_point})
        return MountResult(UNMOUNTABLE, detail)

    report({"event": "sd_mounted", "mount_point": mount_point})
    return MountResult(MOUNTED, None, mount_point, filesystem)


def _card_present(pin, digitalio):
    """Read an optional card-detect pin. Active low, pulled up."""
    switch = digitalio.DigitalInOut(pin)
    try:
        switch.direction = digitalio.Direction.INPUT
        switch.pull = digitalio.Pull.UP
        return not switch.value
    finally:
        switch.deinit()


class RealFileSystem:
    """The :mod:`document_store` backend contract over a mounted filesystem.

    Durability is the only reason this class exists rather than the store calling
    ``open`` directly: every write flushes and then syncs before returning, so
    ``append`` returning is a real promise about what survives losing power.
    """

    def __init__(self, root=DEFAULT_MOUNT_POINT, sync=None):
        # ``os.sync`` is present on CircuitPython but this stays a lookup rather
        # than a call site, so a build without it degrades to flush-only and says
        # so instead of raising on the first save.
        if sync is None:
            sync = getattr(os, "sync", None)
        # Free space must be measured on the card, not on the internal flash:
        # ``statvfs`` reports per-filesystem figures, so asking about "/" would
        # answer a question about CIRCUITPY and let a full card look empty.
        self.root = root
        self._sync = sync
        self.syncs = 0
        self.sync_available = sync is not None

    # -------------------------------------------------------------- durability

    def _flush(self, handle):
        handle.flush()
        if self._sync is not None:
            self._sync()
            self.syncs += 1

    # ------------------------------------------------------------------ layout

    def exists(self, path):
        try:
            os.stat(path)
        except OSError:
            return False
        return True

    def makedirs(self, path):
        parts = [part for part in path.split("/") if part]
        # Every path on CircuitPython is rooted at "/", but rebuilding one
        # unconditionally from "/" turns any other absolute form into nonsense.
        # Preserving what the caller gave is what lets this class be tested
        # against a real host filesystem rather than only against a fake.
        absolute = path.startswith("/")
        walked = ""
        for part in parts:
            walked = (walked + "/" + part) if (walked or absolute) else part
            if self.exists(walked):
                continue
            try:
                os.mkdir(walked)
            except OSError as error:
                # A concurrent or duplicate creation is not a failure; anything
                # else is, and must reach the caller.
                if not self.exists(walked):
                    raise error

    # ------------------------------------------------------------------- files

    def read(self, path):
        if not self.exists(path):
            return None
        with open(path, "rb") as handle:
            return handle.read()

    def append(self, path, data):
        with open(path, "ab") as handle:
            written = handle.write(data)
            if written is not None and written != len(data):
                raise OSError("short append: %d of %d bytes" % (written, len(data)))
            self._flush(handle)

    def write(self, path, data):
        with open(path, "wb") as handle:
            written = handle.write(data)
            if written is not None and written != len(data):
                raise OSError("short write: %d of %d bytes" % (written, len(data)))
            self._flush(handle)

    def remove(self, path):
        try:
            os.remove(path)
        except OSError:
            # Absence is the desired end state, so it is not an error.
            if self.exists(path):
                raise

    def rename(self, src, dst):
        os.rename(src, dst)

    def free_bytes(self):
        statvfs = getattr(os, "statvfs", None)
        if statvfs is None:
            return None
        try:
            info = statvfs(self.root)
        except OSError:
            return None
        return info[0] * info[3]
