from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


DIALOG_IMGS_FOR_MAP: frozenset = frozenset({
    "YESNO.IMG",
    "NEGOTBUT.IMG",
    "NEWPOP.IMG",
    "POPUP11.IMG",
    "FACES00.CIF",
})

OWNER_FACILITY_OR_NEGOT: frozenset = frozenset({
    "tavern_yesno",
    "tavern_rumor_type",
    "tavern_negotiation",
    "negotiation",
    "shop_menu",
    "shop_rumor_type",
    "shop_buy",
    "shop_rooms",
})

INVALID_HELD_COORDS: frozenset = frozenset({
    (0, 0),
    (3, 3),
})


@dataclass
class MapSafeCoord:
    source: str
    player_x: Optional[int]
    player_y: Optional[int]
    angle_deg: Optional[float]
    unsafe_reasons: list = field(default_factory=list)


_NPC_PHASE_IDLE = 0x00


def compute_map_safe_coord(
    *,
    img_name: str,
    npc_phase: Optional[int],
    is_building_entry_msg: bool,
    facility_active: bool,
    owner: str,
    raw_x: Optional[int],
    raw_y: Optional[int],
    raw_angle: Optional[float],
    last_x: Optional[int],
    last_y: Optional[int],
    last_angle: Optional[float],
    npc_phase_idle_value: int = _NPC_PHASE_IDLE,
) -> MapSafeCoord:
    img_upper = (img_name or "").upper()

    unsafe_reasons: list = []
    if is_building_entry_msg:
        unsafe_reasons.append("building_entry")
    if npc_phase is not None and npc_phase != npc_phase_idle_value:
        unsafe_reasons.append("npc_phase_non_idle")
    if img_upper in DIALOG_IMGS_FOR_MAP:
        unsafe_reasons.append(f"dialog_img={img_upper}")
    if facility_active:
        unsafe_reasons.append("facility_active")
    if owner in OWNER_FACILITY_OR_NEGOT:
        unsafe_reasons.append(f"owner={owner}")

    if unsafe_reasons:
        last_pair = (
            (last_x, last_y)
            if last_x is not None and last_y is not None
            else None
        )
        if last_pair is not None and last_pair not in INVALID_HELD_COORDS:
            return MapSafeCoord(
                source="held",
                player_x=last_x,
                player_y=last_y,
                angle_deg=last_angle,
                unsafe_reasons=unsafe_reasons,
            )
        return MapSafeCoord(
            source="none",
            player_x=None,
            player_y=None,
            angle_deg=None,
            unsafe_reasons=unsafe_reasons,
        )
    return MapSafeCoord(
        source="raw",
        player_x=raw_x,
        player_y=raw_y,
        angle_deg=raw_angle,
        unsafe_reasons=[],
    )


__all__ = [
    "MapSafeCoord",
    "compute_map_safe_coord",
    "DIALOG_IMGS_FOR_MAP",
    "INVALID_HELD_COORDS",
    "OWNER_FACILITY_OR_NEGOT",
]
