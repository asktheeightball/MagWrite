"""Checkpoint-gated REFRESH_50 and REFRESH_100 physical test entry point."""

import json
import os
import storage
import supervisor
import time

import config
from magwrite.characterization import (
    CharacterizationTest,
    REFRESH_50_PASS_GUARD,
    guard_paths,
)
from magwrite.display_adapter import (
    REFRESH_100_MODE,
    validate_physical_test_activation,
)
from magwrite.serial_log import StructuredSerialLogger
from magwrite.test_pattern import draw_text, landscape_rect
from magwrite.uc8151_adapter import UC8151DisplayAdapter, UPSTREAM_COMMIT


class PersistentTestGuard:
    def __init__(self, mode):
        self.started, self.completed = guard_paths(mode)

    def claim(self):
        for path in (self.started, self.completed):
            try:
                os.stat(path)
                return False
            except OSError:
                pass
        with open(self.started, "w") as handle:
            handle.write("claimed\n")
        return True

    def complete(self, summary):
        with open(self.completed, "w") as handle:
            handle.write(json.dumps(summary))


def path_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


# Allow a USB serial monitor to reconnect after the true reset that runs
# boot.py. This keeps the boot record and initial full-refresh timing capturable.
time.sleep(3)
logger = StructuredSerialLogger()
mode = config.PHYSICAL_TEST_MODE
logger(
    {
        "event": "characterization_boot",
        "decision": config.HARDWARE_COMPATIBILITY_DECISION,
        "controller": config.DISPLAY_CONTROLLER,
        "activation": config.ENABLE_PHYSICAL_DISPLAY,
        "test_mode": mode,
        "upstream_commit": UPSTREAM_COMMIT,
    }
)

try:
    validate_physical_test_activation(config, mode)
except Exception as error:
    logger({"event": "physical_test_refused", "detail": str(error)})
    while True:
        time.sleep(3600)

supervisor.runtime.autoreload = False
adapter = UC8151DisplayAdapter(config, mode)


def checkerboard(epd, x, y, width, height, phase):
    for yy in range(y, y + height):
        for xx in range(x, x + width):
            ink = ((xx // 4) + (yy // 4) + phase) % 2
            epd.pixel(yy, 295 - xx, ink)


def render_frame(index, total):
    epd = adapter.driver
    epd.fill(0)
    draw_text(epd, "MAGWRITE REFRESH TEST", 106, 5, 1)
    draw_text(epd, "UPDATE %03d / %03d" % (index, total), 64, 18, 2)

    # Static black/white controls.
    landscape_rect(epd, 8, 42, 38, 22, 1)
    landscape_rect(epd, 50, 42, 38, 22, 0)
    # Alternating transition regions.
    landscape_rect(epd, 94, 42, 52, 22, index % 2)
    landscape_rect(epd, 150, 42, 52, 22, (index + 1) % 2)
    # Checkerboard phase changes every update.
    checkerboard(epd, 208, 42, 78, 22, index % 2)

    # One-pixel edge and center references.
    landscape_rect(epd, 3, 70, 290, 1, 1)
    landscape_rect(epd, 3, 122, 290, 1, 1)
    landscape_rect(epd, 3, 70, 1, 53, 1)
    landscape_rect(epd, 292, 70, 1, 53, 1)
    landscape_rect(epd, 148, 70, 1, 53, 1)

    # Repeatedly erased/redrawn text and moving marker.
    phrase = "BLACK TO WHITE" if index % 2 else "WHITE TO BLACK"
    draw_text(epd, phrase, 16, 80, 1)
    marker_x = 10 + (index * 11) % 270
    landscape_rect(epd, marker_x, 106, 10, 8, 1)
    return epd.buf


def checkpoint(test_name, index):
    logger({"event": "checkpoint_wait", "test": test_name, "index": index})
    response = input("Type CONTINUE or STOP: ").strip().upper()
    approved = response == "CONTINUE"
    logger(
        {
            "event": "checkpoint_response",
            "test": test_name,
            "index": index,
            "approved": approved,
        }
    )
    return approved


prerequisite = path_exists(REFRESH_50_PASS_GUARD)
test = CharacterizationTest(
    mode,
    adapter,
    render_frame,
    PersistentTestGuard(mode),
    logger,
    time.monotonic,
    checkpoint,
    prerequisite_passed=prerequisite,
)

try:
    result = test.run()
    logger({"event": "characterization_halted", "result": result})
finally:
    try:
        storage.remount("/", readonly=True)
    except RuntimeError as error:
        logger({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
