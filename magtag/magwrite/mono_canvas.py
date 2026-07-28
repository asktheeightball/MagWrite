"""Small host-safe 1-bit framebuffer compatible with the UC8151 buffer layout."""


class MonoCanvas:
    def __init__(self, width=128, height=296):
        self.width = width
        self.height = height
        self.stride = (width + 7) // 8
        self.buf = bytearray(self.stride * height)
        self.fill(0)

    def fill(self, ink):
        value = 0x00 if ink else 0xFF
        for index in range(len(self.buf)):
            self.buf[index] = value

    def pixel(self, x, y, ink):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        index = y * self.stride + (x >> 3)
        mask = 0x80 >> (x & 7)
        if ink:
            self.buf[index] &= ~mask & 0xFF
        else:
            self.buf[index] |= mask
