"""city_viewer_bridge.py — Assist 内 services/ の街名解決ロジック façade。

旧称は CityViewer への bridge だったが、現在は CityViewer 依存を全廃し、
ロジックは services/ 配下に移植済み。本ファイルは
旧 API (= lookup_interior_facility / lookup_interior_mif / get_mif_level_count)
を維持するための薄いラッパー。新規呼び出しは services を直接 import しても良い。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from runtime_paths import resolve_arena_data_dir

try:
    from services.city_lookup import (
        find_nearest_facility,
        get_facilities_by_location_name,
        get_palace_mif_for_location,
    )
    from services.mif_loader import load_mif
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


# 扉座標と施設マーカーの距離 (二乗) しきい値。実機観測 (Rihad) で
# 店扉=最寄り施設まで d2≈1、宮殿扉=最寄り施設まで d2≈1152 と桁違いに
# 分離できることを確認済み。d2 がこれを超える屋内は「施設ではない」
# (= 宮殿 / 貴族邸 / 家) と判定し、最寄り店への誤解決を防ぐ。
_FACILITY_MATCH_MAX_D2 = 100


def is_available() -> bool:
    return _AVAILABLE


@dataclass(frozen=True)
class InteriorFacilityInfo:
    """街内施設の MIF 名 + 固有名 (en/ja)。

    固有名が未登録 (= 貴族邸 / 家 等、施設名生成対象外) の場合は
    name_en="" / name_ja=None。呼び出し側は固有名の有無を見て表示形式を
    切り替える。
    """
    mif_name: str
    name_en: str
    name_ja: Optional[str]


def lookup_interior_facility(location_name: Optional[str],
                             door_x: Optional[int],
                             door_y: Optional[int]
                             ) -> Optional[InteriorFacilityInfo]:
    """街名 + 推定 door 座標から Interior MIF + 固有名を返す。

    場所/座標が取得できない / 該当施設が無い場合は None。
    Tavern / Temple / Equipment / Mages Guild は固有名が組み立てられるが、
    NOBLE / HOUSE / PALACE 等は施設一覧に含まれず None を返す
    (= 呼び出し側で MIF 名 prefix からの kind label にフォールバック)。
    """
    if not _AVAILABLE:
        return None
    if not location_name or door_x is None or door_y is None:
        return None
    facilities = get_facilities_by_location_name(location_name)
    if not facilities:
        return None
    nearest = find_nearest_facility(facilities, int(door_x), int(door_y))
    if nearest is None:
        return None

    # 扉が最寄り施設マーカーから遠い = 店ではない (宮殿 / 貴族邸 / 家)。
    # 最寄り店への誤解決を止め、宮殿なら cityType+rulerSeed から PALACE*.MIF を
    # 返してマップ描画・「宮殿」表示につなぐ。貴族邸/家は固有 MIF 導出を持たない
    # ため None (= 種別不明、誤った店名は出さない)。
    dx = nearest.original_x - int(door_x)
    dy = nearest.original_y - int(door_y)
    if dx * dx + dy * dy > _FACILITY_MATCH_MAX_D2:
        palace_mif = get_palace_mif_for_location(location_name)
        if palace_mif:
            return InteriorFacilityInfo(
                mif_name=palace_mif, name_en="", name_ja=None)
        return None

    mif_name = nearest.mif_name or ""
    tr = getattr(nearest, "translation", None)
    name_en = (tr.en or "") if tr is not None else ""
    name_ja = tr.ja if tr is not None else None
    return InteriorFacilityInfo(
        mif_name=mif_name,
        name_en=name_en,
        name_ja=name_ja,
    )


def lookup_interior_mif(location_name: Optional[str],
                        door_x: Optional[int],
                        door_y: Optional[int]
                        ) -> Optional[str]:
    """街名 + 推定 door 座標から Interior MIF 名を返す (= 後方互換 API)。"""
    info = lookup_interior_facility(location_name, door_x, door_y)
    if info is None or not info.mif_name:
        return None
    return info.mif_name


_MIF_LEVEL_COUNT_CACHE: dict[str, int] = {}


def _resolve_mif_dir() -> str:
    """ARENA-data/MIF ディレクトリを解決する (候補を順にフォールバック)。"""
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(here, "..", ".."))
    candidates = [os.fspath(resolve_arena_data_dir() / "MIF")]
    candidates.append(os.path.join(repo_root, "docs", "ARENA-data", "MIF"))
    if ".claude" in repo_root:
        parts = repo_root.replace("\\", "/").split("/")
        if ".claude" in parts:
            idx = parts.index(".claude")
            main_root = ("/".join(parts[:idx])
                         if not parts[0].endswith(":") else
                         parts[0] + "/" + "/".join(parts[1:idx]))
            candidates.append(os.path.normpath(os.path.join(
                main_root, "docs", "ARENA-data", "MIF")))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def get_mif_level_count(mif_name: Optional[str]) -> Optional[int]:
    """指定 MIF ファイルの level_count を返す (= 2 階建てなら 2、平屋なら 1)。"""
    if not mif_name:
        return None
    cached = _MIF_LEVEL_COUNT_CACHE.get(mif_name)
    if cached is not None:
        return cached
    if not _AVAILABLE:
        return None
    try:
        # loose（ARENA-data の MIF dir）優先→ユーザー Arena install の VFS
        # （GLOBAL.BSA 内 MIF は非暗号）fallback。`load_mif` が両者を解決するため、
        # loose 不在の公開版でも install VFS から level_count を得る。
        mif = load_mif(mif_name, [_resolve_mif_dir()])
        if mif is None:
            return None
        count = int(mif.level_count) if mif.level_count else 1
        _MIF_LEVEL_COUNT_CACHE[mif_name] = count
        return count
    except Exception:
        return None


__all__ = [
    "InteriorFacilityInfo",
    "is_available",
    "lookup_interior_facility",
    "lookup_interior_mif",
    "get_mif_level_count",
]
