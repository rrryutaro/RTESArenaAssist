from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from .arena_city_utils import CityBlockEntry, expand_city_plan_with_random, imperial_tavern_random, premade_city_entries
from .arena_level_utils import MENU_MIF_PREFIXES
from .arena_location_utils import CENTER_PROVINCE_CITY_MIF_NAME, get_city_reserved_block_list_index, get_city_starting_position_index, get_city_template_count, get_city_template_name_index, get_global_city_id, get_ruler_seed, is_premade_city
from .arena_random import ArenaRandom
from .arena_types import ArenaCityType, ArenaLocationType, Int2, Rect
from .city_data import LocationData, is_data_available, is_world_map_available, load_city_generation_data, load_world_map_data
from .city_facility_detector import FacilityPlacement, detect_city_facilities
_CITY_TYPE_KEY = {ArenaLocationType.CITY_STATE: 'city_state', ArenaLocationType.TOWN: 'town', ArenaLocationType.VILLAGE: 'village'}
_CITY_TYPE_ENUM = {ArenaLocationType.CITY_STATE: ArenaCityType.CITY_STATE, ArenaLocationType.TOWN: ArenaCityType.TOWN, ArenaLocationType.VILLAGE: ArenaCityType.VILLAGE}
_CITY_DIM = {ArenaLocationType.CITY_STATE: 6, ArenaLocationType.TOWN: 5, ArenaLocationType.VILLAGE: 4}

def _location_type_from_id(location_id: int) -> Optional[ArenaLocationType]:
    if 0 <= location_id < 8:
        return ArenaLocationType.CITY_STATE
    if 8 <= location_id < 16:
        return ArenaLocationType.TOWN
    if 16 <= location_id < 32:
        return ArenaLocationType.VILLAGE
    return None

@dataclass(frozen=True)
class CityPlan:
    name: str
    location_type: ArenaLocationType
    province_id: int
    global_city_id: int
    coastal: bool
    city_seed: int
    premade: bool
    base_mif_name: str
    city_dim: int
    start_position: tuple[int, int]
    entries: tuple[CityBlockEntry, ...]
    random_after_plan: Optional[ArenaRandom]

def resolve_city_plan(province_id: int, location_id: int) -> Optional[CityPlan]:
    if not (is_data_available() and is_world_map_available()):
        return None
    location_type = _location_type_from_id(location_id)
    if location_type is None:
        return None
    world_map = load_world_map_data()
    if province_id < 0 or province_id >= len(world_map.provinces):
        return None
    province = world_map.provinces[province_id]
    location = province.get_location(location_id)
    if location is None or not location.name:
        return None
    city_gen = load_city_generation_data()
    global_city_id = get_global_city_id(location_id, province_id)
    is_coastal = city_gen.is_coastal(global_city_id)
    city_seed = location.city_seed()
    city_dim = _CITY_DIM[location_type]
    premade = is_premade_city(location_id, province_id)
    if premade:
        base_mif_name = CENTER_PROVINCE_CITY_MIF_NAME
        entries = premade_city_entries(base_mif_name)
        start_pos = (0, 0)
        random_after = imperial_tavern_random(city_seed)
    else:
        is_city_state = location_type == ArenaLocationType.CITY_STATE
        template_count = get_city_template_count(is_coastal, is_city_state)
        template_id = global_city_id % template_count
        template_name_index = get_city_template_name_index(location_type, is_coastal)
        template_pattern = city_gen.get_template_filename(template_name_index)
        if not template_pattern:
            return None
        base_mif_name = template_pattern.replace('%d', str(template_id + 1)).upper()
        rb_idx = get_city_reserved_block_list_index(is_coastal, template_id)
        sp_idx = get_city_starting_position_index(location_type, is_coastal, template_id)
        reserved = city_gen.get_reserved_block_list(rb_idx) or []
        start_pos = city_gen.get_starting_position(sp_idx) or (0, 0)
        entries, random_after = expand_city_plan_with_random(city_seed, city_dim, reserved)
    return CityPlan(name=location.name, location_type=location_type, province_id=province_id, global_city_id=global_city_id, coastal=is_coastal, city_seed=city_seed, premade=premade, base_mif_name=base_mif_name, city_dim=city_dim, start_position=(int(start_pos[0]), int(start_pos[1])), entries=tuple(entries), random_after_plan=random_after)

def get_facilities_for(province_id: int, location_id: int) -> Optional[list[FacilityPlacement]]:
    plan = resolve_city_plan(province_id, location_id)
    if plan is None:
        return None
    return detect_city_facilities(entries=plan.entries, city_seed=plan.city_seed, start_position=plan.start_position, city_type=_CITY_TYPE_ENUM[plan.location_type], city_type_key=_CITY_TYPE_KEY[plan.location_type], province_id=plan.province_id, coastal=plan.coastal, random_after_plan=plan.random_after_plan, global_city_id=plan.global_city_id)

class _CityDoorsUnavailable(Exception):
    pass

@lru_cache(maxsize=32)
def _get_city_doors_cached(province_id: int, location_id: int) -> tuple:
    plan = resolve_city_plan(province_id, location_id)
    if plan is None:
        raise _CityDoorsUnavailable
    from .city_door_detector import detect_city_doors
    from .city_voxel_assembler import build_city_voxel_grid
    grid = build_city_voxel_grid(plan)
    if grid is None:
        raise _CityDoorsUnavailable
    return tuple(detect_city_doors(grid.map1, grid.placements))

def get_city_doors_for(province_id: int, location_id: int) -> Optional[list]:
    try:
        return list(_get_city_doors_cached(province_id, location_id))
    except _CityDoorsUnavailable:
        return None

def get_city_doors_by_location_name(location_name: str) -> Optional[list]:
    if not is_world_map_available():
        return None
    world_map = load_world_map_data()
    found = world_map.find_location_by_name(location_name)
    if found is None:
        return None
    province_id, location_id, _ = found
    return get_city_doors_for(province_id, location_id)

def get_city_type_and_ruler_seed(location_name: str):
    if not is_world_map_available():
        return None
    world_map = load_world_map_data()
    found = world_map.find_location_by_name(location_name)
    if found is None:
        return None
    province_id, location_id, location = found
    location_type = _location_type_from_id(location_id)
    if location_type is None:
        return None
    province = world_map.provinces[province_id]
    rect = Rect(province.global_x, province.global_y, province.global_w, province.global_h)
    ruler_seed = get_ruler_seed(Int2(location.x, location.y), rect)
    return (_CITY_TYPE_ENUM[location_type], ruler_seed)

def get_facilities_by_location_name(location_name: str) -> Optional[list[FacilityPlacement]]:
    if not is_world_map_available():
        return None
    world_map = load_world_map_data()
    found = world_map.find_location_by_name(location_name)
    if found is None:
        return None
    province_id, location_id, _ = found
    return get_facilities_for(province_id, location_id)

def get_palace_mif_for_location(location_name: str) -> Optional[str]:
    if not is_world_map_available():
        return None
    world_map = load_world_map_data()
    found = world_map.find_location_by_name(location_name)
    if found is None:
        return None
    province_id, location_id, location = found
    location_type = _location_type_from_id(location_id)
    if location_type is None:
        return None
    province = world_map.provinces[province_id]
    rect = Rect(province.global_x, province.global_y, province.global_w, province.global_h)
    ruler_seed = get_ruler_seed(Int2(location.x, location.y), rect)
    variant = (ruler_seed >> 8 & 65535) % 3
    prefix_index = {ArenaLocationType.CITY_STATE: 0, ArenaLocationType.TOWN: 8, ArenaLocationType.VILLAGE: 9}[location_type]
    return f'{MENU_MIF_PREFIXES[prefix_index]}{variant + 1}.MIF'

def find_nearest_facility(facilities: list[FacilityPlacement], x: int, y: int) -> Optional[FacilityPlacement]:
    best: Optional[FacilityPlacement] = None
    best_d2 = -1
    for f in facilities:
        if f.mif_name is None:
            continue
        dx = f.original_x - x
        dy = f.original_y - y
        d2 = dx * dx + dy * dy
        if best is None or d2 < best_d2:
            best = f
            best_d2 = d2
    return best

def find_facility_by_mif_and_pos(facilities: list[FacilityPlacement], mif_name: str, door_x: int, door_y: int) -> Optional[FacilityPlacement]:
    candidates = [f for f in facilities if f.mif_name == mif_name]
    if not candidates:
        return None
    return find_nearest_facility(candidates, door_x, door_y)
