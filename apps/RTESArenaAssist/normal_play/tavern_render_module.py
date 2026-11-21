from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')

def select_tavern_template(candidates, *, img_name: str, lookup_hit):
    from active_template_reader import select_active_template_candidate
    from session.tavern_signals import own_template_table
    return select_active_template_candidate(candidates, own_template_table(), lookup_hit, img_name=img_name)

def _tavern_input_prompt_label(candidate) -> str:
    from session.tavern_signals import input_prompt_label
    return input_prompt_label(candidate)

def template_handoff_owners() -> frozenset:
    from session.tavern_node import TAVERN_NODE
    return TAVERN_NODE.panel_owners

def poll_tavern_render(w, *, tview, shop_state, shop_img_name: str, top_level_state: str) -> tuple[bool, bool, bool, bool]:
    owner = tview.render_owner
    l4_kind = tview.l4_kind
    shop_menu_visible = False
    shop_buy_active = False
    shop_buy_active, shop_menu_visible = _render_tavern_shop_l4(w, owner, l4_kind, shop_state, shop_img_name)
    if owner:
        _cleanup_shop_buy(w, shop_buy_active, shop_menu_visible, shop_img_name)
        _cleanup_shop_menu(w, shop_menu_visible, shop_buy_active, shop_img_name)
    from normal_play.negotiation_module import poll_negotiation as _poll_negotiation, cleanup_if_owner as _cleanup_negotiation
    if owner == 'negotiation':
        negot_handled = _poll_negotiation(w, img_name=shop_img_name, top_level_state=top_level_state)
    else:
        negot_handled = False
        if owner:
            _cleanup_negotiation(w)
    from normal_play.active_template_module import poll_active_template as _poll_active_template, cleanup_if_owner as _cleanup_active_template
    if negot_handled:
        active_tmpl_handled = False
    elif owner != 'active_template':
        active_tmpl_handled = False
    else:
        active_tmpl_handled = _poll_active_template(w, shop_img_name=shop_img_name, shop_menu_visible=shop_menu_visible, shop_buy_active=shop_buy_active, allow_during_shop_menu=True, select_candidate=select_tavern_template, handoff_owners=template_handoff_owners(), diag_label='tavern', input_prompt_label=_tavern_input_prompt_label)
    if owner and owner != 'active_template' and (not negot_handled):
        _cleanup_active_template(w)
    return (negot_handled, active_tmpl_handled, shop_menu_visible, shop_buy_active)

def _render_shop_drinks(w, shop_state) -> None:
    try:
        from shop_item_list_reader import translate_shop_item_list
        from session.tavern_signals import tavern_lists_of
        _buy_items = tavern_lists_of(shop_state, getattr(w, '_analyzer', None), getattr(w, '_anchor', 0))[0]
        _buy_now_tr = translate_shop_item_list(_buy_items, section='drinks')
        _seen = list(getattr(w, '_shop_buy_seen_items', []) or [])
        _seen_keys = {it['en'] for it in _seen}
        _added: list[str] = []
        for it in _buy_now_tr:
            if it['en'] not in _seen_keys:
                _seen.append(it)
                _seen_keys.add(it['en'])
                _added.append(it['en'])
        w._shop_buy_seen_items = _seen
        try:
            if w._ui_router.ensure_panel_mode('shop_buy'):
                _log.info('panel_mode -> shop_buy (initial)')
        except AttributeError:
            pass
        _buy_key_now = tuple(((it['en'], it['price_display']) for it in _seen))
        _forget_key_if_push_lost(w, '_shop_buy_key_prev', 'shop_buy')
        _prev_buy_key = getattr(w, '_shop_buy_key_prev', None)
        if _buy_key_now != _prev_buy_key:
            w._shop_buy_key_prev = _buy_key_now
            w._ui_router.update_shop_buy_list('shop_buy', _seen, 'Buy Drinks', '酒を買う')
            _note_pushed(w, '_shop_buy_key_prev')
            if _added:
                _log.info('shop_buy update (seen=%d added=%r visible=%r)', len(_seen), _added, [it['en'] for it in _buy_now_tr])
    except Exception:
        _log.exception('shop_buy update failed')

def _render_tavern_shop_l4(w, owner: str, l4_kind: str, shop_state, shop_img_name: str) -> tuple[bool, bool]:
    from session.tavern_view import shop_row_owner_of
    from store_surface import publish_list_front, publish_menu_front
    if shop_state is None or not owner or shop_row_owner_of(l4_kind) != owner:
        return (False, False)
    if l4_kind in ('rooms', 'drinks'):
        publish_list_front(w, store_surface=True)
        if l4_kind == 'rooms':
            _render_shop_rooms(w, shop_state)
        else:
            _render_shop_drinks(w, shop_state)
        return (True, False)
    publish_menu_front(w)
    _render_shop_menu(w, shop_state, shop_img_name, owner)
    return (False, True)

def _forget_key_if_push_lost(w, key_attr: str, owner: str) -> None:
    serial_attr = key_attr + '_flush'
    pushed_at = getattr(w, serial_attr, None)
    if not isinstance(pushed_at, int):
        return
    try:
        serial = w._ui_router.flush_serial()
        winner = w._ui_router.last_flush_winner_owner()
    except AttributeError:
        return
    if not isinstance(serial, int) or serial <= pushed_at:
        return
    setattr(w, serial_attr, None)
    if serial == pushed_at + 1 and winner != owner:
        setattr(w, key_attr, None)

def _note_pushed(w, key_attr: str) -> None:
    try:
        serial = w._ui_router.flush_serial()
    except AttributeError:
        return
    if isinstance(serial, int):
        setattr(w, key_attr + '_flush', serial)

def _render_shop_rooms(w, shop_state) -> None:
    try:
        from room_list_reader import translate_room_list
        from session.tavern_signals import tavern_lists_of
        _room_items = tavern_lists_of(shop_state, getattr(w, '_analyzer', None), getattr(w, '_anchor', 0))[2]
        _room_tr = translate_room_list(_room_items, section='rooms')
        w._shop_buy_seen_items = _room_tr
        try:
            if w._ui_router.ensure_panel_mode('shop_buy'):
                _log.info('panel_mode -> shop_buy (rooms initial)')
        except AttributeError:
            pass
        _room_key_now = tuple(((it['en'], it['price_display']) for it in _room_tr))
        _forget_key_if_push_lost(w, '_shop_buy_key_prev', 'shop_buy')
        _prev_buy_key = getattr(w, '_shop_buy_key_prev', None)
        if _room_key_now != _prev_buy_key:
            w._shop_buy_key_prev = _room_key_now
            w._ui_router.update_shop_buy_list('shop_buy', _room_tr, 'Get a Room', '部屋を取る')
            _note_pushed(w, '_shop_buy_key_prev')
            _log.info('shop_rooms update (rooms=%d items=%r)', len(_room_tr), [it['en'] for it in _room_tr])
    except Exception:
        _log.exception('shop_rooms update failed')

def _render_shop_menu(w, shop_state, shop_img_name: str, shop_kind: str) -> None:
    from session.tavern_signals import tavern_surface_of
    _shop_kind = shop_kind
    _title_own = tavern_surface_of(w, shop_state)[1]
    try:
        from shop_menu_reader import translate_shop_menu_items, translate_ui_text
        from normal_play.shop_render_common import build_menu_display
        _menu_items = list(shop_state.ptr_group_items)
        _menu_hotkeys = list(shop_state.ptr_group_hotkeys)
        _menu_key = (_shop_kind, tuple(_menu_items), tuple(_menu_hotkeys))
        _forget_key_if_push_lost(w, '_shop_menu_key_prev', _shop_kind)
        _prev_menu_key = getattr(w, '_shop_menu_key_prev', None)
        if _menu_key != _prev_menu_key:
            w._shop_menu_key_prev = _menu_key
            _note_pushed(w, '_shop_menu_key_prev')
            _menu_tr = translate_shop_menu_items(_menu_items, owner_kind='tavern')
            _title_en = _title_own
            _title_ja = translate_ui_text('tavern', _title_en) or _title_en if _title_en else ''
            _tab_en_text, _tab_ja_text, _panel_en_text, _panel_ja_text = build_menu_display(_menu_tr, _menu_hotkeys, _title_en, _title_ja)
            w._ui_router.update_translation(_shop_kind, _tab_en_text, _tab_ja_text, panel_en=_panel_en_text, panel_ja=_panel_ja_text)
            _log.info('%s update (img=%r title=%r items=%r hotkeys=%r)', _shop_kind, shop_img_name, _title_en, _menu_items, _menu_hotkeys)
    except Exception:
        _log.exception('%s update failed', _shop_kind)

def _cleanup_shop_buy(w, shop_buy_active: bool, shop_menu_visible: bool, shop_img_name: str) -> None:
    if shop_buy_active:
        return
    _had_shop_buy = bool(getattr(w, '_shop_buy_seen_items', None) or getattr(w, '_shop_buy_key_prev', None) is not None)
    if not _had_shop_buy:
        return
    w._shop_buy_seen_items = []
    w._shop_buy_key_prev = None
    try:
        w._ui_router.reset_panel_mode_if(('shop_buy',))
    except AttributeError:
        pass
    if not shop_menu_visible:
        w._ui_router.clear_if_owner('shop_buy', mode='translate')
    else:
        w._ui_router.release_if_owner('shop_buy')
    _log.info('shop_buy exit (img=%r next=%s)', shop_img_name, 'shop_menu' if shop_menu_visible else 'none')

def _cleanup_shop_menu(w, shop_menu_visible: bool, shop_buy_active: bool, shop_img_name: str) -> None:
    if shop_menu_visible:
        return
    _menu_key = getattr(w, '_shop_menu_key_prev', None)
    if _menu_key is None:
        return
    w._shop_menu_key_prev = None
    _was_owner = _menu_key[0] if isinstance(_menu_key, tuple) and _menu_key else 'shop_menu'
    if _was_owner not in ('shop_menu', 'shop_rumor_type'):
        _was_owner = 'shop_menu'
    if not shop_buy_active:
        w._ui_router.clear_if_owner(_was_owner)
    else:
        w._ui_router.release_if_owner(_was_owner)
    _log.info('%s exit (img=%r next=%s)', _was_owner, shop_img_name, 'shop_buy' if shop_buy_active else 'none')

def poll_units_outside_conversation(w, *, shop_img_name: str, shop_menu_visible: bool, shop_buy_active: bool, area: str, top_level_state: str) -> tuple[bool, bool]:
    from controllers.poll_diag import _phase_record, _phase_start
    from normal_play.negotiation_module import poll_negotiation as _poll_negotiation, cleanup_if_owner as _cleanup_negotiation
    from normal_play.artifact_offer_module import poll_artifact_offer as _poll_artifact_offer, release_artifact_offer as _release_artifact_offer
    from normal_play.active_template_module import poll_active_template as _poll_active_template, cleanup_if_owner as _cleanup_active_template, note_unclaimed_dialog_template as _note_unclaimed
    if shop_menu_visible:
        artifact_handled = False
    else:
        artifact_handled = _poll_artifact_offer(w, img_name=shop_img_name, top_level_state=top_level_state)
    if not artifact_handled:
        _release_artifact_offer(w)
    if shop_menu_visible or artifact_handled:
        negot_handled = False
        _cleanup_negotiation(w)
    else:
        negot_handled = _poll_negotiation(w, img_name=shop_img_name, top_level_state=top_level_state)
        if not negot_handled:
            _cleanup_negotiation(w)
    if negot_handled or artifact_handled:
        active_tmpl_handled = False
        if area != 'dungeon':
            _note_unclaimed(w, reason='negotiation img=%r' % shop_img_name if negot_handled else 'artifact_offer')
    else:
        _t_active_tmpl = _phase_start()
        active_tmpl_handled = _poll_active_template(w, shop_img_name=shop_img_name, shop_menu_visible=shop_menu_visible, shop_buy_active=shop_buy_active, allow_during_shop_menu=False, c_area=area, handoff_owners=template_handoff_owners(), input_prompt_label=_tavern_input_prompt_label)
        _phase_record(w, 'active_template', _t_active_tmpl)
    if not active_tmpl_handled and (not negot_handled):
        _cleanup_active_template(w)
    return (negot_handled or artifact_handled, active_tmpl_handled)

def close_units_outside_conversation(w) -> None:
    from normal_play.artifact_offer_module import release_artifact_offer
    release_artifact_offer(w)

def leave_units_outside_conversation(w) -> None:
    from normal_play.artifact_offer_module import release_artifact_offer
    from normal_play.negotiation_module import cleanup_if_owner as _cleanup_negotiation
    release_artifact_offer(w)
    _cleanup_negotiation(w)

def reset_tavern_render_state(w) -> None:
    w._shop_menu_key_prev = None
    w._shop_buy_seen_items = []
    w._shop_buy_key_prev = None
    try:
        w._ui_router.reset_panel_mode_if(('shop_buy',))
    except AttributeError:
        pass

def render_no_session_shop(w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool) -> tuple[bool, bool]:
    from session.tavern_signals import tavern_surface_of
    from session.tavern_view import l4_of_shop_kind, shop_row_owner_of
    _l4 = l4_of_shop_kind(tavern_surface_of(w, shop_state)[0])
    _buy, _menu = _render_tavern_shop_l4(w, shop_row_owner_of(_l4), _l4, shop_state, shop_img_name)
    shop_buy_active = shop_buy_active or _buy
    shop_menu_visible = shop_menu_visible or _menu
    _cleanup_shop_buy(w, shop_buy_active, shop_menu_visible, shop_img_name)
    _cleanup_shop_menu(w, shop_menu_visible, shop_buy_active, shop_img_name)
    return (shop_buy_active, shop_menu_visible)
render_shop_drinks = _render_shop_drinks
render_shop_rooms = _render_shop_rooms
render_shop_menu = _render_shop_menu
cleanup_shop_buy = _cleanup_shop_buy
cleanup_shop_menu = _cleanup_shop_menu
__all__ = ['poll_tavern_render', 'poll_units_outside_conversation', 'close_units_outside_conversation', 'leave_units_outside_conversation', 'select_tavern_template', 'template_handoff_owners', 'render_no_session_shop', 'render_shop_drinks', 'render_shop_rooms', 'render_shop_menu', 'cleanup_shop_buy', 'cleanup_shop_menu', 'reset_tavern_render_state']
