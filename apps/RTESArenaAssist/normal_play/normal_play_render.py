from __future__ import annotations
import logging
from types import SimpleNamespace
from controllers.poll_diag import _checkpoint, _phase_record, _phase_start
from normal_play import npc_conversation_module as _npc_conversation
from top_level.top_level_dispatcher import current_state as _current_top_level
from screen_img_signals import INTERIOR_MENU_IMG, NPC_POPUP_IMG
_log = logging.getLogger('normal_play_render')

def poll_cinematic_dispatch(w, b30):
    from normal_play.cinematic_module import poll_cinematic as _poll_cinematic
    _poll_cinematic(w, b30=b30)

def poll_lock_message_dispatch(w, b30, *, near, band, in_play: bool):
    from normal_play.lock_message_module import poll_lock_message as _poll_lock_message, poll_lock_message_lifetime as _poll_lock_message_lifetime, release_lock_message as _release_lock_message
    if not in_play or near is None:
        _release_lock_message(w)
        return
    _poll_lock_message(w, b30=b30, near=near, band=band)
    _poll_lock_message_lifetime(w, b30=b30, band=band)

def poll_static_action_text_dispatch(w, *, band, in_play: bool):
    from normal_play.static_action_text_module import poll_static_action_text
    poll_static_action_text(w, band=band, in_play=in_play)

def poll_c1_surface_dispatch(w, b30, *, inf_name, mif_name, c_area: str='', band=None, message_taken: bool=False):
    from normal_play.trigger_module import poll_red_text as _poll_red_text, poll_red_text_lifetime as _poll_red_text_lifetime, release_red_text as _release_red_text
    from normal_play.c1_gold_drop_module import poll_gold_drop as _poll_gold_drop, poll_gold_drop_lifetime as _poll_gold_drop_lifetime, release_gold_drop as _release_gold_drop
    from normal_play.c1_runtime_dialog_module import poll_c1_runtime_dialog_lifetime as _poll_c1_runtime_dialog_lifetime, release_c1_runtime_dialog as _release_c1_runtime_dialog
    if c_area != 'dungeon':
        _release_gold_drop(w)
        _release_c1_runtime_dialog(w)
        _release_red_text(w)
        return
    _poll_red_text(w, b30=b30, message_taken=message_taken)
    _poll_gold_drop(w, b30=b30, inf_name=inf_name, mif_name=mif_name, observation=b30.get('gold_observation'))
    _c1_axis = b30.get('c1_dialog_axis')
    _poll_red_text_lifetime(w, b30=b30, band=band)
    _poll_gold_drop_lifetime(w, axis=_c1_axis)
    _poll_c1_runtime_dialog_lifetime(w, axis=_c1_axis)
_ASK_ABOUT_MAIN_STATE = 'ask_about_main'
_UNDECIDED_STATE = 'undecided'
_ASK_ABOUT_MAIN_BLOCKING_LIST_STATES = frozenset({'where_is_list', 'dynamic_place_list', 'npc_response', _UNDECIDED_STATE})
_ASK_ABOUT_MENU_PTR_MIN = 32768
_ASK_ABOUT_MENU_PTR_MAX = 36864

def blocks_ask_about_main(list_state: str) -> bool:
    return list_state in _ASK_ABOUT_MAIN_BLOCKING_LIST_STATES

def ask_about_main_display_allowed(list_state: str, img_name: str, current_ptr: int) -> bool:
    if not blocks_ask_about_main(list_state):
        return True
    if (img_name or '').upper() == NPC_POPUP_IMG:
        return False
    try:
        ptr = int(current_ptr)
    except (TypeError, ValueError):
        return False
    return _ASK_ABOUT_MENU_PTR_MIN <= ptr < _ASK_ABOUT_MENU_PTR_MAX

def _classify_popup11_substate(w, _img_name, _list_state_eligible):
    if _list_state_eligible:
        try:
            from popup11_list_detector import detect_popup11_list_state
            _list_state = detect_popup11_list_state(w._analyzer, w._anchor)
        except Exception:
            _list_state = _UNDECIDED_STATE
    else:
        _list_state = 'npc_response'
    try:
        from popup11_response_reader import candidate_contains_pointer, read_current_text_pointer, read_response_candidate
        _resp_cand = read_response_candidate(w._analyzer, w._anchor)
        _resp_ptr = read_current_text_pointer(w._analyzer, w._anchor)
        _response_pointer_hit = bool(_resp_cand and candidate_contains_pointer(_resp_cand, _resp_ptr))
    except Exception:
        _resp_cand = None
        _response_pointer_hit = False
    _fresh_response_text = _resp_cand.text if _resp_cand else ''
    _response_lookup_hit = bool(_resp_cand and _resp_cand.lookup_hit)
    _diag_resp_off = _resp_cand.source_offset if _resp_cand else -1
    _diag_resp_text = _resp_cand.text[:48] if _resp_cand else ''
    _diag_key = (_img_name, _list_state, _response_lookup_hit, _response_pointer_hit, _diag_resp_off, _diag_resp_text)
    _diag_changed = getattr(w, '_popup11_substate_diag_prev', None) != _diag_key
    if _diag_changed:
        w._popup11_substate_diag_prev = _diag_key
    return SimpleNamespace(list_state=_list_state, fresh_response_text=_fresh_response_text, response_lookup_hit=_response_lookup_hit, response_pointer_hit=_response_pointer_hit, diag_resp_off=_diag_resp_off, diag_resp_text=_diag_resp_text, diag_changed=_diag_changed)

def _render_popup11_substate(w, _img_name, sub):
    _list_state = sub.list_state
    if sub.diag_changed:
        _log.info('popup11 substate diag: list_state=%r img=%r lookup_hit=%s pointer_hit=%s resp_off=0x%X resp_text=%r', _list_state, _img_name, sub.response_lookup_hit, sub.response_pointer_hit, sub.diag_resp_off if sub.diag_resp_off >= 0 else 0, sub.diag_resp_text)
    if _list_state in (_ASK_ABOUT_MAIN_STATE, 'rumor_type'):
        _npc_conversation.show_ask_about_menu(w)
    elif _list_state == _UNDECIDED_STATE:
        pass
    elif _list_state == 'where_is_list':
        _npc_conversation.show_where_is_list(w)
    elif _list_state == 'dynamic_place_list':
        _npc_conversation.show_dynamic_place_list(w)
    elif sub.fresh_response_text and (sub.response_lookup_hit or sub.response_pointer_hit or _img_name == NPC_POPUP_IMG):
        _npc_conversation.show_npc_dialog(w, text_override=sub.fresh_response_text)
    elif sub.diag_changed and sub.fresh_response_text:
        _log.debug('NPC response not identified (img=%r) - skip display: %r', _img_name, sub.fresh_response_text[:48])

def _cif_response_pointer_active(analyzer, anchor) -> bool:
    try:
        from popup11_response_reader import read_current_text_pointer, RESPONSE_OFFSETS, RESPONSE_READ_LEN
        ptr = read_current_text_pointer(analyzer, anchor)
    except Exception:
        return False
    if ptr is None:
        return False
    return any((off <= ptr < off + RESPONSE_READ_LEN for off in RESPONSE_OFFSETS))

def _npc_response_continuation_active(w, img_name, top_level) -> bool:
    if top_level != 'normal-play':
        return False
    return _cif_response_pointer_active(w._analyzer, w._anchor)

def _poll_npc_conversation_foreground(w, _img_name, _shop_menu_visible, _shop_buy_active, _npc_popup_active, _list_state_eligible, _npc_detection_allowed):
    _sub = _classify_popup11_substate(w, _img_name, _list_state_eligible) if _npc_popup_active else None
    _list_state = _sub.list_state if _sub is not None else ''
    _ok = True
    _city_npc = -1
    try:
        from screen_detector import CITY_NPC_ACTIVE_OFFSET, _read_u16_le
        _city_npc = _read_u16_le(w._analyzer, w._anchor + CITY_NPC_ACTIVE_OFFSET)
    except Exception:
        _ok = False
    _menu_foreground = False
    if _ok:
        _ask_about_active = _city_npc == 17285 and _npc_detection_allowed and (not _shop_menu_visible) and (not _shop_buy_active)
        if _ask_about_active:
            try:
                _ptr_raw = w._analyzer.read_bytes(w._anchor + 43076, 2)
                _cur_ptr = _ptr_raw[0] | _ptr_raw[1] << 8
            except (OSError, AttributeError, IndexError):
                _cur_ptr = -1
            _menu_foreground = ask_about_main_display_allowed(_list_state, _img_name, _cur_ptr)
    if _menu_foreground:
        _npc_conversation.show_ask_about_menu(w)
    elif _npc_popup_active:
        _render_popup11_substate(w, _img_name, _sub)
    else:
        _npc_conversation.forget_shown(w)
    if _ok:
        _city_npc_was_nonzero = getattr(w, '_city_npc_active_was_nonzero_prev', False)
        if _current_top_level(w) == 'normal-play' and _city_npc_was_nonzero and (_city_npc == 0):
            _npc_conversation.reset_npc_dialog_display(w)
        w._city_npc_active_was_nonzero_prev = _city_npc != 0

def _poll_npc_popup_display(w, _img_name, _shop_menu_visible, _shop_buy_active):
    _NPC_DIALOG_INCOMPATIBLE_SCREENS = frozenset({'system_menu', 'equipment', 'spellbook', 'spell_detail', 'automap', 'logbook', 'status_page', 'bonus_screen', 'loading'})
    _prev_sid = getattr(w, '_screen_id_prev', None)
    _npc_detection_allowed = _current_top_level(w) == 'normal-play' and _prev_sid not in _NPC_DIALOG_INCOMPATIBLE_SCREENS and w._npc_conversation_active
    _cif_continuation = _npc_response_continuation_active(w, _img_name, _current_top_level(w))
    _npc_popup_active = _npc_detection_allowed and (_img_name == NPC_POPUP_IMG or _cif_continuation)
    try:
        if w._npc_conversation_active and (not _npc_popup_active):
            _diag_popup_active_key = (_img_name, _npc_detection_allowed, _cif_continuation)
            _diag_popup_active_prev = getattr(w, '_npc_popup_active_diag_prev', None)
            if _diag_popup_active_key != _diag_popup_active_prev:
                w._npc_popup_active_diag_prev = _diag_popup_active_key
                _log.info('npc_popup_active=False during npc_conv (img=%r detect_allowed=%s cif_cont=%s)', _img_name, _npc_detection_allowed, _cif_continuation)
    except (AttributeError, OSError):
        pass
    _list_state_eligible = _npc_popup_active and _img_name == NPC_POPUP_IMG
    if not _npc_popup_active and w._npc_conversation_active and (_current_top_level(w) == 'normal-play'):
        try:
            from popup11_response_reader import read_response_candidate as _read_resp_cand_diag
            _diag_cand = _read_resp_cand_diag(w._analyzer, w._anchor)
            _diag_text = _diag_cand.text if _diag_cand else ''
            _diag_off = _diag_cand.source_offset if _diag_cand else -1
            _diag_hit = bool(_diag_cand and _diag_cand.lookup_hit)
            if _diag_text:
                _diag_unpicked_resp_key = (_diag_off, _diag_hit, _diag_text[:80])
                _diag_unpicked_resp_prev = getattr(w, '_unpicked_resp_diag_prev', None)
                if _diag_unpicked_resp_key != _diag_unpicked_resp_prev:
                    w._unpicked_resp_diag_prev = _diag_unpicked_resp_key
                    _log.info('unpicked response candidate (img=%r src_off=0x%X lookup_hit=%s text=%r)', _img_name, _diag_off if _diag_off >= 0 else 0, _diag_hit, _diag_text[:120])
        except Exception:
            pass
    _poll_npc_conversation_foreground(w, _img_name, _shop_menu_visible, _shop_buy_active, _npc_popup_active, _list_state_eligible, _npc_detection_allowed)

def _l3_facility_node(w):
    from l3_facility import l3_node
    return l3_node(w)
_FACILITY_PTR_UNSET = object()

def _read_facility_story_pointer(w) -> int | None:
    try:
        from active_template_reader import read_current_text_pointer
        return read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        return None

def _close_facility_story_units(w) -> None:
    _node = _l3_facility_node(w)
    if _node is not None:
        _node.poll_story(w, active=False)
    w._facility_story_kind_now = ''
    w._facility_story_owner_now = ''
    w._facility_story_ptr_now = None

def _poll_facility_story_dispatch(w, *, blocked: bool, in_interior: bool, story_kind: str, story_ptr: int | None) -> bool:
    _node = _l3_facility_node(w)
    if blocked or not in_interior:
        _close_facility_story_units(w)
        return False
    if _node is None:
        return False
    if not story_kind:
        _node.poll_story(w, active=False)
        return False
    return bool(_node.poll_story(w, active=True, foreground_ptr=story_ptr))

def _poll_facility_render_dispatch(w, *, _shop_state, _shop_img_name, _poll_hierarchy_area, _shop_menu_visible, _shop_buy_active, _facility_foreground_ptr=_FACILITY_PTR_UNSET):
    _node = _l3_facility_node(w)
    _story_ptr = _read_facility_story_pointer(w) if _facility_foreground_ptr is _FACILITY_PTR_UNSET else _facility_foreground_ptr
    _negot_handled = False
    _active_tmpl_handled = False
    _facility_surface_front = False
    _t_facility_render = _phase_start()
    if _node is not None:
        _story_kind, _session_up, _negot_handled, _active_tmpl_handled, _shop_menu_visible, _shop_buy_active, _facility_surface_front = _node.run_render_stage(w, shop_state=_shop_state, shop_img_name=_shop_img_name, shop_menu_visible=_shop_menu_visible, shop_buy_active=_shop_buy_active, foreground_ptr=_story_ptr, top_level_state=_current_top_level(w))
    else:
        _story_kind, _session_up = ('', False)
        w._facility_story_kind_now = ''
        w._facility_story_owner_now = ''
        w._facility_story_ptr_now = _story_ptr
    _phase_record(w, 'facility_render', _t_facility_render)
    _checkpoint(w, 'facility_render')
    _outside = not _story_kind and (not _session_up)
    from l3_facility import finish_exits_in_render_stage as _finish_exits
    _finish_exits(w, outside=_outside)
    if _node is not None:
        _units = _node.poll_units_outside_conversation(w, outside=_outside, shop_img_name=_shop_img_name, shop_menu_visible=_shop_menu_visible, shop_buy_active=_shop_buy_active, area=_poll_hierarchy_area, top_level_state=_current_top_level(w))
    else:
        from normal_play.active_template_module import poll_template_outside_conversation as _poll_template_outside
        _units = (False, _poll_template_outside(w, shop_img_name=_shop_img_name, shop_menu_visible=_shop_menu_visible, shop_buy_active=_shop_buy_active, area=_poll_hierarchy_area))
    if _outside:
        _negot_handled, _active_tmpl_handled = _units
        _facility_surface_front = bool(_shop_menu_visible or _shop_buy_active or _negot_handled)
    return (_negot_handled, _active_tmpl_handled, _shop_menu_visible, _shop_buy_active, _facility_surface_front)

def _store_surface_now(w) -> bool:
    from store_surface import store_surface_now
    return store_surface_now(w)

def _poll_dialog_unit_dispatch(w, *, in_interior, msg_buf, npc_dialog, _npc_dialog_changed, _npc_phase_raw, _img_name_now, _building_entry_active, _entry_phase_prev, _shop_state, _shop_img_name, _shop_menu_visible, _shop_buy_active, _facility_active_now, _poll_hierarchy_area, _negot_handled, _active_tmpl_handled, _inventory_screen=False, _b30=None):
    from arena_bridge import NPC_PHASE_BUILDING_ENTRY, NPC_PHASE_RESPONDING, NPC_PHASE_IDLE, NPC_PHASE_ASKING
    from normal_play.building_entry_module import poll_building_entry as _poll_building_entry
    from normal_play.npc_message_module import poll_npc_message_popup_lifetime as _poll_npc_message_popup_lifetime, poll_travel_event_lifecycle as _poll_travel_event_lifecycle
    from normal_play.dungeon_splash_module import poll_dungeon_splash_lifecycle as _poll_dungeon_splash_lifecycle
    if _b30 is not None and _poll_hierarchy_area == 'dungeon':
        from normal_play.c1_gold_drop_module import observe_gold_drop
        _b30['gold_observation'] = observe_gold_drop(w)
    try:
        from screen_detector import read_popup_frame, popup_frame_is_drawn
        _popup_frame = read_popup_frame(w._analyzer, w._anchor)
        _popup_frame_drawn = popup_frame_is_drawn(_popup_frame)
    except (ImportError, AttributeError, OSError):
        _popup_frame = None
        _popup_frame_drawn = None
    _npc_message_popup_closed = _poll_npc_message_popup_lifetime(w, popup_frame=_popup_frame, popup_frame_drawn=_popup_frame_drawn, screen_img=_img_name_now)
    _travel_event_active = _poll_travel_event_lifecycle(w, npc_dialog=npc_dialog, screen_img=_img_name_now, facility_active_now=_facility_active_now)
    _dungeon_splash_active = _poll_dungeon_splash_lifecycle(w, screen_img=_img_name_now, facility_active_now=_facility_active_now)
    _phase_overlay = _npc_phase_raw in (NPC_PHASE_BUILDING_ENTRY, NPC_PHASE_RESPONDING)
    _menu_overlay = in_interior and _img_name_now == INTERIOR_MENU_IMG and (_npc_phase_raw not in (NPC_PHASE_IDLE, NPC_PHASE_ASKING))
    _npc_overlay_active = (_phase_overlay or _menu_overlay) and (not _building_entry_active) and (not _shop_buy_active) and (not _shop_menu_visible)
    _npc_overlay_active_prev = getattr(w, '_npc_overlay_active_prev', False)
    w._npc_overlay_active_prev = _npc_overlay_active
    if _npc_overlay_active and (not _npc_overlay_active_prev):
        from normal_play.instore_dialog_module import release_current_key_on_overlay_start as _release_instore_key
        _release_instore_key(w)
    _entry_handled = _poll_building_entry(w, building_entry_active=_building_entry_active, entry_phase_prev=_entry_phase_prev, msg_buf=msg_buf, npc_dialog=npc_dialog)
    if _travel_event_active or _dungeon_splash_active:
        _entry_handled = True
    _story_kind = getattr(w, '_facility_story_kind_now', '')
    _story_ptr = getattr(w, '_facility_story_ptr_now', None)
    if _poll_facility_story_dispatch(w, blocked=_entry_handled, in_interior=in_interior, story_kind=_story_kind, story_ptr=_story_ptr):
        _entry_handled = True
    _l3_node = _l3_facility_node(w)
    _t_facility_reply = _phase_start()
    _facility_reply_owns, _facility_reply_handled = (False, False)
    if _l3_node is not None:
        _facility_reply_owns, _facility_reply_handled = _l3_node.poll_reply_unit(w, shop_state=_shop_state, entry_handled=_entry_handled, img_name=_shop_img_name, shop_menu_visible=_shop_menu_visible, area=_poll_hierarchy_area)
    if _facility_reply_owns:
        _phase_record(w, 'facility_reply', _t_facility_reply)
    if _facility_reply_handled:
        _entry_handled = True
    if not _entry_handled:
        from normal_play.camp_rest_module import poll_camp_rest as _poll_camp_rest
        if _poll_camp_rest(w):
            _entry_handled = True
    from normal_play.npc_dialog_module import poll_npc_dialog as _poll_npc_dialog
    _instore_resp_handled = False
    if not _entry_handled:
        _instore_resp_handled = _poll_npc_dialog(w, b30=_b30, entry_handled=False, npc_overlay_active=_npc_overlay_active, in_interior=in_interior, npc_phase_raw=_npc_phase_raw, shop_buy_active=_shop_buy_active, shop_menu_visible=_shop_menu_visible, facility_active_now=_facility_active_now, npc_dialog=npc_dialog, npc_dialog_changed=_npc_dialog_changed, c_area=_poll_hierarchy_area, internalized_facility_active=bool(_l3_node is not None and _l3_node.owns_shop_replies and _l3_node.latch(w)[0]), store_surface_now=_store_surface_now(w), negot_handled=_negot_handled, active_tmpl_handled=_active_tmpl_handled, popup_observation=(_popup_frame, _popup_frame_drawn, True, _npc_message_popup_closed, _img_name_now))
        if _instore_resp_handled:
            _entry_handled = True
    if _poll_hierarchy_area == 'dungeon' and _inventory_screen:
        from normal_play.c1_runtime_dialog_module import pause_c1_runtime_dialog as _pause_c1_runtime_dialog
        _pause_c1_runtime_dialog(w)
    elif _poll_hierarchy_area == 'dungeon' and (not _entry_handled):
        from normal_play.c1_runtime_dialog_module import poll_c1_runtime_dialog as _poll_c1_runtime_dialog
        from normal_play.c1_gold_drop_module import accepted_gold_drop_body
        _gold_surface_body = accepted_gold_drop_body(w)
        _gold_observation = _b30.get('gold_observation') if _b30 else None
        if _gold_observation is not None and _gold_observation.changed and _gold_observation.is_gold and _b30.get('in_gameplay', False):
            _gold_surface_body = _gold_observation.text
        if _poll_c1_runtime_dialog(w, npc_dialog=npc_dialog, facility_active_now=_facility_active_now, msg_buf=msg_buf, axis=_b30.get('c1_dialog_axis') if _b30 else None, gold_surface_body=_gold_surface_body):
            _instore_resp_handled = True
            _entry_handled = True
    return (_entry_handled, _instore_resp_handled)
__all__ = ['poll_c1_surface_dispatch', 'blocks_ask_about_main', 'ask_about_main_display_allowed']
