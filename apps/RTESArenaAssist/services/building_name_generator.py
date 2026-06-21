"""building_name_generator.py — 街内 Tavern / Equipment / Temple の固有名を生成。

OpenTESArena `World/MapGeneration.cpp` の `generateNames` ロジック (行 1898-2093)
を Python 移植。citySeed-based RNG で prefix/suffix インデックスを順次決定し、
ハッシュ重複 (同 prefix-suffix 組) を避ける。

注意:
- 実機の MENU voxel 数 (= 実際に生成される件数) は city block MIF パースが
  必要 (Phase Z 領域)。本モジュールは呼び出し側から件数 (block_count) を
  受け取り、その数だけ名前を生成する。
- coastal フラグで Tavern の suffix テーブル切替。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .arena_random import ArenaRandom


@dataclass(frozen=True)
class TavernName:
    prefix_index: int     # 0-22
    suffix_index: int     # 0-22
    coastal:      bool


@dataclass(frozen=True)
class TempleName:
    model:        int     # 0-2 (0=Order of the / 1=Brotherhood of / 2=Conclave of)
    suffix_index: int     # 0-4 (model=0), 0-8 (model=1), 0-9 (model=2)


@dataclass(frozen=True)
class EquipmentName:
    prefix_index: int     # 0-19
    suffix_index: int     # 0-9
    ef_name: Optional[str] = None
    n_name: Optional[str] = None


# Temple の model ごとの suffix 件数 (OpenTESArena MapGeneration.cpp 行 2054)
TEMPLE_MODEL_SUFFIX_COUNTS = (5, 9, 10)


def generate_tavern_names(random: ArenaRandom, block_count: int,
                          coastal: bool) -> list[TavernName]:
    """街内 Tavern MENU 各個に対して prefix/suffix を順次生成する。

    Args:
        random:      generateCity 後の状態の ArenaRandom (Tavern 名生成は
                     再初期化せず、その状態を引き継ぐ)
        block_count: 生成する数 (実機の MENU voxel 数を渡す)
        coastal:     coastal=True なら tavernMarineSuffixes、False なら
                     tavernSuffixes を使う (両方とも 23 件なので generator
                     としては suffix_index 0-22 のまま)

    Returns:
        TavernName のリスト (long さ = block_count)
    """
    result: list[TavernName] = []
    seen: set[int] = set()
    for _ in range(block_count):
        while True:
            prefix_index = random.next() % 23
            suffix_index = random.next() % 23
            h = (prefix_index << 8) + suffix_index
            if h not in seen:
                seen.add(h)
                break
        result.append(TavernName(prefix_index, suffix_index, coastal))
    return result


def generate_equipment_names(city_seed: int, block_count: int
                             ) -> list[EquipmentName]:
    """街内 Equipment MENU 各個に対して prefix/suffix を順次生成する。

    OpenTESArena では Equipment は generateNames 開始時に
    `random.srand(citySeed)` で再初期化される (行 1903-1905)。
    """
    random = ArenaRandom(city_seed)
    result: list[EquipmentName] = []
    seen: set[int] = set()
    for _ in range(block_count):
        while True:
            prefix_index = random.next() % 20
            suffix_index = random.next() % 10
            h = (prefix_index << 8) + suffix_index
            if h not in seen:
                seen.add(h)
                break
        result.append(EquipmentName(prefix_index, suffix_index))
    return result


def generate_temple_names(city_seed: int, block_count: int) -> list[TempleName]:
    """街内 Temple MENU 各個に対して model/suffix を順次生成する。

    Equipment と同様、Temple も `random.srand(citySeed)` で再初期化される。
    model: 0-2 (3 種類の prefix)
    suffix_index: model に応じて 0-4 / 0-8 / 0-9
    """
    random = ArenaRandom(city_seed)
    result: list[TempleName] = []
    seen: set[int] = set()
    for _ in range(block_count):
        while True:
            model = random.next() % 3
            vars_count = TEMPLE_MODEL_SUFFIX_COUNTS[model]
            suffix_index = random.next() % vars_count
            h = (model << 8) + suffix_index
            if h not in seen:
                seen.add(h)
                break
        result.append(TempleName(model, suffix_index))
    return result


# ============================================================================
# フィールド(C3)建物の固有名生成
#   OpenTESArena 原典(忠実) と 実機観測ベースの仮説(calibrated) を分離する。
#   ※「現行実装＝OpenTESArena 完全再現」ではない。
#     OpenTESArena 原典手順では、同一チャンクの宿屋/神殿が同じ pure chunk seed から
#     種別ごとに再初期化されるが、観測ペア(宿屋 King's Skull / 神殿
#     Brotherhood of Mercy)を同時再現できない。正しい Arena 実機一般式は未確定。
# ============================================================================

# --- OpenTESArena 原典どおりの忠実実装(wildSeed は使わない) -----------------

def make_wild_chunk_name_seed(we: int, sn: int) -> int:
    """OpenTESArena 原典のフィールドチャンク命名シード。

    OpenTESArena `ArenaWildUtils::makeWildChunkSeed(wildX,wildY)=(wildY<<16)+wildX`
    を `makeWildChunkSeed(chunk.y=WE, chunk.x=SN)` で呼ぶため、仕様用語では
    `seed = (SN<<16)+WE`（we=東西チャンク列, sn=南北チャンク行）。**wildSeed は
    加算しない＝location 非依存**（出典: MapGeneration.cpp L2698-2711 /
    ArenaWildUtils.cpp L71-74）。
    """
    return ((sn & 0xFFFF) << 16) | (we & 0xFFFF)


def generate_wild_tavern_name_opentes(we: int, sn: int) -> TavernName:
    """フィールド宿屋1件の固有名を OpenTESArena 原典どおりに生成する。

    `ArenaRandom(makeWildChunkSeed)` で prefix%23 → suffix%23 を1件引く
    （種別ごとに fresh・重複回避ループ無し。出典 MapGeneration.cpp L2200-2204）。
    wild の宿屋 suffix は常に非marine表（coastal=False）。
    実機 Moonguard chunk(WE=31,SN=30) → (14,12) = "King's Skull"（実機一致）。
    """
    random = ArenaRandom(make_wild_chunk_name_seed(we, sn))
    prefix_index = random.next() % 23
    suffix_index = random.next() % 23
    return TavernName(prefix_index, suffix_index, coastal=False)


def generate_wild_temple_name_opentes(we: int, sn: int) -> TempleName:
    """フィールド神殿1件の固有名を OpenTESArena 原典どおりに生成する。

    `ArenaRandom(makeWildChunkSeed)` で model%3 → suffix%ModelVars[model] を1件引く
    （出典 MapGeneration.cpp L2206-2213）。
    **注意**: 実機 Moonguard chunk(WE=31,SN=30) では原典どおりだと (1,1)=
    "Brotherhood of Faith" になり、実機の "Brotherhood of Mercy"=(1,0) と一致しない
    （OpenTESArena 原典手順は本観測ペアを再現できない＝未解決）。
    """
    random = ArenaRandom(make_wild_chunk_name_seed(we, sn))
    model = random.next() % 3
    suffix_index = random.next() % TEMPLE_MODEL_SUFFIX_COUNTS[model]
    return TempleName(model, suffix_index)


# --- 実機観測ベースの仮説(OpenTESArena 原典ではない) --------------------

def make_wild_temple_name_seed_calibrated(we: int, sn: int,
                                          wild_seed: int) -> int:
    """【観測仮説・OpenTESArena 原典ではない】神殿名 calibrated シード。

    pure chunk seed に wildSeed を加算したもの。神殿1件の観測名
    (Brotherhood of Mercy) に合わせた仮説で、原典には無く、同じ式だと
    同一チャンクの宿屋は実機と一致しない。正しい一般式は未確定。
    """
    return (wild_seed + make_wild_chunk_name_seed(we, sn)) & 0xFFFFFFFF


def generate_wild_temple_name_calibrated(we: int, sn: int,
                                         wild_seed: int) -> TempleName:
    """【観測仮説・OpenTESArena 原典ではない】wildSeed 加算 seed で神殿名を生成。

    実機 Moonguard chunk(WE=31,SN=30)・wildSeed=0x6E6F6F4D → (1,0)=
    "Brotherhood of Mercy"（実機一致）。だが同式で宿屋は不一致。観測1件への
    対応であり、別神殿で追加検証が必要。
    """
    seed = make_wild_temple_name_seed_calibrated(we, sn, wild_seed)
    random = ArenaRandom(seed)
    model = random.next() % 3
    suffix_index = random.next() % TEMPLE_MODEL_SUFFIX_COUNTS[model]
    return TempleName(model, suffix_index)
