"""arena_level_utils.py — door 位置 → Interior MIF 名導出。

OpenTESArena `World/ArenaLevelUtils.cpp::getDoorVoxelMifName` を Python 移植。
入力 (door voxel 座標 x, y) + menu_id + ruler_seed + cityType + mapType から
Interior MIF ファイル名 (TAVERN1.MIF など) を計算する。
"""
from __future__ import annotations

from typing import Optional

from .arena_types import ArenaCityType, ArenaMenuType
from .arena_voxel_utils import MapType, get_menu_type
from .bytes_utils import ror16


# menuType → MIF prefix index
# 街路の MENU voxel から導出される 12 種の menuType 対 menuMifPrefix インデックス
# (OpenTESArena `MenuMifMappings` 表)
NO_INDEX = -1
MENU_MIF_MAPPINGS: dict[ArenaMenuType, int] = {
    ArenaMenuType.CITY_GATES:  NO_INDEX,
    ArenaMenuType.CRYPT:       7,
    ArenaMenuType.DUNGEON:     NO_INDEX,
    ArenaMenuType.EQUIPMENT:   5,
    ArenaMenuType.HOUSE:       1,
    ArenaMenuType.MAGES_GUILD: 6,
    ArenaMenuType.NOBLE:       2,
    ArenaMenuType.NONE:        NO_INDEX,
    ArenaMenuType.PALACE:      0,   # cityType 別に 0/8/9 で再分岐
    ArenaMenuType.TAVERN:      3,
    ArenaMenuType.TEMPLE:      4,
    ArenaMenuType.TOWER:       10,
}


# menuMifPrefixes 配列の中身。OpenTESArena は ExeData から動的に取得するが、
# 値そのものは A.EXE 内に固定で、外部抽出済 (apps/RTESArenaAssist/aexe_strings.json
# など) と整合する。
# OpenTESArena の menuMifPrefixes と一致。
MENU_MIF_PREFIXES = [
    "PALACE",   # 0: City state Palace
    "BS",       # 1: House
    "NOBLE",    # 2: Noble
    "TAVERN",   # 3: Tavern
    "TEMPLE",   # 4: Temple
    "EQUIP",    # 5: Equipment
    "MAGE",     # 6: MagesGuild
    "WCRYPT",   # 7: Crypt
    "TOWNPAL",  # 8: Town Palace
    "VILPAL",   # 9: Village Palace
    "TOWER",    # 10: Tower
]


def get_door_voxel_offset(x: int, y: int) -> int:
    """door voxel 座標 → variant 計算用 offset。

    OpenTESArena: `(y << 8) + (x << 1)`
    """
    return ((y & 0xFF) << 8) + ((x & 0xFF) << 1)


def get_door_voxel_mif_name(
    x: int, y: int, menu_id: int, ruler_seed: int,
    palace_is_main_quest_dungeon: bool, city_type: ArenaCityType,
    map_type: MapType,
) -> Optional[str]:
    """door voxel 座標から Interior MIF ファイル名を導出する。

    Args:
        x: door voxel の WEInt (west-east)
        y: door voxel の SNInt (south-north)
        menu_id: 街マップの MENU voxel ID (0〜13)
        ruler_seed: getRulerSeed で計算済の値
        palace_is_main_quest_dungeon: 中央 province の最終ダンジョン入口なら True
        city_type: CityState / Town / Village
        map_type: City / Wilderness

    Returns:
        "TAVERN8.MIF" 等の文字列。
        identifier が CityGates / None / Dungeon の場合は None (MIF なし)。
        中央 province の最終ダンジョン入口なら "IMPERIAL.MIF" 等の固定名 (要 ExeData)。
    """
    menu_type = get_menu_type(menu_id, map_type)

    is_final_dungeon_entrance = (palace_is_main_quest_dungeon
                                 and menu_type == ArenaMenuType.PALACE)
    if is_final_dungeon_entrance:
        # 中央 province の最終ダンジョンは固定 MIF 名 (要 ExeData の
        # finalDungeonMifName)。本ツールではプレースホルダ。
        return None

    prefix_index = MENU_MIF_MAPPINGS.get(menu_type, NO_INDEX)
    if prefix_index == NO_INDEX:
        return None

    # Palace は cityType ごとに別 prefix
    if menu_type == ArenaMenuType.PALACE:
        if city_type == ArenaCityType.CITY_STATE:
            prefix_index = 0
        elif city_type == ArenaCityType.TOWN:
            prefix_index = 8
        elif city_type == ArenaCityType.VILLAGE:
            prefix_index = 9
        else:
            raise ValueError(f"invalid city_type: {city_type}")

    prefix = MENU_MIF_PREFIXES[prefix_index]

    is_palace = (menu_type == ArenaMenuType.PALACE)
    if is_palace:
        variant_id = ((ruler_seed >> 8) & 0xFFFF) % 3
    else:
        offset = get_door_voxel_offset(x, y)
        variant_id = (ror16(offset, 4) ^ offset) % 8

    return f"{prefix}{variant_id + 1}.MIF"


def calc_mif_variant(x: int, y: int, is_palace: bool = False,
                     ruler_seed: int = 0) -> int:
    """door 位置から MIF variant (0-7、Palace は 0-2)。"""
    if is_palace:
        return ((ruler_seed >> 8) & 0xFFFF) % 3
    offset = get_door_voxel_offset(x, y)
    return (ror16(offset, 4) ^ offset) % 8
