from __future__ import annotations

def is_field_temple_interior(*, area: str, in_interior: bool, l3_by_mif: bool) -> bool:
    return bool(in_interior) and (area or '') == 'wilderness' and bool(l3_by_mif)

def detect_field_temple_shop_state(analyzer, anchor, *, top_level_state: str, img_name: str, in_interior: bool, screen_id: str='', yesno_candidate_pointers: tuple=(), interior_mif_name: str=''):
    from shop_popup_detector import detect_shop_popup_state
    state = detect_shop_popup_state(analyzer, anchor, top_level_state=top_level_state, img_name=img_name, in_interior=in_interior, screen_id=screen_id, yesno_candidate_pointers=yesno_candidate_pointers, interior_mif_name=interior_mif_name, active_facility_name='temple', area=None)
    return state

def _store_latch(w, active: bool, prev: bool) -> None:
    w._field_temple_active_now = bool(active)
    w._field_temple_just_started = bool(active and (not prev))
    w._field_temple_just_stopped = bool(prev and (not active))

def stop_field_temple_session(w) -> bool:
    sess = getattr(w, '_field_temple_session', None)
    prev = bool(sess is not None and sess.is_active())
    if prev:
        sess.force_stop(None)
    _store_latch(w, False, prev)
    return prev

def poll_field_temple_session(w, ctx) -> None:
    sess = getattr(w, '_field_temple_session', None)
    prev = bool(sess is not None and sess.is_active())
    from l3_facility import l3_decided_by_mif
    inside = is_field_temple_interior(area=getattr(ctx, 'area', '') or '', in_interior=bool(getattr(ctx, 'in_interior', False)), l3_by_mif=l3_decided_by_mif(w))
    if not inside:
        if prev:
            sess.force_stop(ctx)
        _store_latch(w, False, prev)
        return
    if sess is None:
        from session.temple_session import TempleSession
        sess = TempleSession()
        w._field_temple_session = sess
    if sess.is_active():
        sess.try_stop(ctx)
    else:
        sess.try_start(ctx)
    _store_latch(w, sess.is_active(), prev)
__all__ = ['is_field_temple_interior', 'detect_field_temple_shop_state', 'poll_field_temple_session', 'stop_field_temple_session']
