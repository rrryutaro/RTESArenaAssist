"""npc_name_generator.py — NAMECHNK.DAT ベースの NPC 名生成。"""
from __future__ import annotations

import os
from functools import lru_cache

from .arena_random import ArenaRandom


_NAMECHNK_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "docs", "ARENA-data", "DAT", "NAMECHNK.DAT",
))


NameRule = tuple[str, int | str, int | None]


_RULES: tuple[tuple[tuple[NameRule, ...], tuple[NameRule, ...]], ...] = (
    (((("idx", 0, None), ("idx", 1, None), ("str", " ", None), ("idx", 4, None), ("idx", 5, None))),
     ((("idx", 2, None), ("idx", 3, None), ("str", " ", None), ("idx", 4, None), ("idx", 5, None)))),
    (((("idx", 6, None), ("idx", 7, None), ("idx", 8, None), ("idx_chance", 9, 75))),
     ((("idx", 6, None), ("idx", 7, None), ("idx", 8, None), ("idx_chance", 9, 75), ("idx", 10, None)))),
    (((("idx", 11, None), ("idx", 12, None), ("str", " ", None), ("idx", 15, None), ("idx", 16, None), ("str", "sen", None))),
     ((("idx", 13, None), ("idx", 14, None), ("str", " ", None), ("idx", 15, None), ("idx", 16, None), ("str", "sen", None)))),
    (((("idx", 17, None), ("idx", 18, None), ("str", " ", None), ("idx", 21, None), ("idx", 22, None))),
     ((("idx", 19, None), ("idx", 20, None), ("str", " ", None), ("idx", 21, None), ("idx", 22, None)))),
    (((("idx", 23, None), ("idx", 24, None), ("str", " ", None), ("idx", 27, None), ("idx", 28, None))),
     ((("idx", 25, None), ("idx", 26, None), ("str", " ", None), ("idx", 27, None), ("idx", 28, None)))),
    (((("idx", 29, None), ("idx", 30, None), ("str", " ", None), ("idx", 33, None), ("idx", 34, None))),
     ((("idx", 31, None), ("idx", 32, None), ("str", " ", None), ("idx", 33, None), ("idx", 34, None)))),
    (((("idx", 35, None), ("idx", 36, None), ("str", " ", None), ("idx", 39, None), ("idx", 40, None))),
     ((("idx", 37, None), ("idx", 38, None), ("str", " ", None), ("idx", 39, None), ("idx", 40, None)))),
    (((("idx", 41, None), ("idx", 42, None), ("str", " ", None), ("idx", 45, None), ("idx", 46, None))),
     ((("idx", 43, None), ("idx", 44, None), ("str", " ", None), ("idx", 45, None), ("idx", 46, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None))),
     ((("idx", 47, None), ("idx_chance", 48, 75), ("idx", 49, None)))),
    (((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None))),
     ((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None)))),
    (((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None))),
     ((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None)))),
    (((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None))),
     ((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None)))),
    (((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None))),
     ((("idx", 50, None), ("idx_chance", 51, 75), ("idx", 52, None)))),
    (((("idx", 50, None), ("idx", 52, None), ("idx", 53, None))),
     ((("idx", 50, None), ("idx", 52, None), ("idx", 53, None)))),
    (((("idx_str_chance", 54, 25), ("idx", 55, None), ("idx", 56, None), ("idx", 57, None))),
     ((("idx_str_chance", 54, 25), ("idx", 55, None), ("idx", 56, None), ("idx", 57, None)))),
    (((("idx", 55, None), ("idx", 56, None), ("idx", 57, None))),
     ((("idx", 55, None), ("idx", 56, None), ("idx", 57, None)))),
)


@lru_cache(maxsize=1)
def _read_namechnk() -> bytes | None:
    """NAMECHNK.DAT を loose（ローカルの Arena データ）優先→ユーザー Arena install の VFS
    （GLOBAL.BSA・DAT 非暗号）の順で読む（公開版対応・無ければ None）。"""
    try:
        if os.path.isfile(_NAMECHNK_PATH):
            with open(_NAMECHNK_PATH, "rb") as f:
                return f.read()
    except OSError:
        pass
    try:
        from runtime_paths import install_vfs
        vfs = install_vfs()
        if vfs is not None:
            return vfs.read("NAMECHNK.DAT")
    except Exception:  # noqa: BLE001
        pass
    return None


def load_name_chunks() -> tuple[tuple[str, ...], ...]:
    data = _read_namechnk()
    if not data:
        return ()
    offset = 0
    chunks: list[tuple[str, ...]] = []
    while offset < len(data):
        chunk_length = int.from_bytes(data[offset:offset + 2], "little")
        string_count = data[offset + 2]
        string_offset = offset + 3
        strings: list[str] = []
        for _ in range(string_count):
            end = data.index(0, string_offset)
            strings.append(data[string_offset:end].decode("ascii", errors="replace"))
            string_offset = end + 1
        chunks.append(tuple(strings))
        offset += chunk_length
    return tuple(chunks)


def _pick_chunk(chunks: tuple[tuple[str, ...], ...], index: int,
                random: ArenaRandom) -> str:
    chunk = chunks[index]
    return chunk[random.next() % len(chunk)]


def generate_npc_name(race_id: int, is_male: bool, random: ArenaRandom) -> str:
    chunks = load_name_chunks()
    gender_index = 0 if is_male else 1
    rules = _RULES[race_id][gender_index]
    parts: list[str] = []
    for kind, value, chance in rules:
        if kind == "idx":
            parts.append(_pick_chunk(chunks, int(value), random))
        elif kind == "str":
            parts.append(str(value))
        elif kind == "idx_chance":
            if (random.next() % 100) <= int(chance):
                parts.append(_pick_chunk(chunks, int(value), random))
        elif kind == "idx_str_chance":
            if (random.next() % 100) <= int(chance):
                parts.append(_pick_chunk(chunks, int(value), random) + " ")
        else:
            raise ValueError(f"unknown name rule: {kind}")
    return "".join(parts)
