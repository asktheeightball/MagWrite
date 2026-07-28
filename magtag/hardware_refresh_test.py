"""Dedicated one-full-plus-20-partial UC8151 physical test entry point."""

import json
import os
import storage
import supervisor
import time

import config
from magwrite.display_adapter import (
    PHYSICAL_TEST_MODE,
    validate_physical_test_activation,
)
from magwrite.physical_test import PhysicalRefreshTest
from magwrite.serial_log import StructuredSerialLogger
from magwrite.test_pattern import draw_text, landscape_rect
from magwrite.uc8151_adapter import UC8151DisplayAdapter, UPSTREAM_COMMIT


START_GUARD = "/magwrite_refresh_test_20.started"
COMPLETE_GUARD = "/magwrite_refresh_test_20.complete"

class PersistentFileGuard:
    def claim(self):
        try:
            os.stat(START_GUARD)
            return False
        except OSError:
            pass
        try:
            os.stat(COMPLETE_GUARD)
            return False
        except OSError:
            pass
        with open(START_GUARD, "w") as handle:
            handle.write("claimed\n")
        return True

    def complete(self, summary):
        with open(COMPLETE_GUARD, "w") as handle:
            handle.write(json.dumps(summary))


logger = StructuredSerialLogger()
logger(
    {
        "event": "physical_test_boot",
        "decision": config.HARDWARE_COMPATIBILITY_DECISION,
        "controller": config.DISPLAY_CONTROLLER,
        "activation": config.ENABLE_PHYSICAL_DISPLAY,
        "test_mode": config.PHYSICAL_TEST_MODE,
        "upstream_commit": UPSTREAM_COMMIT,
    }
)

try:
    validate_physical_test_activation(config, config.PHYSICAL_TEST_MODE)
except Exception as error:
    logger({"event": "physical_test_refused", "detail": str(error)})
    while True:
        time.sleep(3600)

supervisor.runtime.autoreload = False
adapter = UC8151DisplayAdapter(config, config.PHYSICAL_TEST_MODE)


def render_frame(index):
    epd = adapter.driver
    epd.fill(0)
    draw_text(epd, "MAGWRITE REFRESH TEST", 106, 10, 1)
    draw_text(epd, "UPDATE %02d / 20" % index, 76, 30, 2)
    landscape_rect(epd, 28, 62, 112, 42, index % 2)
    landscape_rect(epd, 156, 62, 112, 42, (index + 1) % 2)
    marker_x = 20 + (index * 12) % 252
    landscape_rect(epd, marker_x, 114, 12, 8, 1)
    return epd.buf


test = PhysicalRefreshTest(
    adapter,
    render_frame,
    PersistentFileGuard(),
    logger,
    time.monotonic,
    timeout_seconds=20.0,
)
try:
    result = test.run()
    logger({"event": "physical_test_halted", "result": result})
finally:
    # Guard files are closed by this point. Return CIRCUITPY ownership to USB so
    # activation can be disabled without deleting either persistent guard.
    try:
        storage.remount("/", readonly=True)
    except RuntimeError as error:
        logger({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
