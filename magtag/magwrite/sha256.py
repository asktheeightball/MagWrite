"""SHA-256 that works on CircuitPython builds shipping no hashlib.sha256.

The ESP32-S2 CircuitPython 9.1.1 build exposes only sha1, so the pinned
UC8151 driver hash cannot be verified on-device through hashlib. This keeps
the pinned SHA-256 invariant exact by falling back to a pure-Python digest,
and prefers the native implementation wherever one is available.
"""

_MASK = 0xFFFFFFFF
_BLOCK = 64

_K = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5,
    0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC,
    0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7,
    0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3,
    0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5,
    0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
)

_INITIAL = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)


def _rotr(value, count):
    return ((value >> count) | (value << (32 - count))) & _MASK


class Sha256:
    """Incremental pure-Python SHA-256 producing uppercase hex digests."""

    def __init__(self):
        self._state = list(_INITIAL)
        self._buffer = b""
        self._length = 0

    def update(self, data):
        self._length += len(data)
        self._buffer += data
        while len(self._buffer) >= _BLOCK:
            self._compress(self._buffer[:_BLOCK])
            self._buffer = self._buffer[_BLOCK:]

    def _compress(self, block):
        words = [0] * 64
        for index in range(16):
            base = index * 4
            words[index] = (
                (block[base] << 24)
                | (block[base + 1] << 16)
                | (block[base + 2] << 8)
                | block[base + 3]
            )
        for index in range(16, 64):
            previous = words[index - 15]
            recent = words[index - 2]
            s0 = _rotr(previous, 7) ^ _rotr(previous, 18) ^ (previous >> 3)
            s1 = _rotr(recent, 17) ^ _rotr(recent, 19) ^ (recent >> 10)
            words[index] = (
                words[index - 16] + s0 + words[index - 7] + s1
            ) & _MASK

        a, b, c, d, e, f, g, h = self._state
        for index in range(64):
            s1 = _rotr(e, 6) ^ _rotr(e, 11) ^ _rotr(e, 25)
            choose = (e & f) ^ ((~e & _MASK) & g)
            t1 = (h + s1 + choose + _K[index] + words[index]) & _MASK
            s0 = _rotr(a, 2) ^ _rotr(a, 13) ^ _rotr(a, 22)
            majority = (a & b) ^ (a & c) ^ (b & c)
            t2 = (s0 + majority) & _MASK
            h = g
            g = f
            f = e
            e = (d + t1) & _MASK
            d = c
            c = b
            b = a
            a = (t1 + t2) & _MASK

        for index, value in enumerate((a, b, c, d, e, f, g, h)):
            self._state[index] = (self._state[index] + value) & _MASK

    def hexdigest(self):
        bits = self._length * 8
        padding = bytearray()
        padding.append(0x80)
        while (self._length + len(padding)) % _BLOCK != 56:
            padding.append(0x00)
        for shift in (56, 48, 40, 32, 24, 16, 8, 0):
            padding.append((bits >> shift) & 0xFF)

        saved = list(self._state)
        final = self._buffer + bytes(padding)
        offset = 0
        while offset < len(final):
            self._compress(final[offset:offset + _BLOCK])
            offset += _BLOCK
        digest = "".join("%08X" % value for value in self._state)
        self._state = saved
        return digest


def sha256_file(path, chunk_size=256):
    """Uppercase SHA-256 hex digest of a file, streamed to bound memory."""
    try:
        import hashlib

        native = getattr(hashlib, "sha256", None)
    except ImportError:
        native = None

    digest = native() if native is not None else Sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    if native is not None:
        return "".join("%02X" % value for value in digest.digest())
    return digest.hexdigest()
