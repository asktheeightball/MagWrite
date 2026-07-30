"""Unguarded, read-only microSD probe for the Fruit Jam.

Run from the serial REPL only, with every physical-test gate still DISABLED:

    >>> import fruitjam_sd_probe

It answers three questions and changes nothing:

1. what SD-related aliases does this board actually expose;
2. is a card present, how large is it, and does it carry a mountable FAT volume;
3. what does the shipped ``sd_storage.mount`` report for it.

The third matters most. A probe that reimplements detection proves something
about the probe; this one calls the real V1.2 code path, so a PASS here is
evidence about what the runtime will do.

It writes no guard file, writes nothing to any filesystem, mounts nothing
permanently, and never calls ``storage.remount``. Card blocks are only ever
read.
"""

try:
    import json
except ImportError:  # pragma: no cover - CircuitPython builds vary
    import ujson as json

import board
import busio
import digitalio
import os
import storage

try:
    import sdcardio
except ImportError:  # pragma: no cover - a build without the driver
    sdcardio = None

from magwrite_transport import sd_storage

# Candidate volume-boot-record offsets. 133 is what this card's own partition
# table claims; the rest are the offsets a card is conventionally formatted at,
# checked so a stale partition table cannot hide an otherwise usable volume.
CANDIDATE_LBAS = (0, 1, 32, 63, 64, 128, 132, 133, 134, 2048, 4096, 8192, 16384)


def emit(event, **fields):
    fields["event"] = event
    print(json.dumps(fields, separators=(",", ":")))


def describe_aliases():
    emit("sd_probe_aliases",
         aliases=list(sd_storage.board_sd_aliases(board)),
         has_shared_spi=hasattr(board, "SPI"),
         has_sdcardio=sdcardio is not None,
         has_os_sync=hasattr(os, "sync"),
         has_os_statvfs=hasattr(os, "statvfs"))


def read_card_detect():
    if not hasattr(board, "SD_CARD_DETECT"):
        return
    try:
        pin = digitalio.DigitalInOut(board.SD_CARD_DETECT)
    except Exception as error:  # noqa: BLE001 - a claimed pin is a finding
        emit("sd_probe_card_detect_unavailable", detail=str(error))
        return
    try:
        pin.direction = digitalio.Direction.INPUT
        pin.pull = digitalio.Pull.UP
        emit("sd_probe_card_detect", raw_value=pin.value,
             interpreted="present" if not pin.value else "absent")
    finally:
        pin.deinit()


def survey_card():
    """Read-only survey of what is physically on the card."""
    if sdcardio is None:
        emit("sd_probe_no_driver")
        return None
    bus = busio.SPI(board.SD_SCK, board.SD_MOSI, board.SD_MISO)
    try:
        card = sdcardio.SDCard(bus, board.SD_CS)
    except OSError as error:
        emit("sd_probe_absent", detail=str(error))
        bus.deinit()
        return None
    blocks = card.count()
    emit("sd_probe_card", blocks=blocks, megabytes=blocks * 512 // 1048576)

    block = bytearray(512)
    card.readblocks(0, block)
    partitions = []
    for index in range(4):
        base = 446 + index * 16
        kind = block[base + 4]
        if not kind:
            continue
        start = (block[base + 8] | block[base + 9] << 8
                 | block[base + 10] << 16 | block[base + 11] << 24)
        length = (block[base + 12] | block[base + 13] << 8
                  | block[base + 14] << 16 | block[base + 15] << 24)
        partitions.append({
            "index": index + 1, "type": "0x%02X" % kind,
            "start_lba": start, "sectors": length,
            # A partition claiming to run past the end of the card is a corrupt
            # table, and is reported rather than quietly tolerated.
            "fits_on_card": start + length <= blocks,
        })
    emit("sd_probe_mbr",
         signature="0x%02X%02X" % (block[510], block[511]),
         partitions=partitions)

    found = []
    for lba in CANDIDATE_LBAS:
        if lba >= blocks:
            continue
        card.readblocks(lba, block)
        bytes_per_sector = block[11] | block[12] << 8
        tag16 = bytes(block[54:59])
        tag32 = bytes(block[82:87])
        if bytes_per_sector not in (512, 1024, 2048, 4096):
            continue
        if tag16[:3] == b"FAT" or tag32[:3] == b"FAT":
            found.append({
                "lba": lba, "bytes_per_sector": bytes_per_sector,
                "fat16_tag": str(tag16), "fat32_tag": str(tag32),
            })
    emit("sd_probe_fat_scan", volumes_found=found, scanned=list(CANDIDATE_LBAS))
    # Both the card and the bus must be released, not just the bus. Leaving the
    # card object alive keeps SD_CS claimed, and the real mount below then fails
    # with "SD_CS in use" -- a probe artefact that looks exactly like a hardware
    # fault and would be reported as one.
    try:
        card.deinit()
    except AttributeError:
        pass
    bus.deinit()
    return blocks


def try_real_mount():
    """The shipped code path, not a reimplementation of it."""
    result = sd_storage.mount(
        board, sdcardio, storage, busio=busio, digitalio=digitalio,
        cs_alias="SD_CS", sck_alias="SD_SCK", mosi_alias="SD_MOSI",
        miso_alias="SD_MISO", mount_point="/sd", log=lambda record: None,
    )
    emit("sd_probe_real_mount", **result.summary())
    return result


emit("sd_probe_started")
describe_aliases()
read_card_detect()
survey_card()
try:
    try_real_mount()
except Exception as error:  # noqa: BLE001 - the probe reports, never raises
    emit("sd_probe_real_mount_raised", detail=str(error))
emit("sd_probe_complete")
