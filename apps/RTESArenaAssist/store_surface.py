from __future__ import annotations

def begin_poll(w) -> None:
    w._store_surface_prev = store_surface_now(w)
    w._store_menu_front = False
    w._store_list_fronts = []
    w._store_l4_surface_claimed = False

def publish_menu_front(w) -> None:
    w._store_menu_front = True

def publish_list_front(w, *, store_surface: bool) -> None:
    fronts = getattr(w, '_store_list_fronts', None)
    if fronts is None:
        fronts = []
        w._store_list_fronts = fronts
    fronts.append(bool(store_surface))

def publish_l4_surface_claim(w) -> None:
    w._store_l4_surface_claimed = True

def l4_surface_claimed(w) -> bool:
    return bool(getattr(w, '_store_l4_surface_claimed', False))

def store_surface_now(w) -> bool:
    fronts = getattr(w, '_store_list_fronts', None) or []
    if fronts:
        return any(fronts)
    return bool(getattr(w, '_store_menu_front', False))

def store_surface_prev(w) -> bool:
    return bool(getattr(w, '_store_surface_prev', False))
__all__ = ['begin_poll', 'l4_surface_claimed', 'publish_l4_surface_claim', 'publish_list_front', 'publish_menu_front', 'store_surface_now', 'store_surface_prev']
