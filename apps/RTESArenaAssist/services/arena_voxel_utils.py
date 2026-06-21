from __future__ import annotations

from enum import Enum

from .arena_types import ArenaMenuType


class MapType(Enum):
    INTERIOR  = "Interior"
    CITY      = "City"
    WILDERNESS = "Wilderness"


CITY_MENU_MAPPINGS: dict[int, ArenaMenuType] = {
    0:  ArenaMenuType.EQUIPMENT,
    1:  ArenaMenuType.TAVERN,
    2:  ArenaMenuType.MAGES_GUILD,
    3:  ArenaMenuType.TEMPLE,
    4:  ArenaMenuType.HOUSE,
    5:  ArenaMenuType.HOUSE,
    6:  ArenaMenuType.HOUSE,
    7:  ArenaMenuType.CITY_GATES,
    8:  ArenaMenuType.CITY_GATES,
    9:  ArenaMenuType.NOBLE,
    10: ArenaMenuType.NONE,
    11: ArenaMenuType.PALACE,
    12: ArenaMenuType.PALACE,
    13: ArenaMenuType.PALACE,
}

WILD_MENU_MAPPINGS: dict[int, ArenaMenuType] = {
    0: ArenaMenuType.NONE,
    1: ArenaMenuType.CRYPT,
    2: ArenaMenuType.HOUSE,
    3: ArenaMenuType.TAVERN,
    4: ArenaMenuType.TEMPLE,
    5: ArenaMenuType.TOWER,
    6: ArenaMenuType.CITY_GATES,
    7: ArenaMenuType.CITY_GATES,
    8: ArenaMenuType.DUNGEON,
    9: ArenaMenuType.DUNGEON,
}


def get_menu_type(menu_id: int, map_type: MapType) -> ArenaMenuType:
    if menu_id == -1:
        return ArenaMenuType.NONE
    if map_type == MapType.CITY:
        return CITY_MENU_MAPPINGS.get(menu_id, ArenaMenuType.NONE)
    if map_type == MapType.WILDERNESS:
        return WILD_MENU_MAPPINGS.get(menu_id, ArenaMenuType.NONE)
    raise ValueError(f"invalid map_type: {map_type}")


def menu_leads_to_interior(menu_type: ArenaMenuType) -> bool:
    return menu_type in {
        ArenaMenuType.CRYPT, ArenaMenuType.DUNGEON, ArenaMenuType.EQUIPMENT,
        ArenaMenuType.HOUSE, ArenaMenuType.MAGES_GUILD, ArenaMenuType.NOBLE,
        ArenaMenuType.PALACE, ArenaMenuType.TAVERN, ArenaMenuType.TEMPLE,
        ArenaMenuType.TOWER,
    }


def menu_has_display_name(menu_type: ArenaMenuType) -> bool:
    return menu_type in {
        ArenaMenuType.EQUIPMENT, ArenaMenuType.MAGES_GUILD,
        ArenaMenuType.TAVERN, ArenaMenuType.TEMPLE,
    }
