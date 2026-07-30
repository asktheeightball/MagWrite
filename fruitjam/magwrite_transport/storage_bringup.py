"""Bring persistence up at boot, or explain precisely why it did not.

Host-safe: the hardware modules are injected, so every branch below -- including
a missing card, an unformatted card, and a card whose layout cannot be created --
is exercised under CPython.

This module exists so the board entry points stay short and so the *order* of
bring-up is written down once:

1. is persistence enabled at all;
2. is a card present and mountable;
3. can the store layout be created and read;
4. what survived, and is it a document or a fresh start.

Every step can fail, and none of them may stop the writer from typing. A failure
produces a controller with no store, which reports ``NO_CARD`` on the panel and
keeps the editor fully functional. The one outcome that is not allowed is a
silent one: whatever happens is named, logged, and carried into the session
summary.
"""

from magwrite_transport import persistence as persistence_module
from magwrite_transport import sd_storage
from magwrite_transport.document_index import (
    DocumentIndex, MAX_DOCUMENTS,
)
from magwrite_transport.document_store import DocumentStore, StoreError
from magwrite_transport.library import Library
from magwrite_transport.persistence import PersistenceController

OPEN_LATEST = "LATEST"
OPEN_NEW = "NEW"


def _setting(config, name, default):
    return getattr(config, name, default)


def bring_up(
    config, now, log, board_module=None, sdcardio=None, storage_module=None,
    busio=None, digitalio=None, filesystem=None,
):
    """Return ``(controller, mount_result)``.

    ``filesystem`` overrides the real backend, which is how host tests drive the
    whole path with no hardware module present at all. When it is supplied the
    card detection step is skipped, because there is nothing to detect.

    From V1.4 the controller also carries ``library`` and ``index`` when the
    catalogue could be brought up. Both are ``None`` on a degraded card, and a
    ``None`` library is a first-class state: the shell's four items then route
    into the one document exactly as they did in V1.3.
    """
    if not _setting(config, "ENABLE_PERSISTENCE", False):
        detail = "persistence disabled in config"
        log({"event": "persistence_disabled", "detail": detail})
        return _degraded(now, log, detail), sd_storage.MountResult(
            sd_storage.NOT_ENABLED, detail
        )

    mount_point = _setting(config, "SD_MOUNT_POINT", sd_storage.DEFAULT_MOUNT_POINT)
    if filesystem is None:
        result = sd_storage.mount(
            board_module, sdcardio, storage_module, busio=busio,
            digitalio=digitalio,
            cs_alias=_setting(config, "SD_CS_PIN_ALIAS", "SD_CS"),
            sck_alias=_setting(config, "SD_SCK_PIN_ALIAS", None),
            mosi_alias=_setting(config, "SD_MOSI_PIN_ALIAS", None),
            miso_alias=_setting(config, "SD_MISO_PIN_ALIAS", None),
            card_detect_alias=_setting(config, "SD_CARD_DETECT_PIN_ALIAS", None),
            mount_point=mount_point, log=log,
        )
        if not result.mounted:
            # Named, not swallowed. The writer sees NO_CARD and the operator sees
            # which of the four distinct reasons actually applied.
            return _degraded(now, log, result.detail or result.status), result
        filesystem = sd_storage.RealFileSystem(root=mount_point)
    else:
        result = sd_storage.MountResult(
            sd_storage.MOUNTED, "injected filesystem", mount_point
        )

    store = DocumentStore(
        filesystem,
        root=_setting(config, "DOCUMENT_ROOT", mount_point + "/magwrite"),
        reserve_bytes=_setting(config, "DOCUMENT_RESERVE_BYTES", 32768),
    )
    try:
        recovery = store.open()
    except StoreError as error:
        detail = "store unusable: " + str(error)
        log({"event": "document_store_failed", "detail": detail})
        return _degraded(now, log, detail), result

    mode = _setting(config, "DOCUMENT_OPEN_MODE", OPEN_LATEST)
    if mode == OPEN_NEW:
        try:
            store.start_new_document()
        except StoreError as error:
            detail = "cannot start a new document: " + str(error)
            log({"event": "document_store_failed", "detail": detail})
            return _degraded(now, log, detail), result
        log({"event": "document_started", "mode": OPEN_NEW})
        recovery.snapshot = None
    elif mode != OPEN_LATEST:
        # A misspelled mode fails closed here, at bring-up, rather than being
        # guessed at and quietly discarding somebody's draft.
        detail = "unknown DOCUMENT_OPEN_MODE: " + str(mode)
        log({"event": "document_store_failed", "detail": detail})
        return _degraded(now, log, detail), result
    else:
        log(dict(recovery.summary(), event="document_recovery"))

    # ------------------------------------------------------------- catalogue
    # Step 5 of the bring-up order, added in V1.4: which documents exist, and
    # which one was open last. It runs after recovery rather than before,
    # because the one question it might have to answer on a card written by an
    # earlier build is "is there an existing document to adopt", and only
    # recovery can answer that.
    index = DocumentIndex(
        filesystem, _setting(config, "DOCUMENT_ROOT", mount_point + "/magwrite"),
        max_documents=_setting(config, "MAX_DOCUMENTS", MAX_DOCUMENTS),
    )
    index.load()
    library = Library(store, index, log)

    # Migration. The V1.2/V1.3 files are already correct under the per-document
    # naming, so adopting an existing document is one catalogue append and no
    # rewrite of anything the writer owns. Their draft keeps its id, its journal,
    # its checkpoints, and its mirror.
    library.migrate(recovery)

    entry = index.active()
    if entry is not None and entry.document_id != store.document_id:
        # A card written by this build: open whatever was open last rather than
        # whatever happens to be called ``active``.
        try:
            recovery = store.select(entry.document_id)
        except StoreError as error:
            detail = "cannot open the last document: " + str(error)
            log({"event": "document_store_failed", "detail": detail})
            return _degraded(now, log, detail), result
        log(dict(recovery.summary(), event="document_recovery",
                 document_id=entry.document_id))
    if entry is not None:
        log(dict(entry.summary(), event="document_active"))
    log(dict(index.summary(), event="document_catalogue"))

    controller = PersistenceController(
        store, now, log,
        autosave_idle_seconds=_setting(
            config, "AUTOSAVE_IDLE_SECONDS",
            persistence_module.AUTOSAVE_IDLE_SECONDS),
        autosave_max_age_seconds=_setting(
            config, "AUTOSAVE_MAX_AGE_SECONDS",
            persistence_module.AUTOSAVE_MAX_AGE_SECONDS),
        autosave_revisions=_setting(
            config, "AUTOSAVE_REVISIONS",
            persistence_module.AUTOSAVE_REVISIONS),
        checkpoint_records=_setting(
            config, "CHECKPOINT_RECORDS",
            persistence_module.CHECKPOINT_RECORDS),
        checkpoint_max_records=_setting(
            config, "CHECKPOINT_MAX_RECORDS",
            persistence_module.CHECKPOINT_MAX_RECORDS),
        checkpoint_max_age_seconds=_setting(
            config, "CHECKPOINT_MAX_AGE_SECONDS",
            persistence_module.CHECKPOINT_MAX_AGE_SECONDS),
        checkpoint_idle_seconds=_setting(
            config, "CHECKPOINT_IDLE_SECONDS",
            persistence_module.CHECKPOINT_IDLE_SECONDS),
        storage_detail=result.mount_point,
    )
    controller.recovery = recovery
    controller.index = index
    controller.library = library
    controller.document_entry = entry
    return controller, result


def _degraded(now, log, detail):
    """A controller with no store: the editor works, nothing is persisted."""
    return PersistenceController(None, now, log, storage_detail=detail)
