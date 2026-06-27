from __future__ import annotations
import base64
import os
import struct
import zlib

def load_col_bytes(data: bytes) -> list[tuple[int, int, int]]:
    return [(data[8 + i * 3], data[8 + i * 3 + 1], data[8 + i * 3 + 2]) for i in range(256)]

def load_col(col_path: str) -> list[tuple[int, int, int]]:
    with open(col_path, 'rb') as f:
        data = f.read()
    return load_col_bytes(data)

def _decode_type04(src: bytes, out_size: int) -> bytes:
    history = bytearray(b' ' * 4096)
    historypos = 0
    dst = bytearray(out_size)
    dstpos = 0
    i = 0
    bitcount = 0
    mask = 0
    while i < len(src) and dstpos < out_size:
        if bitcount == 0:
            mask = src[i]
            i += 1
            bitcount = 8
        else:
            mask >>= 1
        if mask & 1:
            if i >= len(src):
                break
            b = src[i]
            i += 1
            history[historypos & 4095] = b
            historypos += 1
            dst[dstpos] = b
            dstpos += 1
        else:
            if i + 1 >= len(src):
                break
            byte1 = src[i]
            i += 1
            byte2 = src[i]
            i += 1
            tocopy = (byte2 & 15) + 3
            copypos = ((byte2 & 240) << 4 | byte1) + 18
            for _ in range(tocopy):
                if dstpos >= out_size:
                    break
                val = history[copypos & 4095]
                copypos += 1
                dst[dstpos] = val
                dstpos += 1
                history[historypos & 4095] = val
                historypos += 1
        bitcount -= 1
    return bytes(dst)
_HIGH_OFFSET_BITS = bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 13, 13, 13, 13, 14, 14, 14, 14, 15, 15, 15, 15, 16, 16, 16, 16, 17, 17, 17, 17, 18, 18, 18, 18, 19, 19, 19, 19, 20, 20, 20, 20, 21, 21, 21, 21, 22, 22, 22, 22, 23, 23, 23, 23, 24, 24, 25, 25, 26, 26, 27, 27, 28, 28, 29, 29, 30, 30, 31, 31, 32, 32, 33, 33, 34, 34, 35, 35, 36, 36, 37, 37, 38, 38, 39, 39, 40, 40, 41, 41, 42, 42, 43, 43, 44, 44, 45, 45, 46, 46, 47, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63])
_LOW_OFFSET_BIT_COUNT = bytes([3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8])

def _decode_type08(src: bytes, out_size: int) -> bytes:
    history = bytearray(b' ' * 4096)
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
                bitmask = (bitmask | src[src_idx] << 8 - validbits) & 65535
                src_idx += 1
            validbits += 8
    dst = bytearray(out_size)
    dstpos = 0
    while dstpos < out_size:
        node = NodeTree[626]
        while node < 627:
            ensure_bits()
            node = NodeTree[node + (bitmask >> 15 & 1)]
            bitmask = bitmask << 1 & 65535
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
                NodeTree[freqidx], NodeTree[nextidx] = (NodeTree[nextidx], NodeTree[freqidx])
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
            history[historypos & 4095] = val
            historypos += 1
            dst[dstpos] = val
            dstpos += 1
        else:
            ensure_bits()
            tableidx = bitmask >> 8 & 255
            bitmask = bitmask << 8 & 65535
            validbits -= 8
            offsetHigh = _HIGH_OFFSET_BITS[tableidx] << 6
            low_bitcount = _LOW_OFFSET_BIT_COUNT[tableidx] - 2
            offsetLow = tableidx
            for _ in range(low_bitcount):
                ensure_bits()
                offsetLow = (offsetLow << 1 | bitmask >> 15 & 1) & 65535
                bitmask = bitmask << 1 & 65535
                validbits -= 1
            copypos = historypos - (offsetHigh | offsetLow & 63) - 1 & 65535
            tocopy = codeword - 256 + 3
            for _ in range(tocopy):
                if dstpos >= out_size:
                    break
                val = history[copypos & 4095]
                copypos = copypos + 1 & 65535
                history[historypos & 4095] = val
                historypos += 1
                dst[dstpos] = val
                dstpos += 1
    return bytes(dst)

def decode_cif_frames(cif_path: str) -> list[tuple[int, int, bytes]]:
    return [(w, h, pix) for w, h, _x, _y, pix in decode_cif_frames_with_offsets(cif_path)]

def decode_cif_frames_bytes(data: bytes) -> list[tuple[int, int, bytes]]:
    return [(w, h, pix) for w, h, _x, _y, pix in decode_cif_frames_with_offsets_bytes(data)]

def decode_cif_frames_with_offsets(cif_path: str) -> list[tuple[int, int, int, int, bytes]]:
    with open(cif_path, 'rb') as f:
        data = f.read()
    return decode_cif_frames_with_offsets_bytes(data)

def decode_cif_frames_with_offsets_bytes(data: bytes) -> list[tuple[int, int, int, int, bytes]]:
    frames: list[tuple[int, int, int, int, bytes]] = []
    offset = 0
    while offset + 12 <= len(data):
        hdr = data[offset:offset + 12]
        x_off = hdr[0] | hdr[1] << 8
        y_off = hdr[2] | hdr[3] << 8
        width = hdr[4] | hdr[5] << 8
        height = hdr[6] | hdr[7] << 8
        flags = hdr[8] | hdr[9] << 8
        clen = hdr[10] | hdr[11] << 8
        ctype = flags & 255
        if offset + 12 + clen > len(data):
            break
        if width == 0 or height == 0:
            break
        out_size = width * height
        if ctype == 4:
            raw = data[offset + 12:offset + 12 + clen]
            pixels = _decode_type04(raw, out_size)
        elif ctype == 8:
            raw = data[offset + 14:offset + 12 + clen]
            pixels = _decode_type08(raw, out_size)
        elif ctype == 0:
            pixels = data[offset + 12:offset + 12 + out_size]
        else:
            pixels = bytes(out_size)
        frames.append((width, height, x_off, y_off, pixels))
        offset += 12 + clen
    return frames

def pixels_to_png_b64(pixels: bytes, width: int, height: int, palette: list[tuple[int, int, int]], transparent_index: int=0) -> str:
    rgba = bytearray(width * height * 4)
    for idx, pal_idx in enumerate(pixels):
        r, g, b = palette[pal_idx]
        a = 0 if pal_idx == transparent_index else 255
        rgba[idx * 4:idx * 4 + 4] = bytes((r, g, b, a))

    def _chunk(tag: bytes, payload: bytes) -> bytes:
        crc_src = tag + payload
        return struct.pack('>I', len(payload)) + crc_src + struct.pack('>I', zlib.crc32(crc_src) & 4294967295)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    raw_rows = bytearray()
    for y in range(height):
        raw_rows += b'\x00'
        raw_rows += rgba[y * width * 4:(y + 1) * width * 4]
    png = b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr) + _chunk(b'IDAT', zlib.compress(bytes(raw_rows))) + _chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()

def get_portrait_b64(cif_dir: str, pal_col_path: str, charsht_col_path: str, race_idx: int, is_male: bool, frame_index: int) -> str:
    try:
        prefix = '' if is_male else 'F'
        cif_path = ''
        selected_digit = ''
        for digit in ('0', '1'):
            candidate = os.path.join(cif_dir, f'FACES{prefix}{digit}{race_idx}.CIF')
            if os.path.isfile(candidate):
                cif_path = candidate
                selected_digit = digit
                break
        if not cif_path:
            return ''
        frames = decode_cif_frames(cif_path)
        if not frames:
            return ''
        idx = frame_index if frame_index < len(frames) else 0
        w, h, pixels = frames[idx]
        col_path = pal_col_path if selected_digit == '0' else charsht_col_path
        palette = load_col(col_path)
        return pixels_to_png_b64(pixels, w, h, palette)
    except Exception:
        return ''
