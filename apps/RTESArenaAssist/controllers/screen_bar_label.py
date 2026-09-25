from __future__ import annotations
import logging
import i18n_helper as i18n
from hierarchy_state import SeparationHierarchy
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('poll_controller')
_TAVERN_VIEW_DESC_OFFSET = 36718
_TAVERN_VIEW_FLAG_OFFSET = 36724

def temple_sub_state_label(w, _conv_label, _is_temple_ctx, _active_session_name_for_label, _screen_suppresses_conversation_label, _resolved_area, _shop_img_name, _shop_state):
    if _is_temple_ctx or getattr(w, '_temple_view_dbg_prev_ctx', False):
        try:
            from controllers.recognition_label import temple_sub_state_key
            _temple_owner = getattr(w, '_panel_owner', '') or ''
            _temple_surface = ''
            if _temple_owner in ('temple_cost', 'temple_prompt'):
                _temple_surface = getattr(w, '_temple_cost_current_surface', '') or ''
                _temple_text = getattr(w, '_temple_cost_current_text', '') or ''
            elif _temple_owner == 'temple_priest_reply':
                _temple_text = getattr(w, '_temple_dialog_current_text', '') or ''
            else:
                _temple_surface = getattr(w, '_active_tmpl_surface_kind_prev', '') or ''
                _temple_text = ''
            _temple_sub_key = temple_sub_state_key(_temple_surface, _temple_owner, _shop_img_name, _temple_text)
        except (AttributeError, ImportError):
            _temple_owner = ''
            _temple_surface = ''
            _temple_text = ''
            _temple_sub_key = ''
        _temple_label_active = _active_session_name_for_label == 'temple' or (not _screen_suppresses_conversation_label and bool(getattr(w, '_field_temple_active_now', False)))
        if _is_temple_ctx and _temple_label_active and _temple_sub_key:
            try:
                _conv_label = _conv_label + i18n.tr(_temple_sub_key)
            except (AttributeError, ImportError):
                pass
        try:
            _td_raw = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_DESC_OFFSET, 2)
            _temple_view = _td_raw[0] | _td_raw[1] << 8
        except (OSError, AttributeError):
            _temple_view = None
        try:
            _temple_flag = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_FLAG_OFFSET, 1)[0]
        except (OSError, AttributeError):
            _temple_flag = None
        try:
            from temple_dialog_reader import classify_temple_phase
            _temple_phase, _temple_phase_vals = classify_temple_phase(w._analyzer, w._anchor)
        except Exception:
            _temple_phase = ''
            _temple_phase_vals = {}
        try:
            from active_template_reader import read_active_template_candidates as _ratc, template_surface_kind as _tsk, input_prompt_facility as _ipf
            _temple_cand_descs = []
            for _c in _ratc(w._analyzer, w._anchor):
                _ck = _tsk(_c) or ''
                _cf = _ipf(_c) or ''
                if _ck or _cf:
                    _temple_cand_descs.append(f"{_c.source}:{_ck or '-'}/{_cf or '-'}")
            _temple_cands = ','.join(_temple_cand_descs[:6])
        except Exception:
            _temple_cands = ''
        _temple_shop_kind = getattr(_shop_state, 'kind', 'none') if _shop_state is not None else 'none'
        _temple_shop_owner = getattr(_shop_state, 'owner_kind', '') if _shop_state is not None else ''
        _temple_shop_reason = getattr(_shop_state, 'reason', '') if _shop_state is not None else ''
        _temple_field_latch = bool(getattr(w, '_field_temple_active_now', False))
        _temple_dbg_key = (_is_temple_ctx, _temple_sub_key, _temple_owner, _temple_surface, _shop_img_name, _temple_phase, _temple_cands, _temple_shop_kind, _temple_shop_owner, _resolved_area, _temple_field_latch)
        if _temple_dbg_key != getattr(w, '_temple_view_dbg_key', None):
            w._temple_view_dbg_key = _temple_dbg_key
            _log.warning('temple view dbg: sub=%s view(+0x8F6E)=%s flag(+0x8F74)=%s phase=%s vals=%s surface=%r owner=%r img=%r text=%r cands=[%s] ctx_temple=%s shop=%s/%r area=%r field_latch=%s shop_reason=%r', _temple_sub_key.rsplit('.', 1)[-1] if _temple_sub_key else 'none', f'0x{_temple_view:04X}' if _temple_view is not None else 'None', f'0x{_temple_flag:02X}' if _temple_flag is not None else 'None', _temple_phase, _temple_phase_vals, _temple_surface, _temple_owner, _shop_img_name, _temple_text[:48], _temple_cands, _is_temple_ctx, _temple_shop_kind, _temple_shop_owner, _resolved_area, _temple_field_latch, _temple_shop_reason[:96])
        w._temple_view_dbg_prev_ctx = _is_temple_ctx
    return _conv_label

def tavern_sub_state_label(w, _conv_label, _is_tavern_ctx, _active_session_name_for_label, _shop_img_name, _shop_state):
    if _is_tavern_ctx or getattr(w, '_tavern_view_dbg_prev_ctx', False):
        try:
            _tv_sub_key = getattr(getattr(w, '_tavern_view', None), 'bar_key', '') or ''
            _tv_shop_kind = getattr(_shop_state, 'kind', 'none') if _shop_state is not None else 'none'
            _tv_owner_kind = getattr(_shop_state, 'owner_kind', '') if _shop_state is not None else ''
            _tv_surface = getattr(w, '_active_tmpl_surface_kind_prev', '') or ''
            _tv_owner = getattr(w, '_panel_owner', '') or ''
        except (AttributeError, ImportError):
            _tv_sub_key = ''
            _tv_shop_kind = 'none'
            _tv_owner_kind = ''
            _tv_surface = ''
            _tv_owner = ''
        _tv_cands = ''
        try:
            from active_template_reader import read_active_template_candidates as _ratc, template_surface_kind as _tsk, input_prompt_facility as _ipf
            _cand_descs = []
            for _c in _ratc(w._analyzer, w._anchor):
                _ck = _tsk(_c) or ''
                _cf = _ipf(_c) or ''
                if _ck or _cf:
                    _cand_descs.append(f"{_c.source}:{_ck or '-'}/{_cf or '-'}")
            _tv_cands = ','.join(_cand_descs[:6])
        except Exception:
            _tv_cands = ''
        try:
            _vd_raw = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_DESC_OFFSET, 2)
            _tv_view = _vd_raw[0] | _vd_raw[1] << 8
        except (OSError, AttributeError):
            _tv_view = None
        try:
            _tv_flag = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_FLAG_OFFSET, 1)[0]
        except (OSError, AttributeError):
            _tv_flag = None
        try:
            _tv_ptr = getattr(_shop_state, 'ptr', None) if _shop_state is not None else None
        except AttributeError:
            _tv_ptr = None
        if _is_tavern_ctx and _tv_sub_key:
            try:
                _conv_label = _conv_label + i18n.tr(_tv_sub_key)
            except (AttributeError, ImportError):
                pass
        _tv_npcconv = bool(getattr(w, '_npc_conversation_active', False))
        _tv_sess = _active_session_name_for_label or ''
        _tv_dbg_key = (_is_tavern_ctx, _tv_sub_key, _tv_shop_kind, _tv_owner_kind, _tv_surface, _tv_owner, _tv_cands, _shop_img_name or '', _tv_npcconv, _tv_sess)
        if _tv_dbg_key != getattr(w, '_tavern_view_dbg_key', None):
            w._tavern_view_dbg_key = _tv_dbg_key
            _log.warning('tavern view dbg: sub=%s view(+0x8F6E)=%s flag(+0x8F74)=%s shop_kind=%s owner_kind=%r surface=%r owner=%r ptr=%s img=%r cands=[%s] npcconv=%s sess=%r recov=%s ctx_tavern=%s', _tv_sub_key.rsplit('.', 1)[-1] if _tv_sub_key else 'none', f'0x{_tv_view:04X}' if _tv_view is not None else 'None', f'0x{_tv_flag:02X}' if _tv_flag is not None else 'None', _tv_shop_kind, _tv_owner_kind, _tv_surface, _tv_owner, f'0x{_tv_ptr:04X}' if _tv_ptr is not None else 'None', _shop_img_name, _tv_cands, _tv_npcconv, _tv_sess, getattr(w, '_yesno_menu_recovery_last', False), _is_tavern_ctx)
        w._tavern_view_dbg_prev_ctx = _is_tavern_ctx
    return _conv_label
_temple_sub_state_label = temple_sub_state_label
_tavern_sub_state_label = tavern_sub_state_label

def build_connection_bar_label(w, _screen_id, _screen_name, _img_name, _resolved_area, _shop_img_name, _shop_state, in_interior):
    if getattr(w, '_travel_l4_active', False):
        _screen_id = 'game_screen'
        _screen_name = i18n.tr('screen.game_screen')
    from play_area_classifier import area_suffix_ja
    _suffix_area = _resolved_area
    if _screen_id == 'game_screen' and _suffix_area == 'dungeon':
        _floor_label = getattr(w, '_dungeon_floor_label', '') or ''
        if _floor_label:
            _screen_name += area_suffix_ja(_suffix_area, floor_label=_floor_label)
    w._loading_data_select_active = _screen_id == 'loadsave_in_play'
    if w._loading_data_select_active:
        _screen_name = i18n.tr('screen.loadsave_in_play')
    elif w._loading_state_active:
        _screen_name = i18n.tr('screen.loading_in_play')
    _top_state = _current_top_level(w)
    _area = _resolved_area
    _travel_l4_active_for_label = bool(getattr(w, '_travel_l4_active', False))
    _screen_suppresses_conversation_label = _travel_l4_active_for_label or _screen_id in ('system_menu', 'loadsave_in_play', 'automap', 'logbook')
    _active_session_for_label = None
    try:
        if not _screen_suppresses_conversation_label:
            _active_session_for_label = w._session_manager.active_session()
    except (AttributeError, ImportError):
        _active_session_for_label = None
    _hierarchy_for_label = SeparationHierarchy.from_parts(top_level_state=_top_state, c_area=_area, in_interior=in_interior, npc_active=False if _screen_suppresses_conversation_label else bool(getattr(w, '_npc_conversation_active', False)) or _active_session_for_label is not None)
    _indicator = _hierarchy_for_label.indicator
    _active_session_name_for_label = ''
    if _active_session_for_label is not None:
        _active_session_name_for_label = _active_session_for_label.name
    _facility_label = ''
    _facility_key = ''
    try:
        from controllers.recognition_label import facility_recognition_key, known_facility_kind
        _shop_owner_for_label = getattr(_shop_state, 'owner_kind', '') if _shop_state is not None else ''
        if not in_interior:
            w._interior_facility_kind = ''
        else:
            _kind = known_facility_kind(_active_session_name_for_label, _shop_owner_for_label)
            if _kind:
                w._interior_facility_kind = _kind
        _facility_key = facility_recognition_key(getattr(w, '_interior_mif_name', None) or '', in_interior, active_session_name=_active_session_name_for_label, shop_owner_kind=_shop_owner_for_label, persisted_facility_kind=getattr(w, '_interior_facility_kind', '') or '', area=_area or '')
        if _facility_key:
            _facility_label = i18n.tr(_facility_key)
    except (AttributeError, ImportError):
        pass
    _conv_label = ''
    try:
        if _active_session_name_for_label:
            if _active_session_name_for_label == 'tavern':
                _conv_label = i18n.tr('recognition.conv_shop_owner')
            elif _active_session_name_for_label == 'temple':
                _conv_label = i18n.tr('recognition.conv_priest')
            elif _active_session_name_for_label == 'negotiation':
                _conv_label = i18n.tr('recognition.conv_negotiation')
            elif _active_session_name_for_label == 'npc_chat':
                _conv_label = i18n.tr('recognition.conv_npc')
            elif _active_session_name_for_label == 'equipment':
                _conv_label = i18n.tr('recognition.conv_shop_owner')
            elif _active_session_name_for_label == 'mages_guild':
                _conv_label = i18n.tr('recognition.conv_shop_owner')
        elif not _screen_suppresses_conversation_label and (getattr(w, '_npc_conversation_active', False) or _screen_id == 'npc_dialog'):
            _conv_label = i18n.tr('recognition.conv_npc')
    except (AttributeError, ImportError):
        pass
    if _facility_key == 'recognition.facility_equipment' and _active_session_name_for_label == 'equipment':
        try:
            from controllers.recognition_label import equipment_sub_state_key
            from normal_play.equipment_l4_state import peek_equipment_l4_state
            _eq_snap = peek_equipment_l4_state(w)
            _eq_state = _eq_snap.state if _eq_snap is not None else ''
            _eq_surface = getattr(w, '_active_tmpl_surface_kind_prev', '') or ''
            _eq_sub_key = equipment_sub_state_key(_eq_state, active_template_surface=_eq_surface, img_name=_shop_img_name, negot_counter_active=bool(getattr(w, '_equipment_negot_counter_active', False)))
            if _eq_sub_key:
                _conv_label = _conv_label + i18n.tr(_eq_sub_key)
        except (AttributeError, ImportError):
            pass
    if _facility_key == 'recognition.facility_mages' and _active_session_name_for_label == 'mages_guild':
        try:
            from controllers.recognition_label import mages_sub_state_key
            _mg_owner = getattr(w, '_panel_owner', '') or ''
            _mg_sub_key = mages_sub_state_key(_mg_owner, _shop_img_name, getattr(w, '_mages_list_title_en', '') or '')
            if _mg_sub_key:
                _conv_label = _conv_label + i18n.tr(_mg_sub_key)
        except (AttributeError, ImportError):
            pass
    _is_temple_ctx = _facility_key == 'recognition.facility_temple'
    _conv_label = _temple_sub_state_label(w, _conv_label, _is_temple_ctx, _active_session_name_for_label, _screen_suppresses_conversation_label, _resolved_area, _shop_img_name, _shop_state)
    _is_tavern_ctx = _facility_key == 'recognition.facility_tavern'
    _conv_label = _tavern_sub_state_label(w, _conv_label, _is_tavern_ctx, _active_session_name_for_label, _shop_img_name, _shop_state)
    if not _conv_label:
        _travel_label_key = {'region_select': 'recognition.travel_region', 'detail': 'recognition.travel_detail', 'hover_name': 'recognition.travel_detail', 'estimate': 'recognition.travel_estimate', 'input': 'recognition.travel_input', 'list': 'recognition.travel_list'}.get(getattr(w, '_travel_l4_state', 'none'))
        if _travel_label_key:
            try:
                _conv_label = i18n.tr(_travel_label_key)
            except (AttributeError, ImportError):
                pass
    w._anchor_lbl.setText(i18n.tr('connection.img_info', img=_img_name or '—'))
    return (_screen_id, _screen_name, _indicator, _facility_label, _conv_label)
__all__ = ['build_connection_bar_label', 'temple_sub_state_label', 'tavern_sub_state_label']
