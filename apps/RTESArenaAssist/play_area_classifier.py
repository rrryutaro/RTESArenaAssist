from __future__ import annotations
from typing import Literal, Optional

import i18n_helper as _i18n


_WILDERNESS_FLAG_OFFSET = 0x4BD0

PlayArea = Literal["city", "dungeon", "wilderness", "unknown"]


def classify_play_area(mif_name: str | None) -> PlayArea:
    mu = (mif_name or "").upper()
    if not mu:
        return "unknown"
    if mu == "IMPERIAL.MIF" or mu.startswith(("CITY", "TOWN", "VILLAG")):
        return "city"
    if "WILD" in mu:
        return "wilderness"
    return "dungeon"


def detect_play_area(
    analyzer,
    anchor: Optional[int],
    mif_name: Optional[str],
) -> PlayArea:
    base = classify_play_area(mif_name)
    if base in ("city", "unknown"):
        if analyzer is not None and anchor is not None:
            try:
                raw = analyzer.read_bytes(anchor + _WILDERNESS_FLAG_OFFSET, 1)
                if raw and raw[0] == 0x01:
                    return "wilderness"
            except (OSError, AttributeError):
                pass
    return base


def resolve_in_interior(
    interior_flag: Optional[int],
    place_byte: Optional[int],
    mif_name: Optional[str],
) -> bool:
    raw = interior_flag is not None and interior_flag != 0
    if not raw:
        return False
    if place_byte in (0x00, 0x01) and classify_play_area(mif_name) != "dungeon":
        return False
    return True


def area_suffix_ja(area: PlayArea, player_floor: int = 0) -> str:
    if area == "dungeon":
        if player_floor > 0:
            return _i18n.tr("screen.area_suffix.dungeon", n=player_floor)
        return _i18n.tr("screen.area_suffix.dungeon_no_floor")
    return _i18n.tr(f"screen.area_suffix.{area}")
