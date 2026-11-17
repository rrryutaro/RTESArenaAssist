from __future__ import annotations
import logging
import i18n_helper as i18n
from hierarchy_state import SeparationHierarchy
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('poll_controller')

def build_connection_bar_label(w, _screen_id, _screen_name, _img_name, _resolved_area, _shop_img_name, _shop_state, in_interior, *, loading_active: bool=False):
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
    elif loading_active:
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
        from controllers.recognition_label import facility_key_of
        _facility_key = facility_key_of(getattr(w, '_l3_facility', '') or '', in_interior, area=_area or '')
        if _facility_key:
            _facility_label = i18n.tr(_facility_key)
    except (AttributeError, ImportError):
        pass
    _conv_label = ''
    try:
        if _active_session_for_label is not None:
            _conv_key = getattr(_active_session_for_label, 'bar_label_key', '') or ''
            if _conv_key:
                _conv_label = i18n.tr(_conv_key)
        elif not _screen_suppresses_conversation_label and (getattr(w, '_npc_conversation_active', False) or _screen_id == 'npc_dialog'):
            _conv_label = i18n.tr('recognition.conv_npc')
    except (AttributeError, ImportError):
        pass
    if _facility_key:
        try:
            from l3_facility import l3_node
            _node = l3_node(w)
            if _node is not None:
                _sub_key = _node.bar_sub_label_key(w, active_session_name=_active_session_name_for_label, screen_suppresses_conversation_label=_screen_suppresses_conversation_label, img_name=_shop_img_name)
                if _sub_key:
                    _conv_label = _conv_label + i18n.tr(_sub_key)
        except (AttributeError, ImportError):
            pass
    if not _conv_label:
        _travel_label_key = {'region_select': 'recognition.travel_region', 'detail': 'recognition.travel_detail', 'hover_name': 'recognition.travel_detail', 'estimate': 'recognition.travel_estimate', 'input': 'recognition.travel_input', 'list': 'recognition.travel_list'}.get(getattr(w, '_travel_l4_state', 'none'))
        if _travel_label_key:
            try:
                _conv_label = i18n.tr(_travel_label_key)
            except (AttributeError, ImportError):
                pass
    w._anchor_lbl.setText(i18n.tr('connection.img_info', img=_img_name or '—'))
    return (_screen_id, _screen_name, _indicator, _facility_label, _conv_label)
__all__ = ['build_connection_bar_label']
