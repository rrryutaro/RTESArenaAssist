from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional


_log = logging.getLogger("wild_block_lists")


@dataclass(frozen=True)
class WildBlockLists:
    normal: tuple[int, ...]
    village: tuple[int, ...]
    dungeon: tuple[int, ...]
    tavern: tuple[int, ...]
    temple: tuple[int, ...]


_FALLBACK_LISTS = WildBlockLists(
    normal=tuple(),
    village=tuple(),
    dungeon=tuple(),
    tavern=tuple(),
    temple=tuple(),
)


_CACHED: Optional[WildBlockLists] = None
_CACHE_SOURCE: Optional[str] = None


def _is_plausible_list(data: bytes, offset: int,
                       expected_size: int) -> bool:
    if offset + 1 + expected_size > len(data):
        return False
    if data[offset] != expected_size:
        return False
    ids = data[offset + 1:offset + 1 + expected_size]
    if not all(1 <= b <= 70 for b in ids):
        return False
    return True


def search_block_lists_in_buffer(buf: bytes) -> Optional[WildBlockLists]:
    NORMAL_SIZE = 24
    VILLAGE_SIZE = 12
    DUNGEON_SIZE = 12
    TAVERN_SIZE = 10
    TEMPLE_MIN = 1
    TEMPLE_MAX = 30

    n = len(buf)
    if n < 64:
        return None

    end = n - (1 + NORMAL_SIZE + 1 + VILLAGE_SIZE + 1 + DUNGEON_SIZE
               + 1 + TAVERN_SIZE + 1 + TEMPLE_MIN)
    for off in range(end):
        if buf[off] != NORMAL_SIZE:
            continue
        if not _is_plausible_list(buf, off, NORMAL_SIZE):
            continue
        p = off + 1 + NORMAL_SIZE
        if not _is_plausible_list(buf, p, VILLAGE_SIZE):
            continue
        p += 1 + VILLAGE_SIZE
        if not _is_plausible_list(buf, p, DUNGEON_SIZE):
            continue
        p += 1 + DUNGEON_SIZE
        if not _is_plausible_list(buf, p, TAVERN_SIZE):
            continue
        p += 1 + TAVERN_SIZE
        if p >= n:
            continue
        temple_size = buf[p]
        if not (TEMPLE_MIN <= temple_size <= TEMPLE_MAX):
            continue
        if not _is_plausible_list(buf, p, temple_size):
            continue

        normal = tuple(buf[off + 1:off + 1 + NORMAL_SIZE])
        vp = off + 1 + NORMAL_SIZE
        village = tuple(buf[vp + 1:vp + 1 + VILLAGE_SIZE])
        dp = vp + 1 + VILLAGE_SIZE
        dungeon = tuple(buf[dp + 1:dp + 1 + DUNGEON_SIZE])
        tp = dp + 1 + DUNGEON_SIZE
        tavern = tuple(buf[tp + 1:tp + 1 + TAVERN_SIZE])
        temple = tuple(buf[p + 1:p + 1 + temple_size])
        _log.info(
            "wild_block_lists: signature match at +0x%X "
            "(normal=%s village=%s dungeon=%s tavern=%s temple=%s)",
            off, list(normal), list(village), list(dungeon),
            list(tavern), list(temple))
        return WildBlockLists(
            normal=normal, village=village, dungeon=dungeon,
            tavern=tavern, temple=temple)
    return None


def load_block_lists_from_memory(
        analyzer,
        scan_start: int = 0x00000000,
        scan_end: int = 0x7FFFFFFF) -> Optional[WildBlockLists]:
    if analyzer is None:
        return None
    enum_func = getattr(analyzer, "_enum_readable_regions", None)
    if enum_func is None:
        _log.warning("analyzer has no _enum_readable_regions; skip search")
        return None

    try:
        regions = enum_func(scan_start, scan_end)
    except Exception:  # noqa: BLE001
        _log.exception("_enum_readable_regions failed")
        return None

    for base, size in regions:
        if size <= 0 or size > 0x10000000:
            continue
        try:
            data = analyzer.read_bytes(base, size)
        except OSError:
            continue
        result = search_block_lists_in_buffer(data)
        if result is not None:
            _log.info(
                "wild_block_lists: signature match in region "
                "base=0x%08X size=0x%X", base, size)
            return result
    _log.info("wild_block_lists: no signature match in any region")
    return None


def get_block_lists(analyzer=None) -> WildBlockLists:
    global _CACHED, _CACHE_SOURCE
    if _CACHED is not None:
        return _CACHED

    if analyzer is not None:
        try:
            result = load_block_lists_from_memory(analyzer)
        except Exception:  # noqa: BLE001
            _log.exception("load_block_lists_from_memory failed")
            result = None
        if result is not None:
            _CACHED = result
            _CACHE_SOURCE = "memory"
            return result

    _CACHED = _FALLBACK_LISTS
    _CACHE_SOURCE = "fallback"
    _log.warning(
        "wild_block_lists: using empty fallback (= memory search failed). "
        "wilderness map outside city center will be mostly empty until "
        "block lists are obtained.")
    return _CACHED


def get_cache_source() -> Optional[str]:
    return _CACHE_SOURCE


def invalidate_cache() -> None:
    global _CACHED, _CACHE_SOURCE
    _CACHED = None
    _CACHE_SOURCE = None


__all__ = [
    "WildBlockLists",
    "search_block_lists_in_buffer",
    "load_block_lists_from_memory",
    "get_block_lists",
    "get_cache_source",
    "invalidate_cache",
]
