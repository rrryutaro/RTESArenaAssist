from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional


_HIGH_OFFSET_BITS = [
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02,
    0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03,
    0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05,
    0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
    0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x09, 0x09, 0x09, 0x09, 0x09, 0x09, 0x09, 0x09,
    0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B,
    0x0C, 0x0C, 0x0C, 0x0C, 0x0D, 0x0D, 0x0D, 0x0D, 0x0E, 0x0E, 0x0E, 0x0E, 0x0F, 0x0F, 0x0F, 0x0F,
    0x10, 0x10, 0x10, 0x10, 0x11, 0x11, 0x11, 0x11, 0x12, 0x12, 0x12, 0x12, 0x13, 0x13, 0x13, 0x13,
    0x14, 0x14, 0x14, 0x14, 0x15, 0x15, 0x15, 0x15, 0x16, 0x16, 0x16, 0x16, 0x17, 0x17, 0x17, 0x17,
    0x18, 0x18, 0x19, 0x19, 0x1A, 0x1A, 0x1B, 0x1B, 0x1C, 0x1C, 0x1D, 0x1D, 0x1E, 0x1E, 0x1F, 0x1F,
    0x20, 0x20, 0x21, 0x21, 0x22, 0x22, 0x23, 0x23, 0x24, 0x24, 0x25, 0x25, 0x26, 0x26, 0x27, 0x27,
    0x28, 0x28, 0x29, 0x29, 0x2A, 0x2A, 0x2B, 0x2B, 0x2C, 0x2C, 0x2D, 0x2D, 0x2E, 0x2E, 0x2F, 0x2F,
    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F,
]

_LOW_OFFSET_BIT_COUNT = [
    0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03,
    0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03,
    0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04,
    0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04,
    0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04,
    0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05,
    0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05,
    0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05,
    0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05,
    0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06,
    0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06,
    0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06,
    0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
    0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
    0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
    0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08,
]


def decode_type08(src: bytes, uncompressed_size: int) -> bytes:
    out = bytearray(uncompressed_size)

    history = bytearray(4096)
    for i in range(4096):
        history[i] = 0x20
    historypos = 0

    NodeIdxMap = [0] * 941
    for i in range(626):
        NodeIdxMap[i] = (i >> 1) + 314
    NodeIdxMap[626] = 0
    for i in range(627, 941):
        NodeIdxMap[i] = i - 627

    NodeTree = [0] * 627
    for i in range(314):
        NodeTree[i] = 627 + i
    for i in range(314, 627):
        NodeTree[i] = (i - 314) * 2

    NodeFreq = [0] * 627
    for i in range(314):
        NodeFreq[i] = 1
    iter_i = 0
    for i in range(314, 627):
        v = NodeFreq[iter_i]
        iter_i += 1
        v += NodeFreq[iter_i]
        iter_i += 1
        NodeFreq[i] = v

    bitmask = 0
    validbits = 0
    src_pos = 0
    src_len = len(src)
    dst_pos = 0

    while dst_pos < uncompressed_size:
        node = NodeTree[626]
        while node < 627:
            while validbits < 9:
                if src_pos < src_len:
                    bitmask |= src[src_pos] << (8 - validbits)
                    src_pos += 1
                bitmask &= 0xFFFF
                validbits += 8

            node = NodeTree[node + ((bitmask >> 15) & 1)]
            bitmask = (bitmask << 1) & 0xFFFF
            validbits -= 1

        freqidx = NodeIdxMap[node]
        while True:
            NodeFreq[freqidx] += 1
            freq = NodeFreq[freqidx]
            nextidx = freqidx + 1
            if nextidx < len(NodeFreq) and NodeFreq[nextidx] < freq:
                while nextidx < len(NodeFreq) and NodeFreq[nextidx] < freq:
                    nextidx += 1
                nextidx -= 1

                NodeFreq[freqidx], NodeFreq[nextidx] = NodeFreq[nextidx], freq
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
            history[historypos & 0x0FFF] = codeword
            historypos += 1
            out[dst_pos] = codeword
            dst_pos += 1
        else:
            while validbits < 9:
                if src_pos < src_len:
                    bitmask |= src[src_pos] << (8 - validbits)
                    src_pos += 1
                bitmask &= 0xFFFF
                validbits += 8

            tableidx = (bitmask >> 8) & 0xFF
            bitmask = (bitmask << 8) & 0xFFFF
            validbits -= 8

            offsetHigh = _HIGH_OFFSET_BITS[tableidx] << 6
            bitcount = _LOW_OFFSET_BIT_COUNT[tableidx] - 2
            offsetLow = tableidx
            for _ in range(bitcount):
                while validbits < 9:
                    if src_pos < src_len:
                        bitmask |= src[src_pos] << (8 - validbits)
                        src_pos += 1
                    bitmask &= 0xFFFF
                    validbits += 8

                offsetLow = ((offsetLow << 1) | ((bitmask >> 15) & 1)) & 0xFFFF
                bitmask = (bitmask << 1) & 0xFFFF
                validbits -= 1

            copypos = (historypos - (offsetHigh | (offsetLow & 0x003F)) - 1) & 0xFFFF
            tocopy = codeword - 256 + 3
            for _ in range(tocopy):
                b = history[copypos & 0x0FFF]
                copypos += 1
                if dst_pos < uncompressed_size:
                    out[dst_pos] = b
                    dst_pos += 1
                history[historypos & 0x0FFF] = b
                historypos += 1

    return bytes(out)


@dataclass
class MIFLevel:
    name: str = ""
    info: str = ""
    numf: int = 0

    flor: List[List[int]] = field(default_factory=list)
    map1: List[List[int]] = field(default_factory=list)
    map2: List[List[int]] = field(default_factory=list)


@dataclass
class MIFFile:
    filename: str
    width: int
    depth: int
    starting_level_index: int
    start_points: List[tuple]
    levels: List[MIFLevel]


def _decode_mif_layer(data: bytes, tag_offset: int,
                       width: int, depth: int) -> tuple[List[List[int]], int]:
    compressed_size = int.from_bytes(data[tag_offset + 4: tag_offset + 6], "little")
    uncompressed_size = int.from_bytes(data[tag_offset + 6: tag_offset + 8], "little")

    src_start = tag_offset + 8
    src_end = tag_offset + 6 + compressed_size
    compressed = data[src_start: src_end]

    decomp = decode_type08(compressed, uncompressed_size)

    layer: List[List[int]] = []
    expected_cells = width * depth
    for z in range(depth):
        row = []
        for x in range(width):
            idx = (x + z * width) * 2
            voxel = int.from_bytes(decomp[idx: idx + 2], "little")
            row.append(voxel)
        layer.append(row)

    return layer, compressed_size + 6


def _read_string_size_terminated(data: bytes, tag_offset: int) -> tuple[str, int]:
    size = int.from_bytes(data[tag_offset + 4: tag_offset + 6], "little")
    raw = data[tag_offset + 6: tag_offset + 6 + size]
    nul = raw.find(0)
    if nul >= 0:
        raw = raw[:nul]
    return raw.decode("ascii", errors="replace"), size + 6


def _read_opaque_tag(data: bytes, tag_offset: int) -> int:
    size = int.from_bytes(data[tag_offset + 4: tag_offset + 6], "little")
    return size + 6


_TAGS_WITH_DIMS = {b"FLOR", b"MAP1", b"MAP2"}
_TAGS_STRING = {b"NAME", b"INFO"}
_TAGS_OPAQUE = {b"FLAT", b"INNS", b"LOCK", b"LOOT", b"NUMF", b"STOR", b"TARG", b"TRIG"}


def _load_level(data: bytes, level_offset: int,
                width: int, depth: int) -> tuple[MIFLevel, int]:
    level_size = int.from_bytes(data[level_offset + 4: level_offset + 6], "little")
    tag_offset = level_offset + 6
    level_end = tag_offset + level_size
    level = MIFLevel()

    while tag_offset < level_end and tag_offset + 4 <= len(data):
        tag = data[tag_offset: tag_offset + 4]
        if tag == b"LEVL":
            break
        if tag in _TAGS_WITH_DIMS:
            layer, advance = _decode_mif_layer(data, tag_offset, width, depth)
            if tag == b"FLOR":
                level.flor = layer
            elif tag == b"MAP1":
                level.map1 = layer
            else:
                level.map2 = layer
            tag_offset += advance
        elif tag == b"NAME":
            level.name, advance = _read_string_size_terminated(data, tag_offset)
            tag_offset += advance
        elif tag == b"INFO":
            level.info, advance = _read_string_size_terminated(data, tag_offset)
            tag_offset += advance
        elif tag == b"NUMF":
            size = int.from_bytes(data[tag_offset + 4: tag_offset + 6], "little")
            if size >= 1:
                level.numf = data[tag_offset + 6]
            tag_offset += size + 6
        elif tag in _TAGS_OPAQUE:
            tag_offset += _read_opaque_tag(data, tag_offset)
        else:
            break

    return level, tag_offset - level_offset


def load_mif(path: str) -> MIFFile:
    data = None
    try:
        from .mif_loader import read_mif_bytes
        data = read_mif_bytes(path)
    except ImportError:  # pragma: no cover - direct script fallback
        data = None
    if data is None:
        with open(path, "rb") as f:
            data = f.read()

    if data[0:4] != b"MHDR":
        raise ValueError(f"Not a MIF file: {path}")

    header_size = int.from_bytes(data[4:6], "little")

    hdr = data[6: 6 + header_size]
    starting_level_index = hdr[18]
    width = int.from_bytes(hdr[21:23], "little")
    depth = int.from_bytes(hdr[23:25], "little")

    start_points: List[tuple] = []
    for i in range(4):
        sx = int.from_bytes(hdr[2 + i * 2: 2 + i * 2 + 2], "little")
        sy = int.from_bytes(hdr[10 + i * 2: 10 + i * 2 + 2], "little")
        start_points.append((sx, sy))

    level_offset = 6 + header_size
    levels: List[MIFLevel] = []
    while level_offset + 6 <= len(data):
        if data[level_offset: level_offset + 4] != b"LEVL":
            break
        level, advance = _load_level(data, level_offset, width, depth)
        levels.append(level)
        level_offset += advance

    return MIFFile(
        filename=path,
        width=width,
        depth=depth,
        starting_level_index=starting_level_index,
        start_points=start_points,
        levels=levels,
    )
