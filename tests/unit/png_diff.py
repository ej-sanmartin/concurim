"""Compare exported PNG frames as pictures, not as file bytes.

Chrome on macOS is not bit-stable across processes. A few antialiased
edge pixels may change; a wrong frame moves far more than this.
"""

import struct
import zlib
from pathlib import Path

_LOUD_DELTA = 24
_MAX_LOUD_PIXELS = 50
_MAX_CHANGED_RATIO = 0.005
_PNG_CHANNELS = {2: 3, 6: 4}


def _paeth(left: int, up: int, upper_left: int) -> int:
    """PNG Paeth predictor. Ties prefer left, then up."""
    estimate = left + up - upper_left
    nearest = (
        (abs(estimate - left), 0, left),
        (abs(estimate - up), 1, up),
        (abs(estimate - upper_left), 2, upper_left),
    )
    return min(nearest)[2]


def _unfilter(raw: bytes, height: int, stride: int, channels: int) -> bytes:
    """Undo PNG row filters. Returns packed samples, one row after another."""
    rows = bytearray()
    prev = bytearray(stride)
    index = 0
    for _ in range(height):
        filt = raw[index]
        index += 1
        row = bytearray(raw[index : index + stride])
        index += stride
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up = prev[x]
            upper_left = prev[x - channels] if x >= channels else 0
            if filt == 0:
                predictor = 0
            elif filt == 1:
                predictor = left
            elif filt == 2:
                predictor = up
            elif filt == 3:
                predictor = (left + up) // 2
            elif filt == 4:
                predictor = _paeth(left, up, upper_left)
            else:
                raise AssertionError(f"unknown PNG filter {filt}")
            row[x] = (row[x] + predictor) & 255
        prev = row
        rows += row
    return bytes(rows)


def _png_rgb(data: bytes) -> tuple[int, int, bytes]:
    """Width, height, and packed RGB bytes of an 8-bit PNG."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError("not a PNG")
    pos = 8
    width = height = color_type = 0
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color_type = struct.unpack(
                ">IIBB", chunk[:10]
            )
            if depth != 8 or color_type not in _PNG_CHANNELS or chunk[12] != 0:
                raise AssertionError("unsupported PNG")
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
    channels = _PNG_CHANNELS[color_type]
    samples = _unfilter(
        zlib.decompress(bytes(idat)), height, width * channels, channels
    )
    if channels == 3:
        return width, height, samples
    rgb = bytearray()
    for i in range(0, len(samples), 4):
        rgb += samples[i : i + 3]
    return width, height, bytes(rgb)


def _png_delta(left: bytes, right: bytes) -> tuple[int, int, int]:
    """(changed pixels, loud pixels, peak channel delta) between two PNGs."""
    width, height, a = _png_rgb(left)
    other_w, other_h, b = _png_rgb(right)
    if (width, height) != (other_w, other_h):
        raise AssertionError(f"size {width}x{height} != {other_w}x{other_h}")
    changed = loud = peak = 0
    for i in range(0, len(a), 3):
        delta = max(
            abs(a[i] - b[i]),
            abs(a[i + 1] - b[i + 1]),
            abs(a[i + 2] - b[i + 2]),
        )
        if delta == 0:
            continue
        changed += 1
        peak = max(peak, delta)
        if delta > _LOUD_DELTA:
            loud += 1
    return changed, loud, peak


def assert_same_picture(left: Path, right: Path) -> None:
    """Fail when two frames differ by more than antialiasing."""
    a, b = left.read_bytes(), right.read_bytes()
    if a == b:
        return
    changed, loud, peak = _png_delta(a, b)
    width, height, _ = _png_rgb(a)
    limit = int(width * height * _MAX_CHANGED_RATIO)
    assert changed <= limit and loud <= _MAX_LOUD_PIXELS, (
        f"{left.name}: {changed} pixels differ "
        f"({loud} by more than {_LOUD_DELTA}), peak {peak}"
    )


def _rgb_png(width: int, height: int, rgb: bytes) -> bytes:
    """Filter-None RGB PNG, for the comparator test."""
    if len(rgb) != width * height * 3:
        raise AssertionError("rgb size does not match the image")
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride : (y + 1) * stride]

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


def test_png_delta_counts_changed_pixels():
    base = _rgb_png(2, 1, bytes([0, 0, 0, 10, 20, 30]))
    faint = bytearray([0, 0, 0, 10, 20, 30])
    faint[0] = _LOUD_DELTA
    loud = bytearray([0, 0, 0, 10, 20, 30])
    loud[1] = 255
    assert _png_delta(base, base) == (0, 0, 0)
    assert _png_delta(base, _rgb_png(2, 1, bytes(faint))) == (1, 0, _LOUD_DELTA)
    assert _png_delta(base, _rgb_png(2, 1, bytes(loud))) == (1, 1, 255)
