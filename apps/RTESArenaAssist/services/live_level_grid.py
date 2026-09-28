from __future__ import annotations
import struct
from typing import Optional
LEVEL_GRID_POINTER_OFFSET = 52430
ANCHOR_LINEAR_ADDRESS = 344128
GRID_ROW_CELLS = 128

def read_level_map1(analyzer, anchor: Optional[int], width: int, height: int) -> Optional[tuple[int, ...]]:
    if analyzer is None or anchor is None or width <= 0 or (height <= 0) or (width > GRID_ROW_CELLS):
        return None
    row_bytes = GRID_ROW_CELLS * 2
    size = (height - 1) * row_bytes + width * 2
    try:
        raw_pointer = analyzer.read_bytes(anchor + LEVEL_GRID_POINTER_OFFSET, 4)
        if len(raw_pointer) < 4:
            return None
        offset, segment = struct.unpack('<HH', raw_pointer)
        if segment == 0:
            return None
        address = anchor + (segment * 16 + offset - ANCHOR_LINEAR_ADDRESS)
        raw = analyzer.read_bytes(address, size)
    except (OSError, RuntimeError, ValueError, OverflowError):
        return None
    if len(raw) < size:
        return None
    cells: list[int] = []
    for y in range(height):
        cells.extend(struct.unpack_from(f'<{width}H', raw, y * row_bytes))
    return tuple(cells)

def match_ratio(cells, reference) -> float:
    if not cells or reference is None or len(cells) != len(reference):
        return 0.0
    same = sum((1 for a, b in zip(cells, reference) if a == b))
    return same / len(cells)

def _is_flat(value: int) -> bool:
    return value & 61440 == 32768

def merge_live_cells(current, live) -> list[int]:
    if live is None or len(live) != len(current):
        return list(current)
    out = list(current)
    for i, (have, now) in enumerate(zip(current, live)):
        if have == now:
            continue
        if _is_flat(have) or _is_flat(now) or now != 0:
            out[i] = now
    return out
__all__ = ['LEVEL_GRID_POINTER_OFFSET', 'ANCHOR_LINEAR_ADDRESS', 'GRID_ROW_CELLS', 'read_level_map1', 'match_ratio', 'merge_live_cells']
