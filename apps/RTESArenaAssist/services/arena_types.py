"""arena_types.py — Arena 関連の enum と基本データ型。

OpenTESArena `Assets/ArenaTypes.h` の enum を Python に移植する。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, Enum


class ArenaMenuType(Enum):
    """街マップの MENU voxel が指す building 種別。"""

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
    """2D 整数ベクトル (OpenTESArena Int2 相当)。"""
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    """矩形 (left, top, width, height)。"""
    left:   int
    top:    int
    width:  int
    height: int

    def right(self) -> int:
        return self.left + self.width

    def bottom(self) -> int:
        return self.top + self.height
