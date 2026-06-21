"""arena_city_utils.py — 街内 building plan の生成 (citySeed → BlockType 配列)。

OpenTESArena `World/ArenaCityUtils.cpp::generateCity` の **plan 構築部分のみ**
を Python 移植。city block MIF ファイル本体のロードは含めず、各 plan_index に
対する BlockType (Equipment/Tavern/Temple 等) と各 block の MIF 名 (TVBD5A.MIF
等) を決定するロジックに絞る。

Interior MIF 名 (TAVERN1.MIF 等) は arena_level_utils.get_door_voxel_mif_name
で別途計算する (door voxel 座標が必要)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .arena_random import ArenaRandom
from .mif_utils import (
    BlockType, generate_random_block_type, make_city_block_mif_name_from_block,
)


@dataclass
class CityBlockEntry:
    """街内 plan の 1 セル分のエントリ。"""
    plan_index: int            # 0 〜 city_dim*city_dim - 1
    x_dim:      int            # 街グリッド上の X インデックス
    z_dim:      int            # 街グリッド上の Z インデックス
    block_type: BlockType      # Empty / Reserved / Equipment / ...
    block_mif:  str | None     # city block MIF 名 (例 TVBD5A.MIF)、Reserved は None


def _place_block(plan: List[BlockType], city_size: int,
                 block_type: BlockType, random: ArenaRandom) -> int:
    """plan 内の Empty スロットに block_type を配置し、その plan_index を返す。

    OpenTESArena placeBlock:
        do { planIndex = random.next() % citySize; }
        while (plan[planIndex] != Empty);
        plan[planIndex] = blockType;
    """
    while True:
        plan_index = random.next() % city_size
        if plan[plan_index] == BlockType.EMPTY:
            plan[plan_index] = block_type
            return plan_index


def generate_city_plan(city_seed: int, city_dim: int,
                       reserved_blocks: List[int],
                       random: ArenaRandom | None = None) -> List[BlockType]:
    """citySeed と街サイズから街内 plan (BlockType 配列) を構築する。

    Args:
        city_seed:       街シード値 (= (location.x << 16) | location.y)
        city_dim:        街の grid 辺長 (citySize = city_dim * city_dim)
        reserved_blocks: テンプレートで予約されている plan インデックスのリスト
        random:          ArenaRandom (None なら city_seed で初期化)

    Returns:
        plan: 長さ city_dim*city_dim の BlockType 配列
    """
    if random is None:
        random = ArenaRandom(city_seed)
    else:
        random.srand(city_seed)

    city_size = city_dim * city_dim
    plan: List[BlockType] = [BlockType.EMPTY] * city_size

    # 予約ブロック
    for rb in reserved_blocks:
        if 0 <= rb < city_size:
            plan[rb] = BlockType.RESERVED

    # 固定配置 (順序は OpenTESArena に一致)
    for bt in (BlockType.EQUIPMENT, BlockType.MAGES_GUILD,
               BlockType.NOBLE_HOUSE, BlockType.TEMPLE,
               BlockType.TAVERN, BlockType.SPACER):
        _place_block(plan, city_size, bt, random)

    # 残り Empty を random block type で埋める
    empty_count = plan.count(BlockType.EMPTY)
    for _ in range(empty_count):
        bt = generate_random_block_type(random)
        _place_block(plan, city_size, bt, random)

    return plan


def expand_city_plan(city_seed: int, city_dim: int,
                     reserved_blocks: List[int],
                     random: ArenaRandom | None = None
                     ) -> List[CityBlockEntry]:
    """plan を CityBlockEntry のリストに展開し、各 block の MIF 名も付与する。

    OpenTESArena generateCity の plan iteration 部分を移植。
    Reserved block は MIF を持たない (None)。
    """
    entries, _ = expand_city_plan_with_random(
        city_seed, city_dim, reserved_blocks, random)
    return entries


def expand_city_plan_with_random(
        city_seed: int, city_dim: int,
        reserved_blocks: List[int],
        random: ArenaRandom | None = None
        ) -> tuple[List[CityBlockEntry], ArenaRandom]:
    """expand_city_plan と同じだが、消費後の ArenaRandom も返す。

    Tavern 名生成は plan 構築 + MIF 名決定後の random 状態で行うため、
    呼び出し側で消費後の random が必要。
    """
    if random is None:
        random = ArenaRandom(city_seed)

    # plan 構築 (random を消費)
    plan = generate_city_plan(city_seed, city_dim, reserved_blocks, random)

    # plan を iterate して block MIF 名を決定する (random をさらに消費)
    entries: List[CityBlockEntry] = []
    x_dim = 0
    z_dim = 0
    for plan_index, bt in enumerate(plan):
        if bt == BlockType.RESERVED:
            entries.append(CityBlockEntry(
                plan_index=plan_index, x_dim=x_dim, z_dim=z_dim,
                block_type=bt, block_mif=None,
            ))
        else:
            block_mif = make_city_block_mif_name_from_block(bt, random)
            entries.append(CityBlockEntry(
                plan_index=plan_index, x_dim=x_dim, z_dim=z_dim,
                block_type=bt, block_mif=block_mif,
            ))
        x_dim += 1
        if x_dim == city_dim:
            x_dim = 0
            z_dim += 1
    return entries, random
