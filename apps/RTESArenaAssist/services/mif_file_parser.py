from __future__ import annotations
import struct
from dataclasses import dataclass, field
from typing import List, Optional
_HIGH_OFFSET_BITS = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 13, 13, 13, 13, 14, 14, 14, 14, 15, 15, 15, 15, 16, 16, 16, 16, 17, 17, 17, 17, 18, 18, 18, 18, 19, 19, 19, 19, 20, 20, 20, 20, 21, 21, 21, 21, 22, 22, 22, 22, 23, 23, 23, 23, 24, 24, 25, 25, 26, 26, 27, 27, 28, 28, 29, 29, 30, 30, 31, 31, 32, 32, 33, 33, 34, 34, 35, 35, 36, 36, 37, 37, 38, 38, 39, 39, 40, 40, 41, 41, 42, 42, 43, 43, 44, 44, 45, 45, 46, 46, 47, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63]
_LOW_OFFSET_BIT_COUNT = [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8]

def decode_type08(src: bytes, uncompressed_size: int) -> bytes:
    out = bytearray(uncompressed_size)
    history = bytearray(4096)
    for i in range(4096):
        history[i] = 32
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
                    bitmask |= src[src_pos] << 8 - validbits
                    src_pos += 1
                bitmask &= 65535
                validbits += 8
            node = NodeTree[node + (bitmask >> 15 & 1)]
            bitmask = bitmask << 1 & 65535
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
                NodeFreq[freqidx], NodeFreq[nextidx] = (NodeFreq[nextidx], freq)
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
            history[historypos & 4095] = codeword
            historypos += 1
            out[dst_pos] = codeword
            dst_pos += 1
        else:
            while validbits < 9:
                if src_pos < src_len:
                    bitmask |= src[src_pos] << 8 - validbits
                    src_pos += 1
                bitmask &= 65535
                validbits += 8
            tableidx = bitmask >> 8 & 255
            bitmask = bitmask << 8 & 65535
            validbits -= 8
            offsetHigh = _HIGH_OFFSET_BITS[tableidx] << 6
            bitcount = _LOW_OFFSET_BIT_COUNT[tableidx] - 2
            offsetLow = tableidx
            for _ in range(bitcount):
                while validbits < 9:
                    if src_pos < src_len:
                        bitmask |= src[src_pos] << 8 - validbits
                        src_pos += 1
                    bitmask &= 65535
                    validbits += 8
                offsetLow = (offsetLow << 1 | bitmask >> 15 & 1) & 65535
                bitmask = bitmask << 1 & 65535
                validbits -= 1
            copypos = historypos - (offsetHigh | offsetLow & 63) - 1 & 65535
            tocopy = codeword - 256 + 3
            for _ in range(tocopy):
                b = history[copypos & 4095]
                copypos += 1
                if dst_pos < uncompressed_size:
                    out[dst_pos] = b
                    dst_pos += 1
                history[historypos & 4095] = b
                historypos += 1
    return bytes(out)

@dataclass
class MIFLevel:
    name: str = ''
    info: str = ''
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

def _decode_mif_layer(data: bytes, tag_offset: int, width: int, depth: int) -> tuple[List[List[int]], int]:
    compressed_size = int.from_bytes(data[tag_offset + 4:tag_offset + 6], 'little')
    uncompressed_size = int.from_bytes(data[tag_offset + 6:tag_offset + 8], 'little')
    src_start = tag_offset + 8
    src_end = tag_offset + 6 + compressed_size
    compressed = data[src_start:src_end]
    decomp = decode_type08(compressed, uncompressed_size)
    layer: List[List[int]] = []
    expected_cells = width * depth
    for z in range(depth):
        row = []
        for x in range(width):
            idx = (x + z * width) * 2
            voxel = int.from_bytes(decomp[idx:idx + 2], 'little')
            row.append(voxel)
        layer.append(row)
    return (layer, compressed_size + 6)

def _read_string_size_terminated(data: bytes, tag_offset: int) -> tuple[str, int]:
    size = int.from_bytes(data[tag_offset + 4:tag_offset + 6], 'little')
    raw = data[tag_offset + 6:tag_offset + 6 + size]
    nul = raw.find(0)
    if nul >= 0:
        raw = raw[:nul]
    return (raw.decode('ascii', errors='replace'), size + 6)

def _read_opaque_tag(data: bytes, tag_offset: int) -> int:
    size = int.from_bytes(data[tag_offset + 4:tag_offset + 6], 'little')
    return size + 6
_TAGS_WITH_DIMS = {b'FLOR', b'MAP1', b'MAP2'}
_TAGS_STRING = {b'NAME', b'INFO'}
_TAGS_OPAQUE = {b'FLAT', b'INNS', b'LOCK', b'LOOT', b'NUMF', b'STOR', b'TARG', b'TRIG'}

def _load_level(data: bytes, level_offset: int, width: int, depth: int) -> tuple[MIFLevel, int]:
    level_size = int.from_bytes(data[level_offset + 4:level_offset + 6], 'little')
    tag_offset = level_offset + 6
    level_end = tag_offset + level_size
    level = MIFLevel()
    while tag_offset < level_end and tag_offset + 4 <= len(data):
        tag = data[tag_offset:tag_offset + 4]
        if tag == b'LEVL':
            break
        if tag in _TAGS_WITH_DIMS:
            layer, advance = _decode_mif_layer(data, tag_offset, width, depth)
            if tag == b'FLOR':
                level.flor = layer
            elif tag == b'MAP1':
                level.map1 = layer
            else:
                level.map2 = layer
            tag_offset += advance
        elif tag == b'NAME':
            level.name, advance = _read_string_size_terminated(data, tag_offset)
            tag_offset += advance
        elif tag == b'INFO':
            level.info, advance = _read_string_size_terminated(data, tag_offset)
            tag_offset += advance
        elif tag == b'NUMF':
            size = int.from_bytes(data[tag_offset + 4:tag_offset + 6], 'little')
            if size >= 1:
                level.numf = data[tag_offset + 6]
            tag_offset += size + 6
        elif tag in _TAGS_OPAQUE:
            tag_offset += _read_opaque_tag(data, tag_offset)
        else:
            break
    return (level, tag_offset - level_offset)

def load_mif(path: str) -> MIFFile:
    data = None
    try:
        from .mif_loader import read_mif_bytes
        data = read_mif_bytes(path)
    except ImportError:
        data = None
    if data is None:
        with open(path, 'rb') as f:
            data = f.read()
    if data[0:4] != b'MHDR':
        raise ValueError(f'Not a MIF file: {path}')
    header_size = int.from_bytes(data[4:6], 'little')
    hdr = data[6:6 + header_size]
    starting_level_index = hdr[18]
    width = int.from_bytes(hdr[21:23], 'little')
    depth = int.from_bytes(hdr[23:25], 'little')
    start_points: List[tuple] = []
    for i in range(4):
        sx = int.from_bytes(hdr[2 + i * 2:2 + i * 2 + 2], 'little')
        sy = int.from_bytes(hdr[10 + i * 2:10 + i * 2 + 2], 'little')
        start_points.append((sx, sy))
    level_offset = 6 + header_size
    levels: List[MIFLevel] = []
    while level_offset + 6 <= len(data):
        if data[level_offset:level_offset + 4] != b'LEVL':
            break
        level, advance = _load_level(data, level_offset, width, depth)
        levels.append(level)
        level_offset += advance
    return MIFFile(filename=path, width=width, depth=depth, starting_level_index=starting_level_index, start_points=start_points, levels=levels)
