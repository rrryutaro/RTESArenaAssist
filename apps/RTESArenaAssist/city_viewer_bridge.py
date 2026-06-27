from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
from runtime_paths import resolve_arena_data_dir
try:
    from services.city_lookup import find_nearest_facility, get_facilities_by_location_name, get_palace_mif_for_location
    from services.mif_loader import load_mif
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
_FACILITY_MATCH_MAX_D2 = 100

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
    facilities = get_facilities_by_location_name(location_name)
    if not facilities:
        return None
    nearest = find_nearest_facility(facilities, int(door_x), int(door_y))
    if nearest is None:
        return None
    dx = nearest.original_x - int(door_x)
    dy = nearest.original_y - int(door_y)
    if dx * dx + dy * dy > _FACILITY_MATCH_MAX_D2:
        palace_mif = get_palace_mif_for_location(location_name)
        if palace_mif:
            return InteriorFacilityInfo(mif_name=palace_mif, name_en='', name_ja=None)
        return None
    mif_name = nearest.mif_name or ''
    tr = getattr(nearest, 'translation', None)
    name_en = tr.en or '' if tr is not None else ''
    name_ja = tr.ja if tr is not None else None
    return InteriorFacilityInfo(mif_name=mif_name, name_en=name_en, name_ja=name_ja)

def lookup_interior_mif(location_name: Optional[str], door_x: Optional[int], door_y: Optional[int]) -> Optional[str]:
    info = lookup_interior_facility(location_name, door_x, door_y)
    if info is None or not info.mif_name:
        return None
    return info.mif_name
_MIF_LEVEL_COUNT_CACHE: dict[str, int] = {}

def _resolve_mif_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(here, '..', '..'))
    candidates = [os.fspath(resolve_arena_data_dir() / 'MIF')]
    candidates.append(os.path.join(repo_root, 'docs', 'ARENA-data', 'MIF'))
    if '.claude' in repo_root:
        parts = repo_root.replace('\\', '/').split('/')
        if '.claude' in parts:
            idx = parts.index('.claude')
            main_root = '/'.join(parts[:idx]) if not parts[0].endswith(':') else parts[0] + '/' + '/'.join(parts[1:idx])
            candidates.append(os.path.normpath(os.path.join(main_root, 'docs', 'ARENA-data', 'MIF')))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]

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
