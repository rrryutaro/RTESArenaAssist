"""automap_file.py — AUTOMAP.NN ファイル parser。

OpenTESArena 形式:
  131,136 byte = 16 cache × 8,196 byte
  cache: uint32 levelHash + Note[64] (= 4096B) + bitmap[4096] (= 2 bit/cell × 16384 cells)
  Note: x:u16 LE + y:u16 LE + text[60] (null-terminated)

bitmap encoding:
  2 bits per cell, MSB-first within byte。byte の bit 6-7 が先頭 cell、
  bit 4-5 が 2 番目、bit 2-3 が 3 番目、bit 0-1 が 4 番目。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


CACHE_SIZE = 8196
NUM_CACHES = 16
NOTE_SIZE = 64
NOTES_PER_CACHE = 64
NOTES_BYTES = NOTE_SIZE * NOTES_PER_CACHE  # 4096
BITMAP_BYTES = 4096
EXPECTED_FILE_SIZE = NUM_CACHES * CACHE_SIZE  # 131136


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
    bitmap_grid: np.ndarray | None = field(default=None)  # 128x128 unpacked

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


def _unpack_bitmap_2bit(bitmap: bytes, h: int = 128, w: int = 128) -> np.ndarray:
    """bitmap[4096] (2 bits/cell, 4 cells/byte) を h×w 2D array に展開。

    MSB-first per byte: byte の bit 6-7 が cell N、bit 4-5 が N+1、bit 2-3 が N+2、
    bit 0-1 が N+3。
    """
    arr = np.frombuffer(bitmap, dtype=np.uint8)
    cells = np.zeros(h * w, dtype=np.uint8)
    n = min(h * w, len(arr) * 4)
    for i in range(n):
        byte = arr[i // 4]
        shift = (3 - (i % 4)) * 2
        cells[i] = (byte >> shift) & 0x3
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
        level_hash = int.from_bytes(cache_data[0:4], "little")
        notes_blob = cache_data[4:4 + NOTES_BYTES]
        bitmap = cache_data[4 + NOTES_BYTES:4 + NOTES_BYTES + BITMAP_BYTES]

        notes: list[AutomapNote] = []
        for i in range(NOTES_PER_CACHE):
            note_data = notes_blob[i * NOTE_SIZE:(i + 1) * NOTE_SIZE]
            x = int.from_bytes(note_data[0:2], "little")
            y = int.from_bytes(note_data[2:4], "little")
            text = note_data[4:].split(b"\x00")[0].decode("ascii", errors="replace")
            if x == 0 and y == 0 and not text:
                continue
            notes.append(AutomapNote(slot=i, x=x, y=y, text=text))

        bitmap_grid = _unpack_bitmap_2bit(bitmap)
        caches.append(AutomapCache(
            index=ci,
            level_hash=level_hash,
            notes=notes,
            bitmap=bitmap,
            bitmap_grid=bitmap_grid,
        ))

    return AutomapFile(path=p, file_size=len(data), caches=caches)


# 現在 active な dungeon の levelHash を保持するメモリ位置 (仮説 / 観測 1 回)。
# anchor+0x6637 の 4 byte LE が AUTOMAP.NN cache の levelHash と一致することを
# 2026-05-30 観測 (= ユーザー指定 idx 13 表示中、cache #13 levelHash と一致)。
# 直前後に "automap.64" 等のファイル名テーブルが並ぶレイアウト。
CURRENT_LEVEL_HASH_OFFSET = 0x6637


def find_active_cache(
    automap: AutomapFile,
    analyzer=None,
    anchor: int | None = None,
) -> AutomapCache | None:
    """現在の dungeon cache を選ぶ。

    優先順:
      1. analyzer + anchor 提供かつ ``anchor+CURRENT_LEVEL_HASH_OFFSET`` から
         読んだ levelHash と一致する cache があれば、それを返す
      2. (フォールバック) cache[0] が有効 note または 50x50 範囲内に bitmap
         データを持つ → cache[0]
      3. それ以外で、valid_notes が最も多い cache
      4. 50x50 範囲の bitmap 密度が最も高い cache
      5. すべて空ならば cache[0]
    """
    if not automap.caches:
        return None

    # 1. memory levelHash 一致経路 (= 最優先)
    if analyzer is not None and anchor is not None:
        try:
            raw = analyzer.read_bytes(
                anchor + CURRENT_LEVEL_HASH_OFFSET, 4)
            cur_hash = int.from_bytes(raw, "little")
        except (OSError, AttributeError):
            cur_hash = None
        if cur_hash is not None and cur_hash != 0:
            for c in automap.caches:
                if c.level_hash == cur_hash:
                    return c

    # 2-5. legacy フォールバック (= memory 未提供 / 一致なし時)
    cache0 = automap.caches[0]
    cache0_50x50_nz = (
        int((cache0.bitmap_grid[:50, :50] != 0).sum())
        if cache0.bitmap_grid is not None else 0
    )
    if len(cache0.valid_notes) >= 1 or cache0_50x50_nz > 0:
        return cache0

    candidates = []
    for c in automap.caches[1:]:
        valid_count = len(c.valid_notes)
        nz_50x50 = (
            int((c.bitmap_grid[:50, :50] != 0).sum())
            if c.bitmap_grid is not None else 0
        )
        candidates.append((valid_count, nz_50x50, c))
    with_valid = [t for t in candidates if t[0] >= 1]
    if with_valid:
        with_valid.sort(key=lambda t: (-t[0], -t[1]))
        return with_valid[0][2]
    candidates.sort(key=lambda t: -t[1])
    if candidates and candidates[0][1] > 0:
        return candidates[0][2]
    return cache0
