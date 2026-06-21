from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hierarchy_state import SeparationHierarchy
from session.session_base import SessionContext

TOP_LEVEL_STATES = ("pregame", "chargen", "normal-play")


@dataclass(frozen=True)
class TopLevelDispatchScope:

    state: str
    is_pregame: bool
    is_chargen: bool
    is_normal_play: bool


def current_state(w, default: str = "pregame") -> str:
    return getattr(w, "_top_level_state", default)


def dispatch_scope(w, default: str = "pregame") -> TopLevelDispatchScope:
    state = current_state(w, default=default)
    return TopLevelDispatchScope(
        state=state,
        is_pregame=(state == "pregame"),
        is_chargen=(state == "chargen"),
        is_normal_play=(state == "normal-play"),
    )


def build_session_context(
    w,
    *,
    img_name: Optional[str] = None,
    screen_id: Optional[str] = None,
    top_level_state: Optional[str] = None,
    in_interior: Optional[bool] = None,
    npc_phase: Optional[int] = None,
    npc_active: Optional[bool] = None,
    c_area: Optional[str] = None,
    mif_name: Optional[str] = None,
    interior_mif_name: Optional[str] = None,
    facility_kind: Optional[str] = None,
    hierarchy: Optional[SeparationHierarchy] = None,
    extras: Optional[dict] = None,
) -> SessionContext:
    resolved_top = (
        top_level_state if top_level_state is not None else current_state(w))
    resolved_interior = bool(
        in_interior if in_interior is not None
        else getattr(w, "_in_interior", False))
    resolved_npc_phase = (
        npc_phase if npc_phase is not None else getattr(w, "_npc_phase", None))
    resolved_hierarchy = (
        hierarchy if hierarchy is not None
        else SeparationHierarchy.from_window(
            w,
            top_level_state=resolved_top,
            in_interior=resolved_interior,
            npc_active=npc_active,
            c_area=c_area,
        )
    )
    return SessionContext(
        analyzer=getattr(w, "_analyzer", None),
        anchor=getattr(w, "_anchor", 0),
        img_name=(img_name if img_name is not None
                  else getattr(w, "_img_name_prev", "")),
        screen_id=(screen_id if screen_id is not None
                   else getattr(w, "_screen_id_prev", "")),
        top_level_state=resolved_top,
        in_interior=resolved_interior,
        npc_phase=resolved_npc_phase,
        mif_name=(mif_name if mif_name is not None
                  else getattr(w, "_active_mif", "")),
        interior_mif_name=(
            interior_mif_name if interior_mif_name is not None
            else getattr(w, "_interior_mif_name", None)),
        facility_kind=(facility_kind if facility_kind is not None else ""),
        hierarchy=resolved_hierarchy,
        extras=(extras if extras is not None else {"window": w}),
    )


__all__ = [
    "TopLevelDispatchScope",
    "build_session_context",
    "current_state",
    "dispatch_scope",
    "TOP_LEVEL_STATES",
]
