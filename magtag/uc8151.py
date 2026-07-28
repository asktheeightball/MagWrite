# SPDX-FileCopyrightText: Copyright (c) 2026, BC (https://github.com/bciuca).
# SPDX-License-Identifier: GPL-3.0-or-later
#
# uc8151.py -- CircuitPython UC8151D / IL0373 driver for the Adafruit MagTag 2.9"
# panel, with 1-bit no-flash partial refresh.
#
# Ported faithfully from GxEPD2's GxEPD2_290_T5D (ZinggJM) -- the GDEW029T5D /
# UC8151D glass, which is the original MagTag 2.9" display (corroborated by the
# Pimoroni Badger 2040 UC8151 driver). That is a PROVEN-on-hardware partial
# refresh, unlike the earlier antirez port we tried, which is for a different
# panel and never cleared on this one.
#
# How the no-flash clear actually works (the thing our 3 earlier attempts missed):
#   - Two RAM banks: 0x10 = OLD (previous frame on glass), 0x13 = NEW.
#   - The partial LUTs leave white->white and black->black at ZERO drive (no
#     flash); only black->white (BW, drive to the white rail) and white->black
#     (WB) move. So a pixel only ERASES if the chip sees OLD=black, NEW=white.
#   - The chip keeps OLD correct by auto-copying NEW->OLD after each refresh,
#     BUT ONLY IF (a) power is NOT cut between updates, and (b) both banks were
#     seeded to the white byte 0xFF once at start (first refresh is a full one).
#   - Polarity: in the RAM banks 0xFF = white, 0x00 = black. CDI 0x97 (full) /
#     0x17 (partial) renders that correctly. Our buffer stores the same way.
#
# Scope: 1-bit, full-frame fast refresh + periodic full (flashing) ghost clear.
# True windowed partial (0x91/0x90 sub-rectangle) and 4-level greyscale are out
# of scope here (greyscale cannot be no-flash; keep it a separate full-refresh
# path). Native orientation is 128x296 portrait; landscape mapping is the caller's.

import time
import digitalio

# --- commands ---
_PSR = 0x00       # panel setting
_PWR = 0x01
_POF = 0x02       # power off
_PON = 0x04       # power on
_DTM_OLD = 0x10   # data start transmission 1 == OLD/previous bank
_DRF = 0x12       # display refresh
_DTM_NEW = 0x13   # data start transmission 2 == NEW/current bank
_LUT_VCOM = 0x20
_LUT_WW = 0x21
_LUT_BW = 0x22
_LUT_WB = 0x23
_LUT_BB = 0x24
_CDI = 0x50       # VCOM + data interval (border + polarity)
_TRES = 0x61      # resolution
_VDCS = 0x82      # VCOM_DC setting
_PTL = 0x90       # partial window (phase 2)
_PTIN = 0x91      # partial in (phase 2)
_PTOU = 0x92      # partial out


def _lut(seq, n):
    b = bytearray(n)
    b[0:len(seq)] = bytes(seq)
    return b


# Partial (no-flash) waveform tables, verbatim from GxEPD2_290_T5D (phase length
# Tx19 = 0x20 = 32 frames). Row = [pattern, d0, d1, d2, d3, repeat]; the pattern
# byte's top 2 bits are phase-1's level: 00 GND (hold), 01 VDH (->black), 10 VDL
# (->white), 11 float. WW/BB hold (no drive, no flash); BW drives to white
# (erase); WB drives to black.
_LUT_VCOM_P = _lut((0x00, 0x20, 0x01, 0x00, 0x00, 0x01), 44)
_LUT_WW_P = _lut((0x00, 0x20, 0x01, 0x00, 0x00, 0x01), 42)
_LUT_BW_P = _lut((0x80, 0x20, 0x01, 0x00, 0x00, 0x01), 42)
_LUT_WB_P = _lut((0x40, 0x20, 0x01, 0x00, 0x00, 0x01), 42)
_LUT_BB_P = _lut((0x00, 0x20, 0x01, 0x00, 0x00, 0x01), 42)


class UC8151:
    def __init__(self, spi, *, cs, dc, rst, busy, width=128, height=296,
                 full_update_period=20, baudrate=4_000_000):
        """spi: a busio.SPI (locked for the driver's lifetime). cs/dc/rst/busy:
        board pin objects. full_update_period: force a flashing full refresh every
        Nth update to clear ghosting (the no-flash tables are unbalanced by
        design, so a periodic full is required for panel longevity)."""
        self.spi = spi
        self.width = width
        self.height = height
        self.full_update_period = full_update_period
        self.update_count = 0
        self._powered = False
        self._partial = False

        self.cs = digitalio.DigitalInOut(cs)
        self.cs.switch_to_output(value=True)
        self.dc = digitalio.DigitalInOut(dc)
        self.dc.switch_to_output(value=False)
        self.rst = digitalio.DigitalInOut(rst)
        self.rst.switch_to_output(value=True)
        self.busy = digitalio.DigitalInOut(busy)
        self.busy.switch_to_input()

        _t0 = time.monotonic()
        while not self.spi.try_lock():
            if time.monotonic() - _t0 > 5.0:
                raise RuntimeError("EPD SPI locked; call displayio.release_displays() first")
        self.spi.configure(baudrate=baudrate, polarity=0, phase=0)

        # 1-bit buffer, RAM-bank polarity: bit 1 = white, bit 0 = black/ink.
        # Init to white (0xFF). The draw helpers below keep the intuitive API
        # (c truthy = ink/black) by clearing bits for ink.
        self.stride = (width + 7) // 8
        self.buf = bytearray(b"\xff" * (self.stride * height))

        self._reset()

    # ----- bus -----
    def _wait(self, timeout=20.0):
        t0 = time.monotonic()
        while not self.busy.value:            # low == busy
            if time.monotonic() - t0 > timeout:
                break

    def _cmd(self, cmd, data=None):
        self._wait()
        self.cs.value = False
        self.dc.value = False
        self.spi.write(bytes((cmd,)))
        if data is not None:
            self.dc.value = True
            self.spi.write(data)
        self.cs.value = True

    def _reset(self):
        self.rst.value = False
        time.sleep(0.01)
        self.rst.value = True
        time.sleep(0.01)
        self._wait()

    # ----- init / power -----
    def _init_display(self):
        self._cmd(_PSR, b"\x1f")              # LUT from OTP, 128x296
        self._cmd(_TRES, bytes((self.width & 0xFF, self.height >> 8, self.height & 0xFF)))
        self._cmd(_CDI, b"\x97")              # border floating-white, full-refresh polarity

    def _power_on(self):
        if not self._powered:
            self._cmd(_PON)
            self._wait()
            self._powered = True

    def power_off(self):
        """Cut the panel rails (for sleep). Forces a re-init + full refresh on the
        next update, since powering off loses the OLD-bank / differential state."""
        if self._powered:
            self._cmd(_POF)
            self._wait()
            self._powered = False
        self._partial = False

    def _init_full(self):
        self._init_display()                  # PSR 0x1f -> OTP (flashing) LUTs
        self._power_on()
        self._partial = False

    def _init_part(self):
        self._init_display()
        self._cmd(_PSR, b"\xbf")              # use register (our) LUTs
        self._cmd(_VDCS, b"\x08")
        self._cmd(_CDI, b"\x17")              # partial-refresh border/polarity
        self._cmd(_LUT_VCOM, _LUT_VCOM_P)
        self._cmd(_LUT_WW, _LUT_WW_P)
        self._cmd(_LUT_BW, _LUT_BW_P)
        self._cmd(_LUT_WB, _LUT_WB_P)
        self._cmd(_LUT_BB, _LUT_BB_P)
        self._power_on()
        self._partial = True

    # ----- refresh -----
    def update(self, full=False):
        """Render self.buf. Fast no-flash differential by default; a flashing full
        refresh on the first frame, every full_update_period-th frame, or full=True
        (clears ghosting and re-seeds both banks). Power is kept ON between updates
        so the chip's NEW->OLD auto-copy keeps the differential correct."""
        do_full = (
            full
            or self.update_count == 0
            or (self.full_update_period and self.update_count % self.full_update_period == 0)
        )
        if do_full:
            self._init_full()
            self._cmd(_DTM_OLD, self.buf)     # seed BOTH banks = current image
            self._cmd(_DTM_NEW, self.buf)
            self._cmd(_DRF)
            self._wait()
            self._init_part()                 # reload no-flash LUTs for fast updates
        else:
            if not self._partial:
                self._init_part()
            self._power_on()
            self._cmd(_DTM_NEW, self.buf)     # NEW; chip diffs vs OLD(0x10), no-flash LUT
            self._cmd(_DRF)
            self._wait()
            # chip auto-copies NEW(0x13) -> OLD(0x10) for the next frame's diff
        self.update_count += 1

    def is_busy(self):
        """True while the panel is still executing a refresh (busy pin low)."""
        return not self.busy.value

    def update_start(self):
        """Start a fast refresh and RETURN immediately (does NOT wait for it).
        Poll is_busy() for completion; the chip auto-copies NEW->OLD when done.
        Lets the caller keep polling buttons during the ~0.35s refresh instead of
        blocking on it. A periodic/first full refresh still runs blocking (its
        post-DRF LUT reload needs the panel idle), so it is rare."""
        do_full = (
            self.update_count == 0
            or (self.full_update_period and self.update_count % self.full_update_period == 0)
        )
        if do_full:
            self.update(full=True)            # blocking; handles update_count
            return
        if not self._partial:
            self._init_part()
        self._power_on()
        self._cmd(_DTM_NEW, self.buf)         # NEW; chip diffs vs OLD(0x10)
        self._cmd(_DRF)                       # start refresh; panel goes busy
        self.update_count += 1                # no _wait -> caller polls is_busy()

    # ----- minimal MONO drawing (bank polarity: bit 1 = white, bit 0 = ink) -----
    def fill(self, c):
        v = 0x00 if c else 0xFF               # c truthy = ink/black (0x00)
        for i in range(len(self.buf)):
            self.buf[i] = v

    def pixel(self, x, y, c):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        idx = y * self.stride + (x >> 3)
        mask = 0x80 >> (x & 7)
        if c:
            self.buf[idx] &= ~mask & 0xFF     # ink -> clear bit
        else:
            self.buf[idx] |= mask             # background -> set bit (white)

    def fill_rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.pixel(xx, yy, c)

    def hline(self, x, y, w, c):
        self.fill_rect(x, y, w, 1, c)

    def vline(self, x, y, h, c):
        self.fill_rect(x, y, 1, h, c)
