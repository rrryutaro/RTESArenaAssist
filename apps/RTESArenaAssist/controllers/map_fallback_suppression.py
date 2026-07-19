from __future__ import annotations

def clear_city_load_fallback_suppression(w) -> None:
    w._v1927_city_load_fallback_pending = False
    w._v1927_city_load_fallback_active = False
    w._v1927_city_load_fallback_origin = None

def arm_city_load_fallback_suppression(w) -> None:
    clear_city_load_fallback_suppression(w)

def city_load_fallback_suppression(w, *, area: str | None, coord_source: str, player_x, player_y, surface_owner: str, is_loading: bool=False) -> tuple[bool, str]:
    _ = (area, coord_source, player_x, player_y, surface_owner, is_loading)
    clear_city_load_fallback_suppression(w)
    return (False, '')
