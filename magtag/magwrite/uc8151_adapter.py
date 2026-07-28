"""MagWrite adapter for the GPL-3.0-or-later upstream UC8151 driver.

MagWrite modifications, 2026-07-28: activation gating, lazy hardware imports,
framebuffer handoff, differential-state tracking, and explicit timeouts.
"""

import time

from magwrite.display_adapter import (
    DisplayAdapter,
    validate_physical_test_activation,
)


UPSTREAM_COMMIT = "61bb0fb4b76e95f8c288fb5e0f9ab11e3e413437"


def _physical_driver_factory():
    # CircuitPython-only imports are deliberately deferred until after all gates.
    import board
    import busio
    import displayio
    from uc8151 import UC8151

    displayio.release_displays()
    spi = busio.SPI(board.EPD_SCK, board.EPD_MOSI)
    return UC8151(
        spi,
        cs=board.EPD_CS,
        dc=board.EPD_DC,
        rst=board.EPD_RESET,
        busy=board.EPD_BUSY,
        width=128,
        height=296,
        full_update_period=0,
    )


class UC8151DisplayAdapter(DisplayAdapter):
    def __init__(
        self,
        config,
        selected_mode,
        driver_factory=None,
        monotonic=None,
        sleep=None,
    ):
        self.config = config
        self.selected_mode = selected_mode
        self.driver_factory = driver_factory or _physical_driver_factory
        self.monotonic = monotonic or time.monotonic
        self.sleep = sleep or time.sleep
        self.driver = None
        self.differential_state_valid = False
        self.refresh_active = False
        self.last_refresh_full = None

    @property
    def framebuffer(self):
        if self.driver is None:
            raise RuntimeError("display adapter is not initialized")
        return self.driver.buf

    def initialize(self):
        validate_physical_test_activation(self.config, self.selected_mode)
        if self.driver is None:
            self.driver = self.driver_factory()
        self.differential_state_valid = False
        self.refresh_active = False

    def begin_refresh(self, framebuffer, full=False):
        if self.driver is None:
            raise RuntimeError("display adapter is not initialized")
        if self.is_busy():
            raise RuntimeError("display is busy")
        if len(framebuffer) != len(self.driver.buf):
            raise ValueError("framebuffer size mismatch")
        self.driver.buf[:] = framebuffer
        forced_full = bool(full or not self.differential_state_valid)
        self.last_refresh_full = forced_full
        if forced_full:
            # Upstream seeds OLD and NEW and blocks until the full refresh ends.
            self.driver.update(full=True)
            self.differential_state_valid = True
            self.refresh_active = False
        else:
            # Upstream writes NEW and triggers DRF without waiting.
            self.driver.update_start()
            self.refresh_active = True
        return forced_full

    def is_busy(self):
        if self.driver is None:
            return False
        busy = self.driver.is_busy()
        if self.refresh_active and not busy:
            self.refresh_active = False
        return busy

    def wait_until_idle(self, timeout_seconds):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        started = self.monotonic()
        while self.is_busy():
            if self.monotonic() - started >= timeout_seconds:
                self.differential_state_valid = False
                return False
            self.sleep(0.01)
        return True

    def power_off(self):
        if self.driver is not None:
            self.driver.power_off()
        self.differential_state_valid = False
        self.refresh_active = False
