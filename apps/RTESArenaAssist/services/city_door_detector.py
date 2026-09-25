from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Optional
from .arena_types import ArenaMenuType
from .mif_loader import DEFAULT_INF_DIR, parse_inf_menu_texture_map
_CITY_INF_CANDIDATES = ('TCN.INF', 'DCN.INF', 'MCN.INF')
_CITY_MENU_MAP_FALLBACK = {0: 5, 1: 10, 2: 16, 3: 23, 4: 30, 5: 35, 6: 40, 7: 44, 8: 45, 9: 53, 11: 51, 12: 52, 13: 50}
CITY_MENU_TYPES: dict[int, ArenaMenuType] = {0: ArenaMenuType.EQUIPMENT, 1: ArenaMenuType.TAVERN, 2: ArenaMenuType.MAGES_GUILD, 3: ArenaMenuType.TEMPLE, 4: ArenaMenuType.HOUSE, 5: ArenaMenuType.HOUSE, 6: ArenaMenuType.HOUSE, 7: ArenaMenuType.CITY_GATES, 8: ArenaMenuType.CITY_GATES, 9: ArenaMenuType.NOBLE, 11: ArenaMenuType.PALACE, 12: ArenaMenuType.PALACE, 13: ArenaMenuType.PALACE}

@dataclass(frozen=True)
class CityDoor:
    original_x: int
    original_y: int
    menu_id: int
    menu_type: ArenaMenuType
    block_mif: str
    local_x: int
    local_y: int

def voxel_texture_index(map1_voxel: int) -> Optional[int]:
    high_nibble = map1_voxel >> 12 & 15
    most = (map1_voxel & 32512) >> 8
    least = map1_voxel & 255
    if high_nibble == 8:
        return None
    if high_nibble == 9:
        return least - 1 if least else None
    if high_nibble == 10:
        edge = least & 63
        return edge - 1 if edge else None
    if high_nibble >= 8:
        return None
    if most != least or most == 0:
        return None
    return most - 1

@lru_cache(maxsize=1)
def city_menu_map() -> dict[int, int]:
    for name in _CITY_INF_CANDIDATES:
        menu_map = parse_inf_menu_texture_map(DEFAULT_INF_DIR / name)
        if menu_map:
            return menu_map
    return dict(_CITY_MENU_MAP_FALLBACK)

def texture_to_menu_id() -> dict[int, int]:
    return {tex: mid for mid, tex in city_menu_map().items()}

def _placement_at(placements: Iterable, x: int, y: int):
    for placement in reversed(tuple(placements)):
        if placement.original_x <= x < placement.original_x + placement.width and placement.original_y <= y < placement.original_y + placement.depth:
            return placement
    return None

def detect_city_doors(map1, placements: Iterable) -> list[CityDoor]:
    tex_to_menu = texture_to_menu_id()
    doors: list[CityDoor] = []
    sources = tuple(placements)
    depth, width = map1.shape
    for y in range(depth):
        for x in range(width):
            tex = voxel_texture_index(int(map1[y, x]))
            if tex is None:
                continue
            menu_id = tex_to_menu.get(tex)
            if menu_id is None:
                continue
            menu_type = CITY_MENU_TYPES.get(menu_id)
            if menu_type is None:
                continue
            placement = _placement_at(sources, x, y)
            if placement is None:
                continue
            doors.append(CityDoor(original_x=x, original_y=y, menu_id=menu_id, menu_type=menu_type, block_mif=placement.mif_name, local_x=x - placement.original_x, local_y=y - placement.original_y))
    return sorted(doors, key=lambda d: (d.original_y, d.original_x))

def door_at(doors: Iterable[CityDoor], x: int, y: int, max_d2: int=2) -> Optional[CityDoor]:
    best: Optional[CityDoor] = None
    best_d2 = -1
    for d in doors:
        dx = d.original_x - x
        dy = d.original_y - y
        d2 = dx * dx + dy * dy
        if d2 > max_d2:
            continue
        if best is None or d2 < best_d2:
            best = d
            best_d2 = d2
    return best
__all__ = ['CityDoor', 'CITY_MENU_TYPES', 'city_menu_map', 'texture_to_menu_id', 'voxel_texture_index', 'detect_city_doors', 'door_at']
