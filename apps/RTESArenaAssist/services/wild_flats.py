"""services/wild_flats.py — フィールド(C3)の地物(flat)分類と抽出。

フィールドの木・茂み・岩・墓・廃墟などは RMD の MAP1 voxel（上位ニブル 0x8）に
flat として置かれている（`flat_index = 値 & 0x00FF`）。床上配置は FLOR 下位バイト
（`flat_index = 下位 − 1`）。flat_index を荒地 INF の @FLATS で引くと名前が分かり、
名前から種別（木/茂み/岩/墓/廃墟/巣穴/その他）に分類できる。

種別ごとの index は気候（TWN/MWN/DWN…）が変わっても安定（木の species 名は変わるが
「木」という種別は同じ）。そのため分類は名前の部分一致で行い、どの荒地 INF を使っても
同じ種別が得られる。正確な species 名（オーク/サボテン等）の表示が要る場合は現在気候の
INF を解決する（本モジュールは種別マークのみが目的なので canonical INF を使う）。

参照: OpenTESArena `MapGeneration::readArenaMAP1`（flatIndex = map1Voxel & 0x00FF）/
      `ArenaWildUtils::WILD_DEN_FLAT_INDEX = 37`。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from services.mif_loader import DEFAULT_INF_DIR, parse_inf_flats

# 種別キー（automap_canvas のマーク色・描画形状と対応）。
FLAT_TREE = "tree"
FLAT_BUSH = "bush"
FLAT_ROCK = "rock"
FLAT_GRAVE = "grave"
FLAT_RUIN = "ruin"
FLAT_DEN = "den"
FLAT_OTHER = "other"

# 名前部分一致 → 種別（先頭から順に評価）。全気候の species を含める。
_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("fir", "oak", "pine", "cactus", "palm"), FLAT_TREE),
    (("bush", "weed"), FLAT_BUSH),
    (("rock", "bouldr"), FLAT_ROCK),
    (("grave",), FLAT_GRAVE),
    (("ruins", "column", "altar", "bones"), FLAT_RUIN),
    (("dent",), FLAT_DEN),  # ndent = 巣穴（ダンジョン入口の可能性・別経路）
)

# OpenTESArena `ArenaWildUtils::WILD_DEN_FLAT_INDEX`。名前解決前でも den と分かる。
WILD_DEN_FLAT_INDEX = 37

# 荒地 INF（climate 違いでも種別は安定。canonical に TWN を使い、無ければ順に探す）。
_WILD_INF_CANDIDATES = ("TWN.INF", "TWR.INF", "MWN.INF", "DWN.INF")


def classify_flat_name(name: str) -> str:
    """flat ファイル名（例 'npine4.img'）を種別キーに分類する。"""
    low = name.lower()
    for needles, cat in _NAME_RULES:
        if any(n in low for n in needles):
            return cat
    return FLAT_OTHER


def build_flat_category_map(inf_path: str | Path) -> dict[int, str]:
    """荒地 INF の @FLATS を解析し `flat_index -> 種別キー` を返す。"""
    cat_map: dict[int, str] = {}
    for entry in parse_inf_flats(inf_path):
        cat_map[entry.index] = classify_flat_name(entry.name)
    # 名前が無くても den index は den 扱い（保険）。
    cat_map.setdefault(WILD_DEN_FLAT_INDEX, FLAT_DEN)
    return cat_map


_cached_category_map: Optional[dict[int, str]] = None


def get_wild_flat_category_map() -> dict[int, str]:
    """canonical 荒地 INF から種別写像を解決（モジュールキャッシュ）。"""
    global _cached_category_map
    if _cached_category_map is not None:
        return _cached_category_map
    cat_map: dict[int, str] = {}
    for name in _WILD_INF_CANDIDATES:
        path = DEFAULT_INF_DIR / name
        if path.is_file():
            cat_map = build_flat_category_map(path)
            if cat_map:
                break
    _cached_category_map = cat_map
    return cat_map


def extract_flat_marks(
    map1: np.ndarray,
    category_map: dict[int, str],
    flor: np.ndarray | None = None,
) -> tuple[tuple[int, int, str], ...]:
    """grid から地物マーク `(x, y, 種別キー)` のタプルを抽出する。

    MAP1: 上位ニブル 0x8 → flat_index = 値 & 0x00FF。
    FLOR: 下位バイト != 0 → flat_index = 下位 − 1（床上 flat、任意）。
    種別が解決できない index は FLAT_OTHER。
    """
    marks: list[tuple[int, int, str]] = []
    # MAP1 entity: 上位ニブル 0x8 → flat_index = 値 & 0x00FF。
    ys, xs = np.where((map1 & 0xF000) == 0x8000)
    if len(ys):
        idxs = (map1[ys, xs] & 0x00FF)
        marks.extend(
            (int(x), int(y), category_map.get(int(i), FLAT_OTHER))
            for x, y, i in zip(xs, ys, idxs))
    # FLOR flat: 下位バイト != 0 → flat_index = 下位 − 1（床上 flat、任意）。
    if flor is not None:
        lo = (flor & 0x00FF)
        fy, fx = np.where(lo > 0)
        if len(fy):
            fidx = lo[fy, fx] - 1
            marks.extend(
                (int(x), int(y), category_map.get(int(i), FLAT_OTHER))
                for x, y, i in zip(fx, fy, fidx))
    return tuple(marks)


__all__ = [
    "FLAT_TREE", "FLAT_BUSH", "FLAT_ROCK", "FLAT_GRAVE", "FLAT_RUIN",
    "FLAT_DEN", "FLAT_OTHER", "WILD_DEN_FLAT_INDEX",
    "classify_flat_name", "build_flat_category_map",
    "get_wild_flat_category_map", "extract_flat_marks",
]
