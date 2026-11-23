from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
_TAVERN_VIEW_DESC_OFFSET = 36718
_TAVERN_VIEW_FLAG_OFFSET = 36724

def log_tavern_view_diagnostics(w, *, view, shop_state, img: str) -> None:
    is_ctx = (getattr(w, '_l3_facility', '') or '') == 'tavern'
    if not (is_ctx or getattr(w, '_tavern_view_dbg_prev_ctx', False)):
        return
    sub_key = getattr(view, 'bar_key', '') or ''
    own_kind, _own_title, own = ('none', '', False)
    if shop_state is not None:
        try:
            from session.tavern_signals import tavern_surface_of
            own_kind, _own_title, own = tavern_surface_of(w, shop_state)
        except Exception:
            own_kind, own = ('none', False)
    from active_template_reader import surface_kind_of_pointer
    from session.tavern_signals import input_prompt_label, signal_template_table
    _table = signal_template_table()
    surface = surface_kind_of_pointer(getattr(w, '_active_tmpl_selected_ptr_prev', None), _table)
    owner = getattr(w, '_panel_owner', '') or ''
    cands = ''
    try:
        from active_template_reader import read_active_template_candidates as _ratc, template_surface_kind as _tsk
        descs = []
        for c in _ratc(w._analyzer, w._anchor):
            ck = _tsk(c, _table) or ''
            cf = input_prompt_label(c)
            if ck or cf:
                descs.append(f"{c.source}:{ck or '-'}/{cf or '-'}")
        cands = ','.join(descs[:6])
    except Exception:
        cands = ''
    try:
        raw = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_DESC_OFFSET, 2)
        tv_view = raw[0] | raw[1] << 8
    except (OSError, AttributeError):
        tv_view = None
    try:
        tv_flag = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_FLAG_OFFSET, 1)[0]
    except (OSError, AttributeError):
        tv_flag = None
    ptr = getattr(shop_state, 'ptr', None) if shop_state is not None else None
    npcconv = bool(getattr(w, '_npc_conversation_active', False))
    try:
        active = w._session_manager.active_session()
        sess = active.name if active is not None else ''
    except AttributeError:
        sess = ''
    from session.tavern_signals import yesno_menu_back_of
    recov = yesno_menu_back_of(shop_state)
    lists = _list_inputs_of(w, shop_state)
    running, slots = _list_window_of(w)
    key = (is_ctx, sub_key, own_kind, own, surface, owner, cands, img or '', npcconv, sess, lists[:3] + lists[4:], running)
    if key != getattr(w, '_tavern_view_dbg_key', None):
        w._tavern_view_dbg_key = key
        _log.warning('tavern view dbg: sub=%s view(+0x8F6E)=%s flag(+0x8F74)=%s own_kind=%s own=%s surface=%r owner=%r ptr=%s img=%r cands=[%s] npcconv=%s sess=%r recov=%s ctx_tavern=%s newpop_fg=%s b7c4=%s ff2=%s price(+0xA836)=%s drinks=%s rooms=%s list_window=%s slots(+0xFAB8)=%s', sub_key.rsplit('.', 1)[-1] if sub_key else 'none', f'0x{tv_view:04X}' if tv_view is not None else 'None', f'0x{tv_flag:02X}' if tv_flag is not None else 'None', own_kind, own, surface, owner, f'0x{ptr:04X}' if ptr is not None else 'None', img, cands, npcconv, sess, recov, is_ctx, *lists, running, slots)
    w._tavern_view_dbg_prev_ctx = is_ctx

def _hex_u8(value) -> str:
    return f'0x{value:02X}' if value is not None else '?'

def _list_window_of(w) -> tuple:
    from active_template_reader import ACTIVE_TEMPLATE_PTR_OFFSETS
    from session.tavern_node import TavernNode
    first = ACTIVE_TEMPLATE_PTR_OFFSETS[0]
    try:
        raw = w._analyzer.read_bytes(w._anchor + first, ACTIVE_TEMPLATE_PTR_OFFSETS[-1] + 2 - first)
        slots = bytes(raw).hex()
    except Exception:
        return ('?', '?')
    running = TavernNode.list_window_in(raw)
    return ('?' if running is None else str(running), slots or '?')

def _list_inputs_of(w, shop_state) -> tuple:
    if shop_state is None:
        return ('?', '?', '?', '?', '?', '?')
    price = getattr(shop_state, 'price_cache', None)
    try:
        from session.tavern_signals import tavern_lists_of
        buy_items, _span, rooms = tavern_lists_of(shop_state, getattr(w, '_analyzer', None), getattr(w, '_anchor', 0))
        n_drinks, n_rooms = (str(len(buy_items)), str(len(rooms)))
    except Exception:
        n_drinks = n_rooms = '?'
    return (str(bool(getattr(shop_state, 'newpop_fg', False))), _hex_u8(getattr(shop_state, 'b7c4', None)), _hex_u8(getattr(shop_state, 'ff2', None)), price.hex() if price else '?', n_drinks, n_rooms)
__all__ = ['log_tavern_view_diagnostics']
