from __future__ import annotations
_FIELD_TEMPLE_MIF_PREFIX = 'TEMPLE'

def is_field_temple_interior(*, area: str, in_interior: bool, interior_mif_name: str) -> bool:
    return bool(in_interior) and (area or '') == 'wilderness' and (interior_mif_name or '').upper().startswith(_FIELD_TEMPLE_MIF_PREFIX)

def detect_field_temple_shop_state(analyzer, anchor, *, top_level_state: str, img_name: str, in_interior: bool, screen_id: str='', allow_yesno_menu_recovery: bool=False, interior_mif_name: str=''):
    from shop_popup_detector import detect_shop_popup_state
    state = detect_shop_popup_state(analyzer, anchor, top_level_state=top_level_state, img_name=img_name, in_interior=in_interior, screen_id=screen_id, allow_yesno_menu_recovery=allow_yesno_menu_recovery, interior_mif_name=interior_mif_name, active_facility_name='temple', area=None)
    if (state.owner_kind or '') != 'temple' and state.kind != 'none':
        state.reason = f'field_temple: non-temple result discarded (kind={state.kind} owner={state.owner_kind!r})'
        state.kind = 'none'
        state.owner_kind = ''
        state.menu_items = []
        state.menu_item_hotkeys = []
        state.menu_title_en = ''
    return state

def _store_latch(w, active: bool, prev: bool) -> None:
    w._field_temple_active_now = bool(active)
    w._field_temple_just_started = bool(active and (not prev))
    w._field_temple_just_stopped = bool(prev and (not active))

def poll_field_temple_session(w, ctx) -> None:
    sess = getattr(w, '_field_temple_session', None)
    prev = bool(sess is not None and sess.is_active())
    inside = is_field_temple_interior(area=getattr(ctx, 'area', '') or '', in_interior=bool(getattr(ctx, 'in_interior', False)), interior_mif_name=getattr(ctx, 'interior_mif_name', '') or '')
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
        try:
            mgr_active = w._session_manager.active_session()
        except AttributeError:
            mgr_active = None
        if mgr_active is None:
            sess.try_start(ctx)
    _store_latch(w, sess.is_active(), prev)

def poll_field_temple_render(w, *, shop_state=None, shop_img_name: str='', foreground_ptr=None):
    w._facility_story_kind_now = ''
    w._facility_story_ptr_now = foreground_ptr
    w._equipment_reply_polled_in_render = False
    w._equipment_reply_handled_in_render = False
    w._mages_reply_polled_in_render = False
    w._mages_reply_handled_in_render = False
    from normal_play.normal_play_render import _poll_compute_temple_gate
    _poll_compute_temple_gate(w, _temple_active_now=True)
    from session.temple_node import TEMPLE_NODE
    view = TEMPLE_NODE.classify_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
    return TEMPLE_NODE.render(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name)
__all__ = ['is_field_temple_interior', 'detect_field_temple_shop_state', 'poll_field_temple_session', 'poll_field_temple_render']
