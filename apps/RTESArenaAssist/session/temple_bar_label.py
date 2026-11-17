from __future__ import annotations
_TEMPLE_SURFACE_SUB_KEYS = {'temple_donate_amount': 'recognition.temple_sub_donate_amount', 'tavern_cost_show': 'recognition.temple_sub_cost_show', 'tavern_cost_confirm': 'recognition.temple_sub_cost_confirm'}

def temple_sub_state_key(active_template_surface: str, panel_owner: str, img_name: str='', current_text: str='') -> str:
    owner = panel_owner or ''
    img = (img_name or '').upper()
    surface = active_template_surface or ''
    text = ' '.join((current_text or '').split())
    if owner == 'temple_menu':
        return 'recognition.temple_sub_menu'
    if owner == 'temple_cure':
        return 'recognition.temple_sub_curing'
    if owner == 'temple_prompt':
        return 'recognition.temple_sub_donate_amount'
    if owner == 'temple_cost':
        if surface == 'tavern_cost_confirm' or img == 'YESNO.IMG':
            return 'recognition.temple_sub_cost_confirm'
        return 'recognition.temple_sub_cost_show'
    if owner == 'temple_priest_reply':
        if text.startswith('Receive our blessings'):
            return 'recognition.temple_sub_bless_result'
        if text.startswith('Curing '):
            return 'recognition.temple_sub_curing'
        if 'thou art healed' in text or 'is in perfect condition' in text:
            return 'recognition.temple_sub_heal_result'
        if text.startswith('We humbly beg your forgivness'):
            return 'recognition.temple_sub_cure_result'
        return 'recognition.temple_sub_response'
    if owner == 'active_template':
        return _TEMPLE_SURFACE_SUB_KEYS.get(surface, '')
    return ''

def temple_bar_sub_label_key(w, *, active_session_name: str, screen_suppresses_conversation_label: bool, img_name: str) -> str:
    try:
        _temple_owner = getattr(w, '_panel_owner', '') or ''
        _temple_surface = ''
        if _temple_owner in ('temple_cost', 'temple_prompt'):
            _temple_surface = getattr(w, '_temple_cost_current_surface', '') or ''
            _temple_text = getattr(w, '_temple_cost_current_text', '') or ''
        elif _temple_owner == 'temple_priest_reply':
            _temple_text = getattr(w, '_temple_dialog_current_text', '') or ''
        else:
            from active_template_reader import surface_kind_of_pointer
            from temple_signals import template_table
            _temple_surface = surface_kind_of_pointer(getattr(w, '_active_tmpl_selected_ptr_prev', None), template_table())
            _temple_text = ''
        _temple_sub_key = temple_sub_state_key(_temple_surface, _temple_owner, img_name, _temple_text)
    except AttributeError:
        _temple_sub_key = ''
    _temple_label_active = active_session_name == 'temple' or (not screen_suppresses_conversation_label and bool(getattr(w, '_field_temple_active_now', False)))
    if _temple_label_active and _temple_sub_key:
        return _temple_sub_key
    return ''
