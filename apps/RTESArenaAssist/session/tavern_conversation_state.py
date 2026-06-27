from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
SHOP_KINDS_TAVERN_MENU = frozenset({'shop_menu', 'shop_rooms', 'shop_buy', 'shop_rumor_type'})
_SURFACE_KIND_TO_L4 = {'tavern_stay_days': 'stay_days', 'tavern_sneak_confirm': 'sneak_confirm', 'tavern_sneak_result': 'sneak_result', 'tavern_room_contract': 'room_contract', 'tavern_cost_show': 'cost_show', 'tavern_cost_confirm': 'cost_confirm'}
_SHOP_KIND_TO_L4 = {'shop_menu': 'menu', 'shop_rooms': 'rooms', 'shop_buy': 'drinks', 'shop_rumor_type': 'rumor_type'}
ALL_L4_KINDS = frozenset({'none', 'menu', 'rooms', 'drinks', 'rumor_type', 'rumor_response', 'stay_days', 'sneak_confirm', 'sneak_result', 'room_contract', 'cost_show', 'cost_confirm', 'negotiation'})

@dataclass
class TavernConvInput:
    shop_kind: str = 'none'
    shop_owner: str = ''
    active_slot_surfaces: list = field(default_factory=list)
    current_ptr_surface: str = ''
    rumor_type_marker_visible: bool = False
    rumor_response_text: str = ''
    negotiation_body_present: bool = False
    negotiation_prompts_present: bool = False
    img_name: str = ''

@dataclass
class TavernConvState:
    l3_active: bool
    l4_kind: str
    l4_reason: str

def classify_l4(inp: TavernConvInput) -> tuple[str, str]:
    img_upper = (inp.img_name or '').upper()
    if inp.shop_owner == 'tavern' and inp.shop_kind in _SHOP_KIND_TO_L4:
        return (_SHOP_KIND_TO_L4[inp.shop_kind], 'shop_state_owner_tavern')
    if inp.rumor_type_marker_visible:
        return ('rumor_type', 'rumor_type_marker')
    if inp.rumor_response_text:
        return ('rumor_response', 'rumor_response_text')
    if inp.negotiation_body_present or inp.negotiation_prompts_present:
        return ('negotiation', 'negotiation_body_or_prompts')
    if inp.current_ptr_surface in _SURFACE_KIND_TO_L4:
        l4 = _SURFACE_KIND_TO_L4[inp.current_ptr_surface]
        return (l4, 'current_ptr_surface')
    if img_upper in ('YESNO.IMG', 'NEWPOP.IMG'):
        for sk in inp.active_slot_surfaces:
            if sk in _SURFACE_KIND_TO_L4:
                return (_SURFACE_KIND_TO_L4[sk], 'active_slot_with_img_support')
    return ('none', 'no_visible_l4')

def is_l3_active(inp: TavernConvInput, prev_state: Optional[TavernConvState]) -> tuple[bool, str]:
    if inp.shop_owner == 'tavern' and inp.shop_kind in SHOP_KINDS_TAVERN_MENU:
        return (True, 'tavern_shop_menu_recognized')
    if prev_state is not None and prev_state.l3_active:
        l4_kind, _ = classify_l4(inp)
        if l4_kind != 'none':
            return (True, 'l4_continuation')
        return (False, 'all_l4_signals_lost')
    return (False, 'no_start_signal')

def classify_tavern_conversation(inp: TavernConvInput, prev_state: Optional[TavernConvState]=None) -> TavernConvState:
    active, l3_reason = is_l3_active(inp, prev_state)
    if not active:
        return TavernConvState(l3_active=False, l4_kind='none', l4_reason=f'l3_inactive({l3_reason})')
    l4_kind, l4_reason = classify_l4(inp)
    return TavernConvState(l3_active=True, l4_kind=l4_kind, l4_reason=l4_reason)
__all__ = ['ALL_L4_KINDS', 'SHOP_KINDS_TAVERN_MENU', 'TavernConvInput', 'TavernConvState', 'classify_l4', 'classify_tavern_conversation', 'is_l3_active']
