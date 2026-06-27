from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
CACHE_SIZE = 8196
NUM_CACHES = 16
NOTE_SIZE = 64
NOTES_PER_CACHE = 64
NOTES_BYTES = NOTE_SIZE * NOTES_PER_CACHE
BITMAP_BYTES = 4096
EXPECTED_FILE_SIZE = NUM_CACHES * CACHE_SIZE

@dataclass
class AutomapNote:
    slot: int
    x: int
    y: int
    text: str

    @property
    def is_valid(self) -> bool:
        return 0 <= self.x < 100 and 0 <= self.y < 100

@dataclass
class AutomapCache:
    index: int
    level_hash: int
    notes: list[AutomapNote]
    bitmap: bytes
    bitmap_grid: np.ndarray | None = field(default=None)

    @property
    def valid_notes(self) -> list[AutomapNote]:
        return [n for n in self.notes if n.is_valid]

@dataclass
class AutomapFile:
    path: Path
    file_size: int
    caches: list[AutomapCache]

    @property
    def is_valid(self) -> bool:
        return self.file_size == EXPECTED_FILE_SIZE

def _unpack_bitmap_2bit(bitmap: bytes, h: int=128, w: int=128) -> np.ndarray:
    arr = np.frombuffer(bitmap, dtype=np.uint8)
    cells = np.zeros(h * w, dtype=np.uint8)
    n = min(h * w, len(arr) * 4)
    for i in range(n):
        byte = arr[i // 4]
        shift = (3 - i % 4) * 2
        cells[i] = byte >> shift & 3
    return cells.reshape(h, w)

def parse_automap_file(path: Path | str) -> AutomapFile:
    p = Path(path)
    data = p.read_bytes()
    caches: list[AutomapCache] = []
    for ci in range(NUM_CACHES):
        offset = ci * CACHE_SIZE
        cache_data = data[offset:offset + CACHE_SIZE]
        if len(cache_data) < CACHE_SIZE:
            break
        level_hash = int.from_bytes(cache_data[0:4], 'little')
        notes_blob = cache_data[4:4 + NOTES_BYTES]
        bitmap = cache_data[4 + NOTES_BYTES:4 + NOTES_BYTES + BITMAP_BYTES]
        notes: list[AutomapNote] = []
        for i in range(NOTES_PER_CACHE):
            note_data = notes_blob[i * NOTE_SIZE:(i + 1) * NOTE_SIZE]
            x = int.from_bytes(note_data[0:2], 'little')
            y = int.from_bytes(note_data[2:4], 'little')
            text = note_data[4:].split(b'\x00')[0].decode('ascii', errors='replace')
            if x == 0 and y == 0 and (not text):
                continue
            notes.append(AutomapNote(slot=i, x=x, y=y, text=text))
        bitmap_grid = _unpack_bitmap_2bit(bitmap)
        caches.append(AutomapCache(index=ci, level_hash=level_hash, notes=notes, bitmap=bitmap, bitmap_grid=bitmap_grid))
    return AutomapFile(path=p, file_size=len(data), caches=caches)
CURRENT_LEVEL_HASH_OFFSET = 26167

def find_active_cache(automap: AutomapFile, analyzer=None, anchor: int | None=None) -> AutomapCache | None:
    if not automap.caches:
        return None
    if analyzer is not None and anchor is not None:
        try:
            raw = analyzer.read_bytes(anchor + CURRENT_LEVEL_HASH_OFFSET, 4)
            cur_hash = int.from_bytes(raw, 'little')
        except (OSError, AttributeError):
            cur_hash = None
        if cur_hash is not None and cur_hash != 0:
            for c in automap.caches:
                if c.level_hash == cur_hash:
                    return c
    cache0 = automap.caches[0]
    cache0_50x50_nz = int((cache0.bitmap_grid[:50, :50] != 0).sum()) if cache0.bitmap_grid is not None else 0
    if len(cache0.valid_notes) >= 1 or cache0_50x50_nz > 0:
        return cache0
    candidates = []
    for c in automap.caches[1:]:
        valid_count = len(c.valid_notes)
        nz_50x50 = int((c.bitmap_grid[:50, :50] != 0).sum()) if c.bitmap_grid is not None else 0
        candidates.append((valid_count, nz_50x50, c))
    with_valid = [t for t in candidates if t[0] >= 1]
    if with_valid:
        with_valid.sort(key=lambda t: (-t[0], -t[1]))
        return with_valid[0][2]
    candidates.sort(key=lambda t: -t[1])
    if candidates and candidates[0][1] > 0:
        return candidates[0][2]
    return cache0
