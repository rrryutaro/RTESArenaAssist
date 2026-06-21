from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from .arena_city_utils import CityBlockEntry
from .arena_level_utils import get_door_voxel_mif_name
from .arena_random import ArenaRandom
from .arena_types import ArenaCityType, ArenaMenuType
from .arena_voxel_utils import MapType
from .building_name_generator import (
    EquipmentName, generate_equipment_names, generate_tavern_names,
    generate_temple_names,
)
from .dynamic_translation import (
    BuildingTranslation, translate_equipment, translate_mages_guild,
    translate_tavern, translate_temple,
)
from .mif_utils import BlockType
from .npc_name_generator import generate_npc_name
from .mif_loader import DEFAULT_MIF_DIR
from .mif_file_parser import load_mif


_MIF_DIR = os.fspath(DEFAULT_MIF_DIR)

_SERVICE_MARKERS: dict[ArenaMenuType, int] = {
    ArenaMenuType.EQUIPMENT: 0x0606,
    ArenaMenuType.TAVERN: 0x0B0B,
    ArenaMenuType.TEMPLE: 0x1818,
    ArenaMenuType.MAGES_GUILD: 0x1111,
}

_MENU_IDS: dict[ArenaMenuType, int] = {
    ArenaMenuType.EQUIPMENT: 0,
    ArenaMenuType.TAVERN: 1,
    ArenaMenuType.MAGES_GUILD: 2,
    ArenaMenuType.TEMPLE: 3,
}


@dataclass(frozen=True)
class FacilityPlacement:
    menu_type: ArenaMenuType
    original_x: int
    original_y: int
    block_type: BlockType
    block_mif: str
    local_x: int
    local_y: int
    marker_voxel: int | None
    mif_name: str | None
    translation: BuildingTranslation


@dataclass(frozen=True)
class _MarkerHit:
    original_x: int
    original_y: int
    block_type: BlockType
    block_mif: str
    local_x: int
    local_y: int
    marker_voxel: int


@lru_cache(maxsize=256)
def _load_mif_cached(filename: str):
    return load_mif(os.path.join(_MIF_DIR, filename))


def _iter_marker_hits(entries: Iterable[CityBlockEntry],
                      start_position: tuple[int, int],
                      marker_voxel: int) -> list[_MarkerHit]:
    start_x, start_y = start_position
    hits: list[_MarkerHit] = []
    for entry in entries:
        if entry.block_mif is None:
            continue
        mif = _load_mif_cached(entry.block_mif)
        level = mif.levels[0]
        for local_y, row in enumerate(level.map1):
            for local_x, voxel in enumerate(row):
                if voxel != marker_voxel:
                    continue
                original_x = start_x + (entry.x_dim * 20) + local_x
                original_y = start_y + (entry.z_dim * 20) + local_y
                hits.append(_MarkerHit(
                    original_x=original_x,
                    original_y=original_y,
                    block_type=entry.block_type,
                    block_mif=entry.block_mif,
                    local_x=local_x,
                    local_y=local_y,
                    marker_voxel=marker_voxel,
                ))
    return sorted(hits, key=lambda hit: (hit.original_y, hit.original_x))


def _make_mif_name(hit: _MarkerHit, menu_type: ArenaMenuType,
                   city_type: ArenaCityType) -> str | None:
    return get_door_voxel_mif_name(
        x=hit.original_x,
        y=hit.original_y,
        menu_id=_MENU_IDS[menu_type],
        ruler_seed=0,
        palace_is_main_quest_dungeon=False,
        city_type=city_type,
        map_type=MapType.CITY,
    )


def _equipment_with_names(city_seed: int, hits: list[_MarkerHit],
                          city_type_key: str | None,
                          city_type: ArenaCityType,
                          race_id: int) -> list[FacilityPlacement]:
    names = generate_equipment_names(city_seed, len(hits))
    result: list[FacilityPlacement] = []
    for hit, name in zip(hits, names):
        ef_rng = ArenaRandom((hit.original_y << 16) + hit.original_x)
        n_rng = ArenaRandom((hit.original_x << 16) + hit.original_y)
        ef_name = generate_npc_name(race_id, True, ef_rng).split()[0]
        n_name = generate_npc_name(race_id, True, n_rng)
        named = EquipmentName(
            prefix_index=name.prefix_index,
            suffix_index=name.suffix_index,
            ef_name=ef_name,
            n_name=n_name,
        )
        result.append(FacilityPlacement(
            menu_type=ArenaMenuType.EQUIPMENT,
            original_x=hit.original_x,
            original_y=hit.original_y,
            block_type=hit.block_type,
            block_mif=hit.block_mif,
            local_x=hit.local_x,
            local_y=hit.local_y,
            marker_voxel=hit.marker_voxel,
            mif_name=_make_mif_name(hit, ArenaMenuType.EQUIPMENT, city_type),
            translation=translate_equipment(named, city_type_key),
        ))
    return result


def detect_city_facilities(entries: list[CityBlockEntry], city_seed: int,
                           start_position: tuple[int, int],
                           city_type: ArenaCityType,
                           city_type_key: str | None,
                           province_id: int,
                           coastal: bool,
                           random_after_plan: ArenaRandom
                           ) -> list[FacilityPlacement]:
    result: list[FacilityPlacement] = []

    tavern_hits = _iter_marker_hits(
        entries, start_position, _SERVICE_MARKERS[ArenaMenuType.TAVERN])
    tavern_rng = ArenaRandom(random_after_plan.get_seed())
    for hit, name in zip(tavern_hits, generate_tavern_names(tavern_rng, len(tavern_hits), coastal)):
        result.append(FacilityPlacement(
            menu_type=ArenaMenuType.TAVERN,
            original_x=hit.original_x,
            original_y=hit.original_y,
            block_type=hit.block_type,
            block_mif=hit.block_mif,
            local_x=hit.local_x,
            local_y=hit.local_y,
            marker_voxel=hit.marker_voxel,
            mif_name=_make_mif_name(hit, ArenaMenuType.TAVERN, city_type),
            translation=translate_tavern(name),
        ))

    equipment_hits = _iter_marker_hits(
        entries, start_position, _SERVICE_MARKERS[ArenaMenuType.EQUIPMENT])
    result.extend(_equipment_with_names(
        city_seed, equipment_hits, city_type_key, city_type, province_id))

    temple_hits = _iter_marker_hits(
        entries, start_position, _SERVICE_MARKERS[ArenaMenuType.TEMPLE])
    for hit, name in zip(temple_hits, generate_temple_names(city_seed, len(temple_hits))):
        result.append(FacilityPlacement(
            menu_type=ArenaMenuType.TEMPLE,
            original_x=hit.original_x,
            original_y=hit.original_y,
            block_type=hit.block_type,
            block_mif=hit.block_mif,
            local_x=hit.local_x,
            local_y=hit.local_y,
            marker_voxel=hit.marker_voxel,
            mif_name=_make_mif_name(hit, ArenaMenuType.TEMPLE, city_type),
            translation=translate_temple(name),
        ))

    mages_hits = _iter_marker_hits(
        entries, start_position, _SERVICE_MARKERS[ArenaMenuType.MAGES_GUILD])
    for hit in mages_hits:
        result.append(FacilityPlacement(
            menu_type=ArenaMenuType.MAGES_GUILD,
            original_x=hit.original_x,
            original_y=hit.original_y,
            block_type=hit.block_type,
            block_mif=hit.block_mif,
            local_x=hit.local_x,
            local_y=hit.local_y,
            marker_voxel=hit.marker_voxel,
            mif_name=_make_mif_name(hit, ArenaMenuType.MAGES_GUILD, city_type),
            translation=translate_mages_guild(),
        ))

    order = {
        ArenaMenuType.EQUIPMENT: 0,
        ArenaMenuType.TAVERN: 1,
        ArenaMenuType.TEMPLE: 2,
        ArenaMenuType.MAGES_GUILD: 3,
    }
    return sorted(result, key=lambda item: (
        order.get(item.menu_type, 99),
        item.translation.en,
        item.original_y,
        item.original_x,
    ))


def count_by_menu_type(facilities: Iterable[FacilityPlacement]) -> dict[ArenaMenuType, int]:
    counts: dict[ArenaMenuType, int] = {}
    for facility in facilities:
        counts[facility.menu_type] = counts.get(facility.menu_type, 0) + 1
    return counts
