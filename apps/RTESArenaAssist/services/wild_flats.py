from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
from services.mif_loader import DEFAULT_INF_DIR, parse_inf_flats
FLAT_TREE = 'tree'
FLAT_BUSH = 'bush'
FLAT_ROCK = 'rock'
FLAT_GRAVE = 'grave'
FLAT_RUIN = 'ruin'
FLAT_DEN = 'den'
FLAT_OTHER = 'other'
_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = ((('fir', 'oak', 'pine', 'cactus', 'palm'), FLAT_TREE), (('bush', 'weed'), FLAT_BUSH), (('rock', 'bouldr'), FLAT_ROCK), (('grave',), FLAT_GRAVE), (('ruins', 'column', 'altar', 'bones'), FLAT_RUIN), (('dent',), FLAT_DEN))
WILD_DEN_FLAT_INDEX = 37
_WILD_INF_CANDIDATES = ('TWN.INF', 'TWR.INF', 'MWN.INF', 'DWN.INF')
_CITY_INF_CANDIDATES = ('TCN.INF', 'MCN.INF', 'DCN.INF')

def classify_flat_name(name: str) -> str:
    low = name.lower()
    for needles, cat in _NAME_RULES:
        if any((n in low for n in needles)):
            return cat
    return FLAT_OTHER

def build_flat_category_map(inf_path: str | Path, *, exclude_items: bool=False) -> dict[int, str]:
    entries = parse_inf_flats(inf_path)
    if not entries:
        return {}
    cat_map: dict[int, str] = {}
    for entry in entries:
        if exclude_items and entry.item_number is not None:
            continue
        cat_map[entry.index] = classify_flat_name(entry.name)
    if not exclude_items:
        cat_map.setdefault(WILD_DEN_FLAT_INDEX, FLAT_DEN)
    return cat_map
_cached_category_map: Optional[dict[int, str]] = None
_cached_city_category_map: Optional[dict[int, str]] = None

def get_wild_flat_category_map() -> dict[int, str]:
    global _cached_category_map
    if _cached_category_map is not None:
        return _cached_category_map
    cat_map: dict[int, str] = {}
    for name in _WILD_INF_CANDIDATES:
        path = DEFAULT_INF_DIR / name
        cat_map = build_flat_category_map(path)
        if cat_map:
            break
    _cached_category_map = cat_map
    return cat_map

def get_city_flat_category_map() -> dict[int, str]:
    global _cached_city_category_map
    if _cached_city_category_map is not None:
        return _cached_city_category_map
    cat_map: dict[int, str] = {}
    for name in _CITY_INF_CANDIDATES:
        path = DEFAULT_INF_DIR / name
        cat_map = build_flat_category_map(path, exclude_items=True)
        if cat_map:
            break
    _cached_city_category_map = cat_map
    return cat_map

def extract_flat_marks(map1: np.ndarray, category_map: dict[int, str], flor: np.ndarray | None=None, *, skip_unmapped: bool=False) -> tuple[tuple[int, int, str], ...]:
    marks: list[tuple[int, int, str]] = []
    ys, xs = np.where(map1 & 61440 == 32768)
    if len(ys):
        idxs = map1[ys, xs] & 255
        marks.extend(((int(x), int(y), category_map.get(int(i), FLAT_OTHER)) for x, y, i in zip(xs, ys, idxs) if not (skip_unmapped and int(i) not in category_map)))
    if flor is not None:
        lo = flor & 255
        fy, fx = np.where(lo > 0)
        if len(fy):
            fidx = lo[fy, fx] - 1
            marks.extend(((int(x), int(y), category_map.get(int(i), FLAT_OTHER)) for x, y, i in zip(fx, fy, fidx) if not (skip_unmapped and int(i) not in category_map)))
    return tuple(marks)
__all__ = ['FLAT_TREE', 'FLAT_BUSH', 'FLAT_ROCK', 'FLAT_GRAVE', 'FLAT_RUIN', 'FLAT_DEN', 'FLAT_OTHER', 'WILD_DEN_FLAT_INDEX', 'classify_flat_name', 'build_flat_category_map', 'get_wild_flat_category_map', 'get_city_flat_category_map', 'extract_flat_marks']
