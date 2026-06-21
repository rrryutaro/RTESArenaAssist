from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, Enum


class ArenaMenuType(Enum):

    NONE        = "None"
    CITY_GATES  = "CityGates"
    CRYPT       = "Crypt"
    DUNGEON     = "Dungeon"
    EQUIPMENT   = "Equipment"
    HOUSE       = "House"
    MAGES_GUILD = "MagesGuild"
    NOBLE       = "Noble"
    PALACE      = "Palace"
    TAVERN      = "Tavern"
    TEMPLE      = "Temple"
    TOWER       = "Tower"


class ArenaLocationType(Enum):
    CITY_STATE       = "CityState"
    TOWN             = "Town"
    VILLAGE          = "Village"
    STAFF_DUNGEON    = "StaffDungeon"
    STAFF_MAP_DUNGEON = "StaffMapDungeon"
    NAMED_DUNGEON    = "NamedDungeon"


class ArenaCityType(Enum):
    CITY_STATE = "CityState"
    TOWN       = "Town"
    VILLAGE    = "Village"


class ArenaClimateType(IntEnum):
    TEMPERATE = 0
    DESERT    = 1
    MOUNTAIN  = 2


@dataclass(frozen=True)
class Int2:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    left:   int
    top:    int
    width:  int
    height: int

    def right(self) -> int:
        return self.left + self.width

    def bottom(self) -> int:
        return self.top + self.height
