from __future__ import annotations

import base64
import os
import struct
import zlib



def load_col_bytes(data: bytes) -> list[tuple[int, int, int]]:
    return [(data[8 + i * 3], data[8 + i * 3 + 1], data[8 + i * 3 + 2])
            for i in range(256)]


def load_col(col_path: str) -> list[tuple[int, int, int]]:
    with open(col_path, "rb") as f:
        data = f.read()
    return load_col_bytes(data)



def _decode_type04(src: bytes, out_size: int) -> bytes:
    history = bytearray(b'\x20' * 4096)
    historypos = 0
    dst = bytearray(out_size)
    dstpos = 0

    i = 0
    bitcount = 0
    mask = 0

    while i < len(src) and dstpos < out_size:
        if bitcount == 0:
            mask = src[i]; i += 1
            bitcount = 8
        else:
            mask >>= 1

        if mask & 1:
            if i >= len(src):
                break
            b = src[i]; i += 1
            history[historypos & 0x0FFF] = b
            historypos += 1
            dst[dstpos] = b
            dstpos += 1
        else:
            if i + 1 >= len(src):
                break
            byte1 = src[i]; i += 1
            byte2 = src[i]; i += 1
            tocopy = (byte2 & 0x0F) + 3
            copypos = (((byte2 & 0xF0) << 4) | byte1) + 18

            for _ in range(tocopy):
                if dstpos >= out_size:
                    break
                val = history[copypos & 0x0FFF]
                copypos += 1
                dst[dstpos] = val
                dstpos += 1
                history[historypos & 0x0FFF] = val
                historypos += 1

        bitcount -= 1

    return bytes(dst)



_HIGH_OFFSET_BITS = bytes([
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,0x01,
    0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,0x02,
    0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,
    0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,
    0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,
    0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x09,0x09,0x09,0x09,0x09,0x09,0x09,0x09,
    0x0A,0x0A,0x0A,0x0A,0x0A,0x0A,0x0A,0x0A,0x0B,0x0B,0x0B,0x0B,0x0B,0x0B,0x0B,0x0B,
    0x0C,0x0C,0x0C,0x0C,0x0D,0x0D,0x0D,0x0D,0x0E,0x0E,0x0E,0x0E,0x0F,0x0F,0x0F,0x0F,
    0x10,0x10,0x10,0x10,0x11,0x11,0x11,0x11,0x12,0x12,0x12,0x12,0x13,0x13,0x13,0x13,
    0x14,0x14,0x14,0x14,0x15,0x15,0x15,0x15,0x16,0x16,0x16,0x16,0x17,0x17,0x17,0x17,
    0x18,0x18,0x19,0x19,0x1A,0x1A,0x1B,0x1B,0x1C,0x1C,0x1D,0x1D,0x1E,0x1E,0x1F,0x1F,
    0x20,0x20,0x21,0x21,0x22,0x22,0x23,0x23,0x24,0x24,0x25,0x25,0x26,0x26,0x27,0x27,
    0x28,0x28,0x29,0x29,0x2A,0x2A,0x2B,0x2B,0x2C,0x2C,0x2D,0x2D,0x2E,0x2E,0x2F,0x2F,
    0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39,0x3A,0x3B,0x3C,0x3D,0x3E,0x3F,
])

_LOW_OFFSET_BIT_COUNT = bytes([
    0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,
    0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,0x03,
    0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,
    0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,
    0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,0x04,
    0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,
    0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,
    0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,
    0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,0x05,
    0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,
    0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,
    0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,
    0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,
    0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,
    0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,
    0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,
])


def _decode_type08(src: bytes, out_size: int) -> bytes:
    history = bytearray(b'\x20' * 4096)
    historypos = 0

    NodeIdxMap = [0] * 941
    for i in range(626):
        NodeIdxMap[i] = (i >> 1) + 314
    NodeIdxMap[626] = 0
    for i in range(314):
        NodeIdxMap[627 + i] = i

    NodeTree = [0] * 627
    for i in range(314):
        NodeTree[i] = 627 + i
    for i in range(313):
        NodeTree[314 + i] = i * 2

    NodeFreq = [0] * 627
    for i in range(314):
        NodeFreq[i] = 1
    j = 0
    for i in range(313):
        NodeFreq[314 + i] = NodeFreq[j] + NodeFreq[j + 1]
        j += 2

    bitmask = 0
    validbits = 0
    src_idx = 0

    def ensure_bits() -> None:
        nonlocal bitmask, validbits, src_idx
        while validbits < 9:
            if src_idx < len(src):
                bitmask = (bitmask | (src[src_idx] << (8 - validbits))) & 0xFFFF
                src_idx += 1
            validbits += 8

    dst = bytearray(out_size)
    dstpos = 0

    while dstpos < out_size:
        node = NodeTree[626]
        while node < 627:
            ensure_bits()
            node = NodeTree[node + ((bitmask >> 15) & 1)]
            bitmask = (bitmask << 1) & 0xFFFF
            validbits -= 1

        freqidx = NodeIdxMap[node]
        while True:
            NodeFreq[freqidx] += 1
            freq = NodeFreq[freqidx]
            nextidx = freqidx + 1
            if nextidx < 627 and NodeFreq[nextidx] < freq:
                while nextidx < 627 and NodeFreq[nextidx] < freq:
                    nextidx += 1
                nextidx -= 1

                NodeFreq[freqidx] = NodeFreq[nextidx]
                NodeFreq[nextidx] = freq

                NodeTree[freqidx], NodeTree[nextidx] = NodeTree[nextidx], NodeTree[freqidx]

                mapidx = NodeTree[nextidx]
                NodeIdxMap[mapidx] = nextidx
                if mapidx < 627:
                    NodeIdxMap[mapidx + 1] = nextidx

                mapidx = NodeTree[freqidx]
                NodeIdxMap[mapidx] = freqidx
                if mapidx < 627:
                    NodeIdxMap[mapidx + 1] = freqidx

                freqidx = nextidx

            freqidx = NodeIdxMap[freqidx]
            if freqidx == 0:
                break

        codeword = node - 627
        if codeword < 256:
            val = codeword
            history[historypos & 0x0FFF] = val
            historypos += 1
            dst[dstpos] = val
            dstpos += 1
        else:
            ensure_bits()
            tableidx = (bitmask >> 8) & 0xFF
            bitmask = (bitmask << 8) & 0xFFFF
            validbits -= 8

            offsetHigh = _HIGH_OFFSET_BITS[tableidx] << 6
            low_bitcount = _LOW_OFFSET_BIT_COUNT[tableidx] - 2
            offsetLow = tableidx
            for _ in range(low_bitcount):
                ensure_bits()
                offsetLow = ((offsetLow << 1) | ((bitmask >> 15) & 1)) & 0xFFFF
                bitmask = (bitmask << 1) & 0xFFFF
                validbits -= 1

            copypos = (historypos - (offsetHigh | (offsetLow & 0x3F)) - 1) & 0xFFFF
            tocopy = codeword - 256 + 3
            for _ in range(tocopy):
                if dstpos >= out_size:
                    break
                val = history[copypos & 0x0FFF]
                copypos = (copypos + 1) & 0xFFFF
                history[historypos & 0x0FFF] = val
                historypos += 1
                dst[dstpos] = val
                dstpos += 1

    return bytes(dst)



def decode_cif_frames(cif_path: str) -> list[tuple[int, int, bytes]]:
    return [(w, h, pix) for w, h, _x, _y, pix in decode_cif_frames_with_offsets(cif_path)]


def decode_cif_frames_bytes(data: bytes) -> list[tuple[int, int, bytes]]:
    return [(w, h, pix)
            for w, h, _x, _y, pix in decode_cif_frames_with_offsets_bytes(data)]


def decode_cif_frames_with_offsets(
        cif_path: str) -> list[tuple[int, int, int, int, bytes]]:
    with open(cif_path, "rb") as f:
        data = f.read()
    return decode_cif_frames_with_offsets_bytes(data)


def decode_cif_frames_with_offsets_bytes(
        data: bytes) -> list[tuple[int, int, int, int, bytes]]:
    frames: list[tuple[int, int, int, int, bytes]] = []
    offset = 0

    while offset + 12 <= len(data):
        hdr = data[offset:offset + 12]
        x_off  = hdr[0] | (hdr[1] << 8)
        y_off  = hdr[2] | (hdr[3] << 8)
        width  = hdr[4] | (hdr[5] << 8)
        height = hdr[6] | (hdr[7] << 8)
        flags  = hdr[8] | (hdr[9] << 8)
        clen   = hdr[10] | (hdr[11] << 8)
        ctype  = flags & 0x00FF

        if offset + 12 + clen > len(data):
            break
        if width == 0 or height == 0:
            break

        out_size = width * height

        if ctype == 0x04:
            raw = data[offset + 12: offset + 12 + clen]
            pixels = _decode_type04(raw, out_size)
        elif ctype == 0x08:
            raw = data[offset + 14: offset + 12 + clen]
            pixels = _decode_type08(raw, out_size)
        elif ctype == 0x00:
            pixels = data[offset + 12: offset + 12 + out_size]
        else:
            pixels = bytes(out_size)

        frames.append((width, height, x_off, y_off, pixels))
        offset += 12 + clen

    return frames



def pixels_to_png_b64(pixels: bytes, width: int, height: int,
                       palette: list[tuple[int, int, int]],
                       transparent_index: int = 0) -> str:
    rgba = bytearray(width * height * 4)
    for idx, pal_idx in enumerate(pixels):
        r, g, b = palette[pal_idx]
        a = 0 if pal_idx == transparent_index else 255
        rgba[idx * 4:idx * 4 + 4] = bytes((r, g, b, a))

    def _chunk(tag: bytes, payload: bytes) -> bytes:
        crc_src = tag + payload
        return (struct.pack(">I", len(payload))
                + crc_src
                + struct.pack(">I", zlib.crc32(crc_src) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

    raw_rows = bytearray()
    for y in range(height):
        raw_rows += b'\x00'
        raw_rows += rgba[y * width * 4: (y + 1) * width * 4]

    png = (b'\x89PNG\r\n\x1a\n'
           + _chunk(b'IHDR', ihdr)
           + _chunk(b'IDAT', zlib.compress(bytes(raw_rows)))
           + _chunk(b'IEND', b''))
    return "data:image/png;base64," + base64.b64encode(png).decode()



def get_portrait_b64(cif_dir: str, pal_col_path: str, charsht_col_path: str,
                     race_idx: int, is_male: bool,
                     frame_index: int) -> str:
    try:
        prefix = "" if is_male else "F"
        cif_path = ""
        selected_digit = ""
        for digit in ("0", "1"):
            candidate = os.path.join(cif_dir, f"FACES{prefix}{digit}{race_idx}.CIF")
            if os.path.isfile(candidate):
                cif_path = candidate
                selected_digit = digit
                break
        if not cif_path:
            return ""

        frames = decode_cif_frames(cif_path)
        if not frames:
            return ""
        idx = frame_index if frame_index < len(frames) else 0
        w, h, pixels = frames[idx]

        col_path = pal_col_path if selected_digit == "0" else charsht_col_path
        palette = load_col(col_path)
        return pixels_to_png_b64(pixels, w, h, palette)
    except Exception:
        return ""
