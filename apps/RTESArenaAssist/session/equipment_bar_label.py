from __future__ import annotations
from screen_img_signals import YESNO_IMG
_EQUIPMENT_STATE_SUB_KEYS = {'menu': 'recognition.equipment_sub_menu', 'buy_list': 'recognition.equipment_sub_list', 'item_select': 'recognition.equipment_sub_list', 'repair_entry': 'recognition.equipment_sub_repair_entry', 'repair_jobs': 'recognition.equipment_sub_repair_jobs', 'repair_status_reply': 'recognition.equipment_sub_repair_status', 'repair_done_reply': 'recognition.equipment_sub_repair_done', 'repair_estimate': 'recognition.equipment_sub_repair_estimate', 'reply': 'recognition.equipment_sub_response'}

def equipment_sub_state_key(l4_state, *, active_template_surface: str='', img_name: str='', negot_counter_active: bool=False) -> str:
    state = str(getattr(l4_state, 'value', l4_state) or '')
    img = (img_name or '').upper()
    surface = active_template_surface or ''
    if negot_counter_active or surface == 'negotiation_counter':
        return 'recognition.equipment_sub_amount_counter'
    if state == 'negotiation':
        if img == YESNO_IMG:
            return 'recognition.equipment_sub_final_confirm'
        return 'recognition.equipment_sub_amount_present'
    return _EQUIPMENT_STATE_SUB_KEYS.get(state, '')

def equipment_bar_sub_label_key(w, *, active_session_name: str, img_name: str) -> str:
    if active_session_name != 'equipment':
        return ''
    from normal_play.equipment_l4_state import peek_equipment_l4_state
    _eq_snap = peek_equipment_l4_state(w)
    _eq_state = _eq_snap.state if _eq_snap is not None else ''
    from active_template_reader import COUNTER_OFFER_TABLE, surface_kind_of_pointer
    _eq_surface = surface_kind_of_pointer(getattr(w, '_active_tmpl_selected_ptr_prev', None), COUNTER_OFFER_TABLE)
    return equipment_sub_state_key(_eq_state, active_template_surface=_eq_surface, img_name=img_name, negot_counter_active=bool(getattr(w, '_equipment_negot_counter_active', False)))
