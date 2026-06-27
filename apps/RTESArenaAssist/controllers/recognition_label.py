from __future__ import annotations
from typing import Callable
_FACILITY_PREFIX_KEYS: tuple[tuple[str, str], ...] = (('TAVERN', 'recognition.facility_tavern'), ('TEMPLE', 'recognition.facility_temple'), ('EQUIPMENT', 'recognition.facility_equipment'), ('ARMORS', 'recognition.facility_equipment'), ('EQUIP', 'recognition.facility_equipment'), ('MAGES', 'recognition.facility_mages'), ('MAGE', 'recognition.facility_mages'), ('WCRYPT', 'recognition.facility_crypt'), ('TOWER', 'recognition.facility_tower'), ('BS', 'recognition.facility_house'), ('PALACE', 'recognition.facility_palace'), ('TOWNPAL', 'recognition.facility_palace'), ('VILPAL', 'recognition.facility_palace'))
_SESSION_FACILITY_KEYS = {'tavern': 'recognition.facility_tavern', 'temple': 'recognition.facility_temple', 'equipment': 'recognition.facility_equipment', 'mages_guild': 'recognition.facility_mages', 'palace': 'recognition.facility_palace'}

def resolve_stable_screen_name(stable_id: str, raw_id: str, raw_name: str, tr: Callable[[str], str]) -> str:
    if stable_id == 'npc_dialog':
        return tr('screen.game_screen')
    if stable_id == raw_id:
        return raw_name
    return tr(f'screen.{stable_id}')

def format_recognition_label(screen_name: str, indicator: str, facility_label: str, conv_label: str) -> str:
    if facility_label:
        return f'{indicator}{facility_label}{conv_label}' if indicator else f'{facility_label}{conv_label}'
    return f'{indicator} {screen_name}{conv_label}' if indicator else f'{screen_name}{conv_label}'
_TAVERN_SURFACE_SUB_KEYS = {'tavern_stay_days': 'recognition.tavern_sub_stay_days', 'tavern_sneak_confirm': 'recognition.tavern_sub_sneak_confirm', 'tavern_sneak_result': 'recognition.tavern_sub_sneak_result', 'tavern_room_contract': 'recognition.tavern_sub_room_contract', 'tavern_cost_show': 'recognition.tavern_sub_cost_show', 'tavern_cost_confirm': 'recognition.tavern_sub_cost_confirm'}

def tavern_sub_state_key(shop_kind: str, active_template_surface: str, panel_owner: str, img_name: str='', negot_counter_active: bool=False) -> str:
    owner = panel_owner or ''
    img = (img_name or '').upper()
    surface = active_template_surface or ''
    if negot_counter_active or surface == 'negotiation_counter':
        return 'recognition.tavern_sub_amount_counter'
    if owner == 'active_template':
        return _TAVERN_SURFACE_SUB_KEYS.get(surface, '')
    if owner == 'shop_buy':
        if shop_kind == 'shop_rooms':
            return 'recognition.tavern_sub_rooms'
        return 'recognition.tavern_sub_drinks'
    if owner == 'shop_menu':
        return 'recognition.tavern_sub_menu'
    if owner in ('shop_rumor_type', 'tavern_rumor_type'):
        return 'recognition.tavern_sub_rumor_type'
    if owner == 'negotiation':
        if img == 'YESNO.IMG':
            return 'recognition.tavern_sub_final_confirm'
        return 'recognition.tavern_sub_amount_present'
    if owner == 'npc_dialog':
        return 'recognition.tavern_sub_response'
    return ''
_TEMPLE_SURFACE_SUB_KEYS = {'temple_donate_amount': 'recognition.temple_sub_donate_amount', 'tavern_cost_show': 'recognition.temple_sub_cost_show', 'tavern_cost_confirm': 'recognition.temple_sub_cost_confirm'}

def temple_sub_state_key(active_template_surface: str, panel_owner: str, img_name: str='', current_text: str='') -> str:
    owner = panel_owner or ''
    img = (img_name or '').upper()
    surface = active_template_surface or ''
    text = ' '.join((current_text or '').split())
    if owner == 'temple_menu':
        return 'recognition.temple_sub_menu'
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

def equipment_sub_state_key(active_template_surface: str, panel_owner: str, img_name: str='', negot_counter_active: bool=False) -> str:
    owner = panel_owner or ''
    img = (img_name or '').upper()
    surface = active_template_surface or ''
    if negot_counter_active or surface == 'negotiation_counter':
        return 'recognition.equipment_sub_amount_counter'
    if owner == 'equipment_menu':
        return 'recognition.equipment_sub_menu'
    if owner == 'equipment_list':
        return 'recognition.equipment_sub_list'
    if owner == 'equipment_negotiation':
        if img == 'YESNO.IMG':
            return 'recognition.equipment_sub_final_confirm'
        return 'recognition.equipment_sub_amount_present'
    if owner == 'equipment_reply':
        return 'recognition.equipment_sub_response'
    return ''

def mages_sub_state_key(panel_owner: str, img_name: str='', list_title: str='') -> str:
    owner = panel_owner or ''
    if owner == 'mages_menu':
        return 'recognition.mages_sub_menu'
    if owner == 'mages_list':
        title = (list_title or '').strip()
        if title == 'Targets':
            return 'recognition.mages_sub_spellmaker_targets'
        if title == 'Effects':
            return 'recognition.mages_sub_spellmaker_effects'
        if title == 'Effect Options':
            return 'recognition.mages_sub_spellmaker_effect_options'
        if title == 'Spells':
            return 'recognition.mages_sub_buy_spells'
        if title == 'Potions':
            return 'recognition.mages_sub_buy_potions'
        if title == 'Magic Items':
            return 'recognition.mages_sub_magic_items'
        if title == 'Inventory':
            return 'recognition.mages_sub_inventory'
        return 'recognition.mages_sub_list'
    if owner == 'mages_spellmaker':
        return 'recognition.mages_sub_spellmaker'
    if owner == 'mages_effect_menu':
        return 'recognition.mages_sub_spellmaker_edit_effects'
    if owner == 'mages_spelldetail':
        return 'recognition.mages_sub_spelldetail'
    if owner == 'mages_prompt':
        return 'recognition.mages_sub_prompt'
    if owner == 'mages_confirm':
        return 'recognition.mages_sub_confirm'
    if owner == 'mages_negotiation':
        return 'recognition.mages_sub_negotiation'
    if owner == 'mages_reply':
        return 'recognition.mages_sub_response'
    return ''

def known_facility_kind(*hints: str) -> str:
    for h in hints:
        if (h or '') in _SESSION_FACILITY_KEYS:
            return h
    return ''

def facility_recognition_key(interior_mif_name: str, in_interior: bool, *, active_session_name: str='', shop_owner_kind: str='', persisted_facility_kind: str='') -> str:
    if not in_interior:
        return ''
    u = (interior_mif_name or '').upper()
    for prefix, key in _FACILITY_PREFIX_KEYS:
        if u.startswith(prefix):
            return key
    for hint in (active_session_name, shop_owner_kind, persisted_facility_kind):
        key = _SESSION_FACILITY_KEYS.get(hint or '')
        if key:
            return key
    return 'recognition.facility_other'
__all__ = ['resolve_stable_screen_name', 'format_recognition_label', 'equipment_sub_state_key', 'mages_sub_state_key', 'facility_recognition_key', 'known_facility_kind', 'temple_sub_state_key', 'tavern_sub_state_key']
