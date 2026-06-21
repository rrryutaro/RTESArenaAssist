"""services/wild_edges.py — フィールド(C3)のフェンス/生垣/庭の分類と抽出。

フェンス等は RMD の MAP1 に複数の voxel 種別で置かれている（実データ確認）:
  - transparent(上位ニブル 0x9): 透過壁。フェンスの**直線/枠の大多数**。
  - edge(上位ニブル 0xA): 縁 voxel。フェンスの一部（N/W facing のみ）。
  - その他の壁(wall/raised/diagonal)も texture が一致すれば対象。

「壁の輪郭(edge)だけ」を見ると transparent のフェンスを取りこぼし、壁色の塗り
ブロックのまま残る。そこで **voxel 種別ごとに正しい基準でテクスチャ index を引き**、
荒地 INF @WALLS 名で `twfence*`=フェンス・`tznhedge`=生垣・`tzgarden`=庭に分類する。

texture index（@FLOORS+@WALLS 連結の通し番号）は **voxel 種別で基準が違う**
（OpenTESArena `World/MapGeneration.cpp::writeVoxelInfoForMAP1` 準拠）:
  - solid wall(most==least, bit15=0): ((value >> 8) & 0xFF) - 1
  - transparent(0x9):                  (value & 0x00FF) - 1   ← 最下位バイト全体
  - edge(0xA):                         (value & 0x003F) - 1
  - raised(most!=least)=BOXSIDE 間接 / flat(0x8)/door(0xB)/none(0xC)/diagonal(0xD)
    は @WALLS 直 index ではないので対象外。
実機確認: 生垣は transparent `0x9031`＝(0x31)-1=48=tznhedge。most-1 で引くと 15
（フェンス域）と誤判定し、生垣を取りこぼす。

向き（縦/横/角）は facing ビットではなく **隣接フェンスセルとの接続**から描画側で
決める（直線・角・T字が自動で出る・x_flip 安全）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from services.mif_loader import DEFAULT_INF_DIR, parse_inf_wall_texture_names

# 区分キー（automap_canvas の線色と対応）。
EDGE_FENCE = "fence"
EDGE_HEDGE = "hedge"
EDGE_GARDEN = "garden"

# 名前部分一致 → 区分（先頭から順に評価）。
_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("fence",), EDGE_FENCE),
    (("hedge",), EDGE_HEDGE),
    (("garden",), EDGE_GARDEN),
)

# 作物（面で塗る・線でない）。トウモロコシ=edge(0xA) `twcorn`。
# ※ 畑(twfarm)は solid wall で、市街ブロックの建物壁が同じ texture index に当たると
#   建物を farm と誤検出する。畑の地面は FLOR の tznfield(floor_id 2)で
#   別途タイントするため、ここでは solid wall ベースの farm 検出を行わない。
CROP_CORN = "corn"
CROP_FARM = "farm"  # 互換のため定義のみ（検出ルールには含めない）
_CROP_NAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("corn",), CROP_CORN),
)

# 荒地 INF（climate 違いでも区分は概ね安定。canonical に TWN、無ければ順に探す）。
_WILD_INF_CANDIDATES = ("TWN.INF", "MWN.INF", "DWN.INF")


def classify_wall_name(name: str) -> Optional[str]:
    """壁テクスチャ名（例 'twfence1.set'）を区分キーに分類する（非該当は None）。"""
    low = name.lower()
    for needles, cat in _NAME_RULES:
        if any(n in low for n in needles):
            return cat
    return None


def build_edge_category_map(inf_path: str | Path) -> dict[int, str]:
    """荒地 INF の @WALLS を解析し `texture index -> 区分キー` を返す（該当のみ）。"""
    cat_map: dict[int, str] = {}
    for idx, name in parse_inf_wall_texture_names(inf_path).items():
        cat = classify_wall_name(name)
        if cat is not None:
            cat_map[idx] = cat
    return cat_map


_cached_category_map: Optional[dict[int, str]] = None


def get_wild_edge_category_map() -> dict[int, str]:
    """canonical 荒地 INF から区分写像を解決（モジュールキャッシュ）。"""
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
    """壁テクスチャ名を作物区分へ分類する（非該当は None）。

    `tzdfarm`（*MENU の農家入口・作物ではない）は除外する。
    """
    low = name.lower()
    if "dfarm" in low:        # 農家入口(menu)・作物ではない
        return None
    for needles, cat in _CROP_NAME_RULES:
        if any(n in low for n in needles):
            return cat
    return None


def build_crop_category_map(inf_path: str | Path) -> dict[int, str]:
    """荒地 INF の @WALLS を解析し `texture index -> 作物区分` を返す（該当のみ）。"""
    cat_map: dict[int, str] = {}
    for idx, name in parse_inf_wall_texture_names(inf_path).items():
        cat = classify_crop_name(name)
        if cat is not None:
            cat_map[idx] = cat
    return cat_map


_cached_crop_map: Optional[dict[int, str]] = None


def get_wild_crop_category_map() -> dict[int, str]:
    """canonical 荒地 INF から作物区分写像を解決（モジュールキャッシュ）。"""
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
    """edge/transparent voxel の @WALLS texture index を返す（対象外は None）。

    **solid wall(建物壁) は対象外**にする。フェンス/生垣/庭/トウモロコシは実データ上
    edge(0xA) か transparent(0x9) で置かれ、solid wall ではない。solid wall も拾うと、
    市街ブロックの建物壁が同じ index に当たった時に誤検出する。
    raised/flat/door/diagonal も @WALLS 直 index でないので対象外。
    """
    if v == 0:
        return None
    if (v & 0x8000) == 0:
        return None             # solid wall / raised（建物壁等）は対象外
    high = (v >> 12) & 0x0F
    if high == 0x9:             # transparent: 最下位バイト全体
        return (v & 0x00FF) - 1
    if high == 0xA:             # edge: 下位 6bit
        return (v & 0x003F) - 1
    return None                 # flat(0x8)/door(0xB)/none(0xC)/diagonal(0xD)


def extract_edge_marks(
    map1: np.ndarray,
    category_map: dict[int, str],
) -> tuple[tuple[int, int, str], ...]:
    """grid からフェンス/生垣/庭のセル `(x, z, 区分キー)` を抽出する。

    全 voxel 種別（edge/transparent/wall/raised/diagonal）を対象に、種別ごとの
    正しい基準で texture index を引いて区分へ写像する。flat/door は対象外。
    向きは持たない（描画側が隣接接続で直線/角を決める）。
    """
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
    """grid から作物セル `(x, z, 区分キー=corn/farm)` を抽出する。

    抽出ロジックは fence/hedge/garden と共通（voxel 種別ごとの texture index→区分）。
    描画は線でなく**面（セル塗り＋マーク）**で行う（呼び出し側が区別）。
    """
    return extract_edge_marks(map1, category_map)


__all__ = [
    "EDGE_FENCE", "EDGE_HEDGE", "EDGE_GARDEN",
    "CROP_CORN", "CROP_FARM",
    "classify_wall_name", "build_edge_category_map",
    "get_wild_edge_category_map", "extract_edge_marks",
    "classify_crop_name", "build_crop_category_map",
    "get_wild_crop_category_map", "extract_crop_marks",
]
