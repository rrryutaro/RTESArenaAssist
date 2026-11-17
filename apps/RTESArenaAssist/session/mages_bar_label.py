from __future__ import annotations
_MAGES_KIND_SUB_KEYS = {'menu': 'recognition.mages_sub_menu', 'spellmaker': 'recognition.mages_sub_spellmaker', 'effect_menu': 'recognition.mages_sub_spellmaker_edit_effects', 'spelldetail': 'recognition.mages_sub_spelldetail', 'prompt': 'recognition.mages_sub_prompt', 'confirm': 'recognition.mages_sub_confirm', 'negotiation': 'recognition.mages_sub_negotiation', 'reply': 'recognition.mages_sub_response'}
_MAGES_LIST_TITLE_SUB_KEYS = {'Targets': 'recognition.mages_sub_spellmaker_targets', 'Effects': 'recognition.mages_sub_spellmaker_effects', 'Effect Options': 'recognition.mages_sub_spellmaker_effect_options', 'Spells': 'recognition.mages_sub_buy_spells', 'Potions': 'recognition.mages_sub_buy_potions', 'Magic Items': 'recognition.mages_sub_magic_items', 'Inventory': 'recognition.mages_sub_inventory'}

def mages_sub_state_key(view, list_title: str='') -> str:
    kind = str(getattr(view, 'l4_kind', '') or '')
    if kind == 'list':
        return _MAGES_LIST_TITLE_SUB_KEYS.get((list_title or '').strip(), 'recognition.mages_sub_list')
    return _MAGES_KIND_SUB_KEYS.get(kind, '')

def mages_bar_sub_label_key(w, *, active_session_name: str) -> str:
    if active_session_name != 'mages_guild':
        return ''
    return mages_sub_state_key(getattr(w, '_mages_view_now', None), getattr(w, '_mages_list_title_en', '') or '')
