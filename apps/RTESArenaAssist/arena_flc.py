from __future__ import annotations
import struct
from dataclasses import dataclass
FLC_TYPE = 44818
_FRAME_TYPE = 61946
_HEADER_LEN = 128
_FRAME_HEADER_LEN = 16
_CHUNK_HEADER_LEN = 6
_FLI_SS2 = 7
_FLI_LC = 12
_BLACK = 13
_FLI_BRUN = 15
_FLI_COPY = 16

@dataclass(frozen=True)
class FlcAnimation:
    width: int
    height: int
    frames: tuple

def _signed(value: int) -> int:
    return value - 256 if value > 127 else value

def _put(pixels: bytearray, start: int, chunk: bytes, declared: int, room: int) -> None:
    if len(chunk) < declared:
        raise ValueError('chunk shorter than declared')
    n = min(declared, room)
    if n > 0:
        pixels[start:start + n] = chunk[:n]

def _apply_byte_run(body: bytes, pixels: bytearray, width: int, height: int) -> None:
    p = 0
    for y in range(height):
        p += 1
        x = 0
        row = y * width
        while x < width:
            count = _signed(body[p])
            p += 1
            if count > 0:
                _put(pixels, row + x, bytes((body[p],)) * count, count, width - x)
                p += 1
                x += count
            elif count < 0:
                n = -count
                _put(pixels, row + x, body[p:p + n], n, width - x)
                p += n
                x += n
            else:
                raise ValueError('byte run packet of zero')

def _apply_delta_fli(body: bytes, pixels: bytearray, width: int) -> None:
    first, lines = struct.unpack_from('<HH', body, 0)
    p = 4
    for y in range(first, first + lines):
        packets = body[p]
        p += 1
        x = 0
        row = y * width
        for _ in range(packets):
            x += body[p]
            count = _signed(body[p + 1])
            p += 2
            if count > 0:
                _put(pixels, row + x, body[p:p + count], count, width - x)
                p += count
                x += count
            elif count < 0:
                n = -count
                _put(pixels, row + x, bytes((body[p],)) * n, n, width - x)
                p += 1
                x += n

def _apply_delta_flc(body: bytes, pixels: bytearray, width: int) -> None:
    lines = struct.unpack_from('<H', body, 0)[0]
    p = 2
    y = 0
    for _ in range(lines):
        while True:
            word = struct.unpack_from('<h', body, p)[0]
            p += 2
            if word >= 0:
                packets = word
                break
            if word & 16384:
                y += -word
                continue
            pixels[y * width + width - 1] = word & 255
        x = 0
        row = y * width
        for _ in range(packets):
            x += body[p]
            count = _signed(body[p + 1])
            p += 2
            if count > 0:
                n = count * 2
                _put(pixels, row + x, body[p:p + n], n, width - x)
                p += n
                x += n
            elif count < 0:
                n = -count
                pair = body[p:p + 2]
                if len(pair) < 2:
                    raise ValueError('delta pair truncated')
                _put(pixels, row + x, pair * n, n * 2, width - x)
                p += 2
                x += n * 2
        y += 1

def _apply_chunk(ctype: int, body: bytes, pixels: bytearray, width: int, height: int) -> None:
    if ctype == _BLACK:
        pixels[:] = bytes(width * height)
    elif ctype == _FLI_COPY:
        n = width * height
        if len(body) < n:
            raise ValueError('copy chunk truncated')
        pixels[:] = body[:n]
    elif ctype == _FLI_BRUN:
        _apply_byte_run(body, pixels, width, height)
    elif ctype == _FLI_LC:
        _apply_delta_fli(body, pixels, width)
    elif ctype == _FLI_SS2:
        _apply_delta_flc(body, pixels, width)

def parse(data) -> FlcAnimation | None:
    if not data or len(data) < _HEADER_LEN:
        return None
    try:
        _size, kind, count, width, height, depth = struct.unpack_from('<IHHHHH', data, 0)
    except struct.error:
        return None
    if kind != FLC_TYPE or width <= 0 or height <= 0 or (depth != 8):
        return None
    pixels = bytearray(width * height)
    frames: list[bytes] = []
    pos = _HEADER_LEN
    try:
        while pos + _FRAME_HEADER_LEN <= len(data):
            fsize, ftype, chunks = struct.unpack_from('<IHH', data, pos)
            if fsize < _FRAME_HEADER_LEN or pos + fsize > len(data):
                return None
            if ftype == _FRAME_TYPE:
                cpos = pos + _FRAME_HEADER_LEN
                end = pos + fsize
                for _ in range(chunks):
                    csize, ctype = struct.unpack_from('<IH', data, cpos)
                    if csize < _CHUNK_HEADER_LEN or cpos + csize > end:
                        return None
                    _apply_chunk(ctype, bytes(data[cpos + _CHUNK_HEADER_LEN:cpos + csize]), pixels, width, height)
                    cpos += csize
                if len(pixels) != width * height:
                    return None
                frames.append(bytes(pixels))
            pos += fsize
    except (struct.error, IndexError, ValueError):
        return None
    if count and len(frames) > count:
        del frames[count:]
    if not frames:
        return None
    return FlcAnimation(width, height, tuple(frames))

def load(vfs, name: str) -> FlcAnimation | None:
    if vfs is None:
        return None
    try:
        raw = vfs.read(name)
    except Exception:
        return None
    return parse(raw) if raw else None
__all__ = ['FLC_TYPE', 'FlcAnimation', 'parse', 'load']
