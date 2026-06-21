from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from services.mif_loader import DEFAULT_INF_DIR, parse_inf_wall_texture_names

EDGE_FENCE = "fence"
EDGE_HEDGE = "hedge"
EDGE_GARDEN = "garden"

_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("fence",), EDGE_FENCE),
    (("hedge",), EDGE_HEDGE),
    (("garden",), EDGE_GARDEN),
)

CROP_CORN = "corn"
CROP_FARM = "farm"
_CROP_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("corn",), CROP_CORN),
)

_WILD_INF_CANDIDATES = ("TWN.INF", "MWN.INF", "DWN.INF")


def classify_wall_name(name: str) -> Optional[str]:
    low = name.lower()
    for needles, cat in _NAME_RULES:
        if any(n in low for n in needles):
            return cat
    return None


def build_edge_category_map(inf_path: str | Path) -> dict[int, str]:
    cat_map: dict[int, str] = {}
    for idx, name in parse_inf_wall_texture_names(inf_path).items():
        cat = classify_wall_name(name)
        if cat is not None:
            cat_map[idx] = cat
    return cat_map


_cached_category_map: Optional[dict[int, str]] = None


def get_wild_edge_category_map() -> dict[int, str]:
    global _cached_category_map
    if _cached_category_map is not None:
        return _cached_category_map
    cat_map: dict[int, str] = {}
    for name in _WILD_INF_CANDIDATES:
        path = DEFAULT_INF_DIR / name
        if path.is_file():
            cat_map = build_edge_category_map(path)
            if cat_map:
                break
    _cached_category_map = cat_map
    return cat_map


def classify_crop_name(name: str) -> Optional[str]:
    low = name.lower()
    if "dfarm" in low:
        return None
    for needles, cat in _CROP_NAME_RULES:
        if any(n in low for n in needles):
            return cat
    return None


def build_crop_category_map(inf_path: str | Path) -> dict[int, str]:
    cat_map: dict[int, str] = {}
    for idx, name in parse_inf_wall_texture_names(inf_path).items():
        cat = classify_crop_name(name)
        if cat is not None:
            cat_map[idx] = cat
    return cat_map


_cached_crop_map: Optional[dict[int, str]] = None


def get_wild_crop_category_map() -> dict[int, str]:
    global _cached_crop_map
    if _cached_crop_map is not None:
        return _cached_crop_map
    cat_map: dict[int, str] = {}
    for name in _WILD_INF_CANDIDATES:
        path = DEFAULT_INF_DIR / name
        if path.is_file():
            cat_map = build_crop_category_map(path)
            if cat_map:
                break
    _cached_crop_map = cat_map
    return cat_map


def _wall_texture_index(v: int) -> Optional[int]:
    if v == 0:
        return None
    if (v & 0x8000) == 0:
        return None
    high = (v >> 12) & 0x0F
    if high == 0x9:
        return (v & 0x00FF) - 1
    if high == 0xA:
        return (v & 0x003F) - 1
    return None


def extract_edge_marks(
    map1: np.ndarray,
    category_map: dict[int, str],
) -> tuple[tuple[int, int, str], ...]:
    if not category_map:
        return ()
    ys, xs = np.where(map1 != 0)
    if not len(ys):
        return ()
    marks: list[tuple[int, int, str]] = []
    for y, x in zip(ys, xs):
        ti = _wall_texture_index(int(map1[y, x]))
        if ti is None:
            continue
        cat = category_map.get(ti)
        if cat is not None:
            marks.append((int(x), int(y), cat))
    return tuple(marks)


def extract_crop_marks(
    map1: np.ndarray,
    category_map: dict[int, str],
) -> tuple[tuple[int, int, str], ...]:
    return extract_edge_marks(map1, category_map)


__all__ = [
    "EDGE_FENCE", "EDGE_HEDGE", "EDGE_GARDEN",
    "CROP_CORN", "CROP_FARM",
    "classify_wall_name", "build_edge_category_map",
    "get_wild_edge_category_map", "extract_edge_marks",
    "classify_crop_name", "build_crop_category_map",
    "get_wild_crop_category_map", "extract_crop_marks",
]
