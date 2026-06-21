from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .arena_random import ArenaRandom
from .mif_utils import (
    BlockType, generate_random_block_type, make_city_block_mif_name_from_block,
)


@dataclass
class CityBlockEntry:
    plan_index: int
    x_dim:      int
    z_dim:      int
    block_type: BlockType
    block_mif:  str | None


def _place_block(plan: List[BlockType], city_size: int,
                 block_type: BlockType, random: ArenaRandom) -> int:
    while True:
        plan_index = random.next() % city_size
        if plan[plan_index] == BlockType.EMPTY:
            plan[plan_index] = block_type
            return plan_index


def generate_city_plan(city_seed: int, city_dim: int,
                       reserved_blocks: List[int],
                       random: ArenaRandom | None = None) -> List[BlockType]:
    if random is None:
        random = ArenaRandom(city_seed)
    else:
        random.srand(city_seed)

    city_size = city_dim * city_dim
    plan: List[BlockType] = [BlockType.EMPTY] * city_size

    for rb in reserved_blocks:
        if 0 <= rb < city_size:
            plan[rb] = BlockType.RESERVED

    for bt in (BlockType.EQUIPMENT, BlockType.MAGES_GUILD,
               BlockType.NOBLE_HOUSE, BlockType.TEMPLE,
               BlockType.TAVERN, BlockType.SPACER):
        _place_block(plan, city_size, bt, random)

    empty_count = plan.count(BlockType.EMPTY)
    for _ in range(empty_count):
        bt = generate_random_block_type(random)
        _place_block(plan, city_size, bt, random)

    return plan


def expand_city_plan(city_seed: int, city_dim: int,
                     reserved_blocks: List[int],
                     random: ArenaRandom | None = None
                     ) -> List[CityBlockEntry]:
    entries, _ = expand_city_plan_with_random(
        city_seed, city_dim, reserved_blocks, random)
    return entries


def expand_city_plan_with_random(
        city_seed: int, city_dim: int,
        reserved_blocks: List[int],
        random: ArenaRandom | None = None
        ) -> tuple[List[CityBlockEntry], ArenaRandom]:
    if random is None:
        random = ArenaRandom(city_seed)

    plan = generate_city_plan(city_seed, city_dim, reserved_blocks, random)

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
