from __future__ import annotations

from enum import IntEnum

from .arena_random import ArenaRandom


class BlockType(IntEnum):

    EMPTY       = 0
    RESERVED    = 1
    EQUIPMENT   = 2
    MAGES_GUILD = 3
    NOBLE_HOUSE = 4
    TEMPLE      = 5
    TAVERN      = 6
    SPACER      = 7
    HOUSES      = 8


CITY_BLOCK_CODES      = ["EQ", "MG", "NB", "TP", "TV", "TS", "BS"]
CITY_BLOCK_VARIATIONS = [13, 11, 10, 12, 15, 11, 20]
CITY_BLOCK_ROTATIONS  = ["A", "B", "C", "D"]


def get_city_block_code(index: int) -> str:
    return CITY_BLOCK_CODES[index]


def get_city_block_variations(index: int) -> int:
    return CITY_BLOCK_VARIATIONS[index]


def get_city_block_rotation(index: int) -> str:
    return CITY_BLOCK_ROTATIONS[index]


def make_city_block_mif_name(block_code: str, variation: int, rotation: str) -> str:
    return f"{block_code}BD{variation}{rotation}.MIF"


def make_city_block_mif_name_from_block(block_type: BlockType,
                                        random: ArenaRandom) -> str:
    block_index = int(block_type) - 2
    if block_index < 0 or block_index >= len(CITY_BLOCK_CODES):
        raise ValueError(f"invalid block_type for MIF generation: {block_type}")
    block_code = CITY_BLOCK_CODES[block_index]
    rotation_idx = random.next() % len(CITY_BLOCK_ROTATIONS)
    rotation = CITY_BLOCK_ROTATIONS[rotation_idx]
    variation_count = CITY_BLOCK_VARIATIONS[block_index]
    variation = max(random.next() % variation_count, 1)
    return make_city_block_mif_name(block_code, variation, rotation)


def generate_random_block_type(random: ArenaRandom) -> BlockType:
    rand_val = random.next()
    if rand_val <= 0x7333:
        return BlockType.HOUSES
    if rand_val <= 0xA666:
        return BlockType.TAVERN
    if rand_val <= 0xCCCC:
        return BlockType.EQUIPMENT
    if rand_val <= 0xE666:
        return BlockType.TEMPLE
    return BlockType.NOBLE_HOUSE
