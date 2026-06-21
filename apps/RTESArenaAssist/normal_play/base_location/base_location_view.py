from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from play_area_classifier import detect_play_area


@dataclass(frozen=True)
class FieldEntranceContext:
    interior_mif_name: Optional[str] = None
    menu_label: str = ""
    name_en: str = ""
    name_ja: Optional[str] = None


_WILD_FIELD_FLAG = 0x01
_WILD_CRYPT_FLAG = 0x04


def resolve_field_facility_entry(
    hint: Optional[FieldEntranceContext],
    *,
    interior_flag_nonzero: bool,
    wild_flag: int,
) -> Tuple[bool, Optional[str], str]:
    if hint is None or not hint.interior_mif_name:
        return (False, None, "")
    if wild_flag == _WILD_CRYPT_FLAG:
        active = True
    elif interior_flag_nonzero and wild_flag != _WILD_FIELD_FLAG:
        active = True
    else:
        active = False
    if not active:
        return (False, None, "")
    return (True, hint.interior_mif_name, hint.menu_label or "")


_AREA_TO_L2 = {"dungeon": "C1", "city": "C2", "wilderness": "C3"}
_L2_TO_AREA = {v: k for k, v in _AREA_TO_L2.items()}

_INTERIOR_MIF_PREFIXES: Tuple[str, ...] = (
    "TAVERN", "TEMPLE", "EQUIP", "ARMORS", "MAGES", "MAGE",
    "PALACE", "NOBLE", "HOUSE",
)


def _looks_like_interior_mif(mif_name: Optional[str]) -> bool:
    u = (mif_name or "").upper()
    return any(u.startswith(p) for p in _INTERIOR_MIF_PREFIXES)


def classify_base_location(
    analyzer, anchor: Optional[int], mif_name: Optional[str]) -> str:
    return _AREA_TO_L2.get(detect_play_area(analyzer, anchor, mif_name), "")


def area_name(l2_code: str) -> str:
    return _L2_TO_AREA.get(l2_code or "", "")


def classify_map_axis(
    analyzer,
    anchor: Optional[int],
    *,
    mif_name: Optional[str],
    interior_mif_name: Optional[str],
    in_interior: Optional[bool] = None,
    area: Optional[str] = None,
) -> Optional[str]:
    if in_interior is None:
        from arena_bridge import read_interior_flag
        from play_area_classifier import (
            resolve_in_interior, _WILDERNESS_FLAG_OFFSET,
        )
        try:
            _place = analyzer.read_bytes(
                anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
        except (OSError, IndexError, AttributeError):
            _place = None
        in_interior = resolve_in_interior(
            read_interior_flag(analyzer, anchor), _place, mif_name)
    if in_interior and interior_mif_name:
        return "interior"
    if area is None:
        area = detect_play_area(analyzer, anchor, mif_name)
    if in_interior:
        return "dungeon" if area == "dungeon" else "interior"
    if area in _AREA_TO_L2:
        return area
    return None


def resolve_area_with_indoor_fallback(
    analyzer,
    anchor: Optional[int],
    mif_name: Optional[str],
    in_interior: bool,
    last_non_interior_area: str,
) -> Tuple[str, str]:
    if in_interior:
        if last_non_interior_area:
            return last_non_interior_area, last_non_interior_area
        area = detect_play_area(analyzer, anchor, mif_name)
        if area == "unknown" or (
                area == "dungeon" and _looks_like_interior_mif(mif_name)):
            return "city", last_non_interior_area
        return area, last_non_interior_area
    area = detect_play_area(analyzer, anchor, mif_name)
    if area in ("city", "wilderness", "dungeon"):
        return area, area
    return area, last_non_interior_area


__all__ = [
    "FieldEntranceContext",
    "resolve_field_facility_entry",
    "classify_base_location",
    "area_name",
    "classify_map_axis",
    "resolve_area_with_indoor_fallback",
]
