from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .arena_random import ArenaRandom

@dataclass(frozen=True)
class TavernName:
    prefix_index: int
    suffix_index: int
    coastal: bool

@dataclass(frozen=True)
class TempleName:
    model: int
    suffix_index: int

@dataclass(frozen=True)
class EquipmentName:
    prefix_index: int
    suffix_index: int
    ef_name: Optional[str] = None
    n_name: Optional[str] = None
TEMPLE_MODEL_SUFFIX_COUNTS = (5, 9, 10)
MAIN_QUEST_TEMPLE_OVERRIDES: dict[int, tuple[int, int, int]] = {2: (1, 7, 23), 224: (2, 8, 32)}

def apply_main_quest_temple_override(names: list[TempleName], *, global_city_id: int | None, first_temple_name_index: int) -> list[TempleName]:
    if global_city_id is None:
        return names
    override = MAIN_QUEST_TEMPLE_OVERRIDES.get(global_city_id)
    if override is None:
        return names
    model, suffix_index, menu_names_index = override
    ordinal = menu_names_index - first_temple_name_index
    if not 0 <= ordinal < len(names):
        return names
    out = list(names)
    out[ordinal] = TempleName(model, suffix_index)
    return out

def generate_tavern_names(random: ArenaRandom, block_count: int, coastal: bool) -> list[TavernName]:
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

def generate_equipment_names(city_seed: int, block_count: int) -> list[EquipmentName]:
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

def make_wild_chunk_name_seed(we: int, sn: int) -> int:
    return (sn & 65535) << 16 | we & 65535

def generate_wild_tavern_name_opentes(we: int, sn: int) -> TavernName:
    random = ArenaRandom(make_wild_chunk_name_seed(we, sn))
    prefix_index = random.next() % 23
    suffix_index = random.next() % 23
    return TavernName(prefix_index, suffix_index, coastal=False)

def generate_wild_temple_name_opentes(we: int, sn: int) -> TempleName:
    random = ArenaRandom(make_wild_chunk_name_seed(we, sn))
    model = random.next() % 3
    suffix_index = random.next() % TEMPLE_MODEL_SUFFIX_COUNTS[model]
    return TempleName(model, suffix_index)

def make_wild_temple_name_seed_calibrated(we: int, sn: int, wild_seed: int) -> int:
    return wild_seed + make_wild_chunk_name_seed(we, sn) & 4294967295

def generate_wild_temple_name_calibrated(we: int, sn: int, wild_seed: int) -> TempleName:
    seed = make_wild_temple_name_seed_calibrated(we, sn, wild_seed)
    random = ArenaRandom(seed)
    model = random.next() % 3
    suffix_index = random.next() % TEMPLE_MODEL_SUFFIX_COUNTS[model]
    return TempleName(model, suffix_index)
