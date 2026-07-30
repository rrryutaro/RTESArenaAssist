from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
from runtime_paths import resolve_arena_data_dir
try:
    from services.city_lookup import get_city_doors_by_location_name, get_city_type_and_ruler_seed, get_facilities_by_location_name
    from services.mif_loader import load_mif
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def is_available() -> bool:
    return _AVAILABLE

@dataclass(frozen=True)
class InteriorFacilityInfo:
    mif_name: str
    name_en: str
    name_ja: Optional[str]

def lookup_interior_facility(location_name: Optional[str], door_x: Optional[int], door_y: Optional[int]) -> Optional[InteriorFacilityInfo]:
    if not _AVAILABLE:
        return None
    if not location_name or door_x is None or door_y is None:
        return None
    door_x, door_y = (int(door_x), int(door_y))
    door = _resolve_entered_door(location_name, door_x, door_y)
    if door is None:
        return None
    mif_name = _mif_for_door(location_name, door) or ''
    if not mif_name:
        return None
    name_en, name_ja = _facility_name_at(location_name, door)
    return InteriorFacilityInfo(mif_name=mif_name, name_en=name_en, name_ja=name_ja)

def describe_entered_door(location_name: str, door_x: int, door_y: int) -> str:
    if not _AVAILABLE or not location_name:
        return 'unavailable'
    try:
        doors = get_city_doors_by_location_name(location_name)
    except Exception:
        return 'doors=error'
    if not doors:
        return 'doors=0'
    from services.city_door_detector import door_at
    hit = door_at(doors, int(door_x), int(door_y))
    if hit is not None:
        return 'doors=%d hit=(%d,%d) menu=%d %s' % (len(doors), hit.original_x, hit.original_y, hit.menu_id, hit.menu_type.value)
    best, best_d2 = (None, -1)
    for d in doors:
        d2 = (d.original_x - door_x) ** 2 + (d.original_y - door_y) ** 2
        if best is None or d2 < best_d2:
            best, best_d2 = (d, d2)
    return 'doors=%d hit=none nearest=(%d,%d) menu=%d %s d2=%d' % (len(doors), best.original_x, best.original_y, best.menu_id, best.menu_type.value, best_d2)

def _resolve_entered_door(location_name: str, door_x: int, door_y: int):
    try:
        doors = get_city_doors_by_location_name(location_name)
    except Exception:
        return None
    if not doors:
        return None
    from services.city_door_detector import door_at
    return door_at(doors, door_x, door_y)

def _mif_for_door(location_name: str, door) -> Optional[str]:
    from services.arena_level_utils import get_door_voxel_mif_name
    from services.arena_voxel_utils import MapType
    ct = get_city_type_and_ruler_seed(location_name)
    if ct is None:
        return None
    city_type, ruler_seed = ct
    return get_door_voxel_mif_name(x=door.original_x, y=door.original_y, menu_id=door.menu_id, ruler_seed=ruler_seed, palace_is_main_quest_dungeon=False, city_type=city_type, map_type=MapType.CITY)

def _facility_name_at(location_name: str, door) -> tuple[str, Optional[str]]:
    try:
        facilities = get_facilities_by_location_name(location_name)
    except Exception:
        return ('', None)
    for f in facilities or ():
        if f.original_x == door.original_x and f.original_y == door.original_y:
            tr = getattr(f, 'translation', None)
            return (tr.en or '' if tr is not None else '', tr.ja if tr is not None else None)
    return ('', None)

def lookup_interior_mif(location_name: Optional[str], door_x: Optional[int], door_y: Optional[int]) -> Optional[str]:
    info = lookup_interior_facility(location_name, door_x, door_y)
    if info is None or not info.mif_name:
        return None
    return info.mif_name
_MIF_LEVEL_COUNT_CACHE: dict[str, int] = {}

def _resolve_mif_dir() -> str:
    return os.fspath(resolve_arena_data_dir() / 'MIF')

def get_mif_level_count(mif_name: Optional[str]) -> Optional[int]:
    if not mif_name:
        return None
    cached = _MIF_LEVEL_COUNT_CACHE.get(mif_name)
    if cached is not None:
        return cached
    if not _AVAILABLE:
        return None
    try:
        mif = load_mif(mif_name, [_resolve_mif_dir()])
        if mif is None:
            return None
        count = int(mif.level_count) if mif.level_count else 1
        _MIF_LEVEL_COUNT_CACHE[mif_name] = count
        return count
    except Exception:
        return None
__all__ = ['InteriorFacilityInfo', 'is_available', 'lookup_interior_facility', 'lookup_interior_mif', 'get_mif_level_count']
