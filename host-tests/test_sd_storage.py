"""microSD detection, mounting, and bring-up, with fake hardware modules.

The interesting cases here are all failures -- an empty slot, an unformatted
card, a board whose pin aliases are not what config guessed, a firmware build
with no SD driver -- and none of them are convenient to produce on a bench. They
are all produced here instead, by injecting fakes for ``board``, ``sdcardio``,
and ``storage``.

The property every test below is really defending is one thing: the system must
never report that it is saving when it is not.
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "magtag"))
sys.path.append(os.path.join(ROOT, "fruitjam"))
sys.path.append(os.path.join(ROOT, "host-tests"))

from fake_filesystem import FakeFileSystem
from magwrite_transport import sd_storage, save_state
from magwrite_transport.journal import Snapshot
from magwrite_transport.sd_storage import (
    FAILED, MOUNTED, NO_CARD, NOT_CONFIGURED, NOT_ENABLED, UNMOUNTABLE,
    MountResult, board_sd_aliases, resolve_pins,
)
from magwrite_transport.storage_bringup import bring_up


class FakeBoard:
    """A board module exposing whichever SD aliases a test wants it to."""

    def __init__(self, aliases=("SD_CS",), spi="shared-spi"):
        for name in aliases:
            setattr(self, name, "pin-" + name)
        self._spi = spi

    def SPI(self):
        if self._spi is None:
            raise RuntimeError("SPI bus in use")
        return self._spi


class FakeSdCardIo:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def SDCard(self, spi, cs, baudrate=None):
        self.calls.append((spi, cs, baudrate))
        if self.error is not None:
            raise self.error
        return "card"


class FakeStorage:
    def __init__(self, vfs_error=None, mount_error=None):
        self.vfs_error = vfs_error
        self.mount_error = mount_error
        self.mounted = []

    def VfsFat(self, card):
        if self.vfs_error is not None:
            raise self.vfs_error
        return "vfs:" + str(card)

    def mount(self, filesystem, point):
        if self.mount_error is not None:
            raise self.mount_error
        self.mounted.append((filesystem, point))


class FakeConfig:
    ENABLE_PERSISTENCE = True
    SD_CS_PIN_ALIAS = "SD_CS"
    SD_SCK_PIN_ALIAS = None
    SD_MOSI_PIN_ALIAS = None
    SD_MISO_PIN_ALIAS = None
    SD_CARD_DETECT_PIN_ALIAS = None
    SD_MOUNT_POINT = "/sd"
    DOCUMENT_ROOT = "/sd/magwrite"
    DOCUMENT_RESERVE_BYTES = 1024
    DOCUMENT_OPEN_MODE = "LATEST"


def settings(**overrides):
    class Config(FakeConfig):
        pass
    for name, value in overrides.items():
        setattr(Config, name, value)
    return Config


class PinResolutionTests(unittest.TestCase):
    def test_present_aliases_resolve_to_pins(self):
        board = FakeBoard(("SD_CS", "SD_SCK"))
        pins = resolve_pins(board, {"cs": "SD_CS", "sck": "SD_SCK"})
        self.assertEqual(pins, {"cs": "pin-SD_CS", "sck": "pin-SD_SCK"})

    def test_a_none_alias_is_an_unused_role_not_a_missing_one(self):
        pins = resolve_pins(FakeBoard(), {"cs": "SD_CS", "card_detect": None})
        self.assertEqual(list(pins), ["cs"])

    def test_a_missing_alias_names_itself_and_what_the_board_does_expose(self):
        board = FakeBoard(("SD_CS", "SD_CARD_DETECT"))
        with self.assertRaises(AttributeError) as caught:
            resolve_pins(board, {"cs": "SD_CHIP_SELECT"})
        message = str(caught.exception)
        self.assertIn("SD_CHIP_SELECT", message)
        self.assertIn("SD_CS", message)
        self.assertIn("SD_CARD_DETECT", message)

    def test_a_board_with_no_sd_aliases_says_so_rather_than_listing_nothing(self):
        with self.assertRaises(AttributeError) as caught:
            resolve_pins(FakeBoard(()), {"cs": "SD_CS"})
        self.assertIn("none", str(caught.exception))

    def test_board_aliases_are_reported_sorted(self):
        board = FakeBoard(("SD_MOSI", "SD_CS", "SD_SCK"))
        self.assertEqual(
            board_sd_aliases(board), ("SD_CS", "SD_MOSI", "SD_SCK")
        )


class MountTests(unittest.TestCase):
    def mount(self, board=None, sdcardio=None, storage=None, **kwargs):
        self.records = []
        return sd_storage.mount(
            board or FakeBoard(), sdcardio or FakeSdCardIo(),
            storage or FakeStorage(), log=self.records.append, **kwargs
        )

    def events(self):
        return [record["event"] for record in self.records]

    def test_a_healthy_card_mounts(self):
        storage = FakeStorage()
        result = self.mount(storage=storage)
        self.assertTrue(result.mounted)
        self.assertEqual(result.status, MOUNTED)
        self.assertEqual(storage.mounted, [("vfs:card", "/sd")])
        self.assertIn("sd_mounted", self.events())

    def test_an_empty_slot_is_no_card_not_a_failure(self):
        result = self.mount(sdcardio=FakeSdCardIo(OSError("no SD card")))
        self.assertEqual(result.status, NO_CARD)
        self.assertIn("no card responded", result.detail)
        self.assertIn("sd_absent", self.events())

    def test_an_unformatted_card_is_distinguished_from_an_empty_slot(self):
        """The operator must be told to format it, not to reseat it."""
        result = self.mount(storage=FakeStorage(vfs_error=OSError("no filesystem")))
        self.assertEqual(result.status, UNMOUNTABLE)
        self.assertIn("FAT", result.detail)
        self.assertIn("sd_unmountable", self.events())

    def test_a_card_that_mounts_nowhere_is_also_unmountable(self):
        result = self.mount(storage=FakeStorage(mount_error=OSError("busy")))
        self.assertEqual(result.status, UNMOUNTABLE)

    def test_a_wrong_pin_alias_is_not_configured_and_never_touches_the_card(self):
        sdcardio = FakeSdCardIo()
        result = self.mount(sdcardio=sdcardio, cs_alias="SD_NOT_A_PIN")
        self.assertEqual(result.status, NOT_CONFIGURED)
        self.assertEqual(sdcardio.calls, [])
        self.assertIn("sd_not_configured", self.events())

    def test_an_unavailable_spi_bus_fails_explicitly(self):
        result = self.mount(board=FakeBoard(spi=None))
        self.assertEqual(result.status, FAILED)
        self.assertIn("spi unavailable", result.detail)

    def test_a_non_oserror_from_the_driver_is_reported_not_mistaken_for_absence(self):
        result = self.mount(sdcardio=FakeSdCardIo(ValueError("bad argument")))
        self.assertEqual(result.status, FAILED)
        self.assertIn("sd_init_failed", self.events())

    def test_explicit_bus_aliases_build_a_dedicated_spi(self):
        class FakeBusio:
            def __init__(self):
                self.calls = []

            def SPI(self, sck, MOSI=None, MISO=None):
                self.calls.append((sck, MOSI, MISO))
                return "dedicated"

        busio = FakeBusio()
        board = FakeBoard(("SD_CS", "SD_SCK", "SD_MOSI", "SD_MISO"))
        result = self.mount(
            board=board, busio=busio, sck_alias="SD_SCK",
            mosi_alias="SD_MOSI", miso_alias="SD_MISO",
        )
        self.assertTrue(result.mounted)
        self.assertEqual(busio.calls, [("pin-SD_SCK", "pin-SD_MOSI", "pin-SD_MISO")])

    def test_a_baudrate_is_passed_through_when_given(self):
        sdcardio = FakeSdCardIo()
        self.mount(sdcardio=sdcardio, baudrate=8000000)
        self.assertEqual(sdcardio.calls[0][2], 8000000)

    def test_an_unknown_status_cannot_be_constructed(self):
        with self.assertRaises(ValueError):
            MountResult("PROBABLY_FINE")


class CardDetectTests(unittest.TestCase):
    class FakeDigitalIO:
        class Direction:
            INPUT = "input"

        class Pull:
            UP = "up"

        def __init__(self, value=False, error=None):
            self.value = value
            self.error = error
            self.deinits = 0

        def DigitalInOut(self, pin):
            if self.error is not None:
                raise self.error
            owner = self

            class Switch:
                direction = None
                pull = None
                value = owner.value

                def deinit(self):
                    owner.deinits += 1

            return Switch()

    def test_an_empty_slot_is_observed_rather_than_inferred(self):
        records = []
        digitalio = self.FakeDigitalIO(value=True)  # active low: True means absent
        sdcardio = FakeSdCardIo()
        result = sd_storage.mount(
            FakeBoard(("SD_CS", "SD_CARD_DETECT")), sdcardio, FakeStorage(),
            digitalio=digitalio, card_detect_alias="SD_CARD_DETECT",
            log=records.append,
        )
        self.assertEqual(result.status, NO_CARD)
        self.assertIn("card-detect", result.detail)
        # The card was never even addressed, and the pin was released.
        self.assertEqual(sdcardio.calls, [])
        self.assertEqual(digitalio.deinits, 1)

    def test_a_present_card_proceeds_to_mount(self):
        result = sd_storage.mount(
            FakeBoard(("SD_CS", "SD_CARD_DETECT")), FakeSdCardIo(), FakeStorage(),
            digitalio=self.FakeDigitalIO(value=False),
            card_detect_alias="SD_CARD_DETECT",
        )
        self.assertTrue(result.mounted)

    def test_an_unreadable_detect_pin_degrades_to_trying_the_card(self):
        # A detect line that cannot be read is worse than not having one, so it
        # must not become a reason to refuse a card that is actually present.
        records = []
        result = sd_storage.mount(
            FakeBoard(("SD_CS", "SD_CARD_DETECT")), FakeSdCardIo(), FakeStorage(),
            digitalio=self.FakeDigitalIO(error=RuntimeError("pin in use")),
            card_detect_alias="SD_CARD_DETECT", log=records.append,
        )
        self.assertTrue(result.mounted)
        self.assertIn(
            "sd_card_detect_unreadable", [record["event"] for record in records]
        )


class RealFileSystemTests(unittest.TestCase):
    """The durability wrapper, against a real temporary directory."""

    def setUp(self):
        import tempfile
        self.directory = tempfile.mkdtemp()
        self.syncs = []
        self.filesystem = sd_storage.RealFileSystem(
            root=self.directory, sync=lambda: self.syncs.append(1)
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.directory, name).replace("\\", "/")

    def test_a_missing_file_reads_as_none_rather_than_raising(self):
        self.assertIsNone(self.filesystem.read(self.path("absent")))
        self.assertFalse(self.filesystem.exists(self.path("absent")))

    def test_append_accumulates_and_syncs_every_time(self):
        path = self.path("log")
        self.filesystem.append(path, b"one\n")
        self.filesystem.append(path, b"two\n")
        self.assertEqual(self.filesystem.read(path), b"one\ntwo\n")
        self.assertEqual(len(self.syncs), 2)

    def test_write_replaces_rather_than_appends(self):
        path = self.path("doc")
        self.filesystem.write(path, b"first")
        self.filesystem.write(path, b"second")
        self.assertEqual(self.filesystem.read(path), b"second")

    def test_makedirs_creates_parents_and_is_idempotent(self):
        nested = self.path("a/b/c")
        self.filesystem.makedirs(nested)
        self.filesystem.makedirs(nested)
        self.assertTrue(self.filesystem.exists(nested))

    def test_removing_an_absent_file_is_not_an_error(self):
        self.filesystem.remove(self.path("never existed"))

    def test_rename_moves_the_content(self):
        self.filesystem.write(self.path("from"), b"data")
        self.filesystem.rename(self.path("from"), self.path("to"))
        self.assertEqual(self.filesystem.read(self.path("to")), b"data")
        self.assertFalse(self.filesystem.exists(self.path("from")))

    def test_a_build_without_os_sync_degrades_rather_than_raising(self):
        filesystem = sd_storage.RealFileSystem(root=self.directory, sync=False)
        filesystem._sync = None
        filesystem.sync_available = False
        filesystem.write(self.path("x"), b"y")
        self.assertEqual(filesystem.read(self.path("x")), b"y")

    def test_free_space_is_measured_on_the_card_not_on_circuitpy(self):
        # ``statvfs`` is per-filesystem, so asking about "/" would answer a
        # question about CIRCUITPY and let a full card look empty.
        self.assertEqual(self.filesystem.root, self.directory)
        free = self.filesystem.free_bytes()
        self.assertTrue(free is None or free >= 0)

    def test_the_store_runs_end_to_end_on_a_real_directory(self):
        from magwrite_transport.document_store import DocumentStore
        store = DocumentStore(self.filesystem, root=self.path("magwrite"))
        store.open()
        store.journal(Snapshot(1, 0, 3, "abc"))
        store.checkpoint(Snapshot(2, 0, 4, "abcd"))
        reopened = DocumentStore(self.filesystem, root=self.path("magwrite"))
        self.assertEqual(reopened.open().snapshot, Snapshot(2, 0, 4, "abcd"))


class BringUpTests(unittest.TestCase):
    def bring_up(self, config=None, **kwargs):
        self.records = []
        return bring_up(
            config or settings(), 0.0, self.records.append,
            board_module=kwargs.pop("board", FakeBoard()),
            sdcardio=kwargs.pop("sdcardio", FakeSdCardIo()),
            storage_module=kwargs.pop("storage", FakeStorage()),
            **kwargs
        )

    def test_a_healthy_card_produces_a_working_controller(self):
        controller, result = self.bring_up(filesystem=FakeFileSystem())
        self.assertTrue(controller.has_storage)
        self.assertEqual(result.status, MOUNTED)
        self.assertEqual(controller.state, save_state.SAVED)

    def test_disabled_persistence_reports_itself_and_still_returns_a_controller(self):
        controller, result = self.bring_up(settings(ENABLE_PERSISTENCE=False))
        self.assertFalse(controller.has_storage)
        self.assertEqual(result.status, NOT_ENABLED)
        self.assertEqual(controller.state, save_state.NO_CARD)

    def test_an_absent_card_degrades_instead_of_raising(self):
        controller, result = self.bring_up(sdcardio=FakeSdCardIo(OSError("empty")))
        self.assertFalse(controller.has_storage)
        self.assertEqual(result.status, NO_CARD)
        self.assertIn("empty", controller.storage_detail)

    def test_a_firmware_build_with_no_sd_driver_degrades(self):
        # ``dev_runtime`` passes ``sdcardio=None`` when the import failed.
        controller, result = self.bring_up(sdcardio=None)
        self.assertFalse(controller.has_storage)
        self.assertEqual(result.status, FAILED)

    def test_an_unusable_store_layout_degrades(self):
        filesystem = FakeFileSystem()

        def refuse(path):
            raise OSError("read-only")

        filesystem.makedirs = refuse
        controller, _ = self.bring_up(filesystem=filesystem)
        self.assertFalse(controller.has_storage)
        self.assertIn("store unusable", controller.storage_detail)

    def test_the_latest_draft_is_opened_by_default(self):
        filesystem = FakeFileSystem()
        controller, _ = self.bring_up(filesystem=filesystem)
        controller.store.checkpoint(Snapshot(6, 0, 2, "existing draft"))

        reopened, _ = self.bring_up(filesystem=filesystem)
        self.assertTrue(reopened.recovery.recovered)
        self.assertEqual(reopened.recovery.snapshot.text, "existing draft")

    def test_a_new_document_mode_discards_the_stored_draft(self):
        filesystem = FakeFileSystem()
        controller, _ = self.bring_up(filesystem=filesystem)
        controller.store.checkpoint(Snapshot(6, 0, 2, "existing draft"))

        fresh, _ = self.bring_up(settings(DOCUMENT_OPEN_MODE="NEW"),
                                 filesystem=filesystem)
        self.assertFalse(fresh.recovery.recovered)
        self.assertIsNone(fresh.store.read_latest())

    def test_an_unknown_open_mode_fails_closed_rather_than_guessing(self):
        """Guessing here would quietly discard somebody's draft."""
        controller, _ = self.bring_up(settings(DOCUMENT_OPEN_MODE="MAYBE"),
                                      filesystem=FakeFileSystem())
        self.assertFalse(controller.has_storage)
        self.assertIn("unknown DOCUMENT_OPEN_MODE", controller.storage_detail)

    def test_the_recovery_is_logged_with_its_truncation_state(self):
        self.bring_up(filesystem=FakeFileSystem())
        recovery = [
            record for record in self.records
            if record.get("event") == "document_recovery"
        ]
        self.assertEqual(len(recovery), 1)
        self.assertIn("truncated_final_record", recovery[0])

    def test_the_controller_takes_its_thresholds_from_config(self):
        controller, _ = self.bring_up(
            settings(AUTOSAVE_REVISIONS=3, CHECKPOINT_RECORDS=7,
                     CHECKPOINT_MAX_RECORDS=9),
            filesystem=FakeFileSystem(),
        )
        self.assertEqual(controller.autosave_revisions, 3)
        self.assertEqual(controller.checkpoint_records, 7)

    def test_a_config_missing_the_new_settings_still_brings_up(self):
        """An older config.py must not stop the board from starting."""
        class Sparse:
            ENABLE_PERSISTENCE = True

        controller, result = self.bring_up(Sparse, filesystem=FakeFileSystem())
        self.assertTrue(controller.has_storage)
        self.assertEqual(result.status, MOUNTED)


if __name__ == "__main__":
    unittest.main()
