from __future__ import annotations
from typing import Optional
from .arena_types import ArenaCityType, ArenaMenuType
from .arena_voxel_utils import MapType, get_menu_type
from .bytes_utils import ror16
NO_INDEX = -1
MENU_MIF_MAPPINGS: dict[ArenaMenuType, int] = {ArenaMenuType.CITY_GATES: NO_INDEX, ArenaMenuType.CRYPT: 7, ArenaMenuType.DUNGEON: NO_INDEX, ArenaMenuType.EQUIPMENT: 5, ArenaMenuType.HOUSE: 1, ArenaMenuType.MAGES_GUILD: 6, ArenaMenuType.NOBLE: 2, ArenaMenuType.NONE: NO_INDEX, ArenaMenuType.PALACE: 0, ArenaMenuType.TAVERN: 3, ArenaMenuType.TEMPLE: 4, ArenaMenuType.TOWER: 10}
MENU_MIF_PREFIXES = ['PALACE', 'BS', 'NOBLE', 'TAVERN', 'TEMPLE', 'EQUIP', 'MAGE', 'WCRYPT', 'TOWNPAL', 'VILPAL', 'TOWER']

def get_door_voxel_offset(x: int, y: int) -> int:
    return ((y & 255) << 8) + ((x & 255) << 1)

def get_door_voxel_mif_name(x: int, y: int, menu_id: int, ruler_seed: int, palace_is_main_quest_dungeon: bool, city_type: ArenaCityType, map_type: MapType) -> Optional[str]:
    menu_type = get_menu_type(menu_id, map_type)
    is_final_dungeon_entrance = palace_is_main_quest_dungeon and menu_type == ArenaMenuType.PALACE
    if is_final_dungeon_entrance:
        return None
    prefix_index = MENU_MIF_MAPPINGS.get(menu_type, NO_INDEX)
    if prefix_index == NO_INDEX:
        return None
    if menu_type == ArenaMenuType.PALACE:
        if city_type == ArenaCityType.CITY_STATE:
            prefix_index = 0
        elif city_type == ArenaCityType.TOWN:
            prefix_index = 8
        elif city_type == ArenaCityType.VILLAGE:
            prefix_index = 9
        else:
            raise ValueError(f'invalid city_type: {city_type}')
    prefix = MENU_MIF_PREFIXES[prefix_index]
    is_palace = menu_type == ArenaMenuType.PALACE
    if is_palace:
        variant_id = (ruler_seed >> 8 & 65535) % 3
    else:
        offset = get_door_voxel_offset(x, y)
        variant_id = (ror16(offset, 4) ^ offset) % 8
    return f'{prefix}{variant_id + 1}.MIF'

def calc_mif_variant(x: int, y: int, is_palace: bool=False, ruler_seed: int=0) -> int:
    if is_palace:
        return (ruler_seed >> 8 & 65535) % 3
    offset = get_door_voxel_offset(x, y)
    return (ror16(offset, 4) ^ offset) % 8
