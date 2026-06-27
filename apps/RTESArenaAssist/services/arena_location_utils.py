from __future__ import annotations
from .arena_types import ArenaLocationType, Int2, Rect
from .bytes_utils import rol32, get_le32
CENTER_PROVINCE_ID = 8

def city_to_location_id(local_city_id: int) -> int:
    return local_city_id

def dungeon_to_location_id(local_dungeon_id: int) -> int:
    return local_dungeon_id + 32

def get_global_city_id(local_city_id: int, province_id: int) -> int:
    return (province_id << 5) + local_city_id

def get_local_city_and_province_id(global_city_id: int) -> tuple[int, int]:
    return (global_city_id & 31, global_city_id >> 5)

def get_city_type(local_city_id: int) -> ArenaLocationType:
    if local_city_id < 8:
        return ArenaLocationType.CITY_STATE
    if local_city_id < 16:
        return ArenaLocationType.TOWN
    if local_city_id < 32:
        return ArenaLocationType.VILLAGE
    raise ValueError(f'invalid local_city_id: {local_city_id}')

def get_dungeon_type(local_dungeon_id: int) -> ArenaLocationType:
    if local_dungeon_id == 0:
        return ArenaLocationType.STAFF_DUNGEON
    if local_dungeon_id == 1:
        return ArenaLocationType.STAFF_MAP_DUNGEON
    return ArenaLocationType.NAMED_DUNGEON

def get_global_point(local_point: Int2, province_rect: Rect) -> Int2:
    global_x = local_point.x * (province_rect.width * 100 // 320) // 100 + province_rect.left
    global_y = local_point.y * (province_rect.height * 100 // 200) // 100 + province_rect.top
    return Int2(global_x, global_y)

def get_local_point(global_point: Int2, province_rect: Rect) -> Int2:
    local_x = (global_point.x - province_rect.left) * 100 // (province_rect.width * 100 // 320)
    local_y = (global_point.y - province_rect.top) * 100 // (province_rect.height * 100 // 200)
    return Int2(local_x, local_y)

def get_local_city_point(city_seed: int) -> Int2:
    return Int2(city_seed >> 16, city_seed & 65535)

def get_city_seed(local_x: int, local_y: int) -> int:
    return (local_x & 65535) << 16 | local_y & 65535

def get_wilderness_seed(location_name: str) -> int:
    if len(location_name) < 4:
        return 0
    return get_le32(location_name[:4].encode('ascii', errors='replace'))

def get_ruler_seed(local_point: Int2, province_rect: Rect) -> int:
    global_point = get_global_point(local_point, province_rect)
    seed = (global_point.x & 65535) << 16 | global_point.y & 65535
    return rol32(seed, 16)

def get_sky_seed(local_point: Int2, province_id: int, province_rect: Rect) -> int:
    global_point = get_global_point(local_point, province_rect)
    seed = (global_point.x & 65535) << 16 | global_point.y & 65535
    return seed * province_id & 4294967295

def is_ruler_male(local_x: int, local_y: int, province_rect: Rect) -> bool:
    ruler_seed = get_ruler_seed(Int2(local_x, local_y), province_rect)
    return ruler_seed & 3 != 0

def get_city_template_count(is_coastal: bool, is_city_state: bool) -> int:
    if is_coastal:
        return 3 if is_city_state else 2
    return 5

def get_city_template_name_index(location_type: ArenaLocationType, is_coastal: bool) -> int:
    if location_type == ArenaLocationType.CITY_STATE:
        return 5 if is_coastal else 4
    if location_type == ArenaLocationType.TOWN:
        return 1 if is_coastal else 0
    if location_type == ArenaLocationType.VILLAGE:
        return 3 if is_coastal else 2
    raise ValueError(f'invalid location_type: {location_type}')

def get_city_starting_position_index(location_type: ArenaLocationType, is_coastal: bool, template_id: int) -> int:
    if location_type == ArenaLocationType.CITY_STATE:
        return (19 if is_coastal else 14) + template_id
    if location_type == ArenaLocationType.TOWN:
        return (5 if is_coastal else 0) + template_id
    if location_type == ArenaLocationType.VILLAGE:
        return (12 if is_coastal else 7) + template_id
    raise ValueError(f'invalid location_type: {location_type}')

def get_city_reserved_block_list_index(is_coastal: bool, template_id: int) -> int:
    return (5 if is_coastal else 0) + template_id
