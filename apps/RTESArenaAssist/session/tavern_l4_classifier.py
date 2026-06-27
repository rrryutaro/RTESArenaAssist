from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
_SURFACE_TO_L4 = {'tavern_stay_days': 'stay_days', 'tavern_sneak_confirm': 'sneak_confirm', 'tavern_cost_confirm': 'cost_confirm', 'tavern_sneak_result': 'result', 'tavern_room_contract': 'result', 'tavern_cost_show': 'result'}
_YESNO_L4_KINDS = frozenset({'stay_days', 'sneak_confirm', 'cost_confirm'})
_YESNO_CONFIRM_SURFACES = frozenset({'tavern_sneak_confirm', 'tavern_cost_confirm'})
OWNER_TAVERN_YESNO = 'tavern_yesno'
OWNER_TAVERN_NEGOT = 'tavern_negotiation'
OWNER_TAVERN_RUMOR = 'tavern_rumor_type'

@dataclass
class L4ActiveSlotCandidate:
    surface_kind: str
    matches_current_ptr: bool

@dataclass
class TavernL4Result:
    kind: str
    reason: str
    release_owners: list = field(default_factory=list)
    selected_surface_kind: str = ''

def classify_tavern_l4(*, in_interior: bool, facility_known_tavern: bool, img_name: str, cur_ptr: Optional[int], shop_menu_group_ptrs: frozenset, active_slot_candidates: list, body_present: bool, prompts_present: bool, has_npc_response: bool, rumor_type_marker_visible: bool=False) -> TavernL4Result:
    img_upper = (img_name or '').upper()
    if not in_interior or not facility_known_tavern:
        return TavernL4Result(kind='none', reason='not_in_tavern', release_owners=[OWNER_TAVERN_YESNO, OWNER_TAVERN_NEGOT, OWNER_TAVERN_RUMOR])
    if img_upper == 'YESNO.IMG' and cur_ptr is not None and (cur_ptr in shop_menu_group_ptrs):
        for c in active_slot_candidates:
            if c.surface_kind in _YESNO_CONFIRM_SURFACES:
                l4 = _SURFACE_TO_L4[c.surface_kind]
                return TavernL4Result(kind=l4, reason='yesno_confirm_over_menu_ptr', release_owners=[OWNER_TAVERN_NEGOT, OWNER_TAVERN_RUMOR], selected_surface_kind=c.surface_kind)
    if cur_ptr is not None and cur_ptr in shop_menu_group_ptrs:
        return TavernL4Result(kind='menu', reason='current_ptr_menu', release_owners=[OWNER_TAVERN_YESNO, OWNER_TAVERN_NEGOT])
    if rumor_type_marker_visible:
        return TavernL4Result(kind='rumor_type', reason='rumor_type_marker', release_owners=[OWNER_TAVERN_YESNO, OWNER_TAVERN_NEGOT])
    if img_upper in ('NEGOTBUT.IMG', 'YESNO.IMG'):
        if body_present or prompts_present:
            return TavernL4Result(kind='negotiation', reason='negotiation_body_or_prompts', release_owners=[OWNER_TAVERN_YESNO, OWNER_TAVERN_RUMOR])
    selected_cur_ptr_match = None
    selected_active_slot_only = None
    for c in active_slot_candidates:
        l4 = _SURFACE_TO_L4.get(c.surface_kind)
        if l4 is None:
            continue
        if c.matches_current_ptr and selected_cur_ptr_match is None:
            selected_cur_ptr_match = c
        elif not c.matches_current_ptr and selected_active_slot_only is None:
            selected_active_slot_only = c
    if selected_cur_ptr_match is not None:
        l4 = _SURFACE_TO_L4[selected_cur_ptr_match.surface_kind]
        return TavernL4Result(kind=l4, reason='current_ptr_match', release_owners=[OWNER_TAVERN_NEGOT, OWNER_TAVERN_RUMOR], selected_surface_kind=selected_cur_ptr_match.surface_kind)
    if selected_active_slot_only is not None:
        if img_upper in ('YESNO.IMG', 'NEWPOP.IMG'):
            l4 = _SURFACE_TO_L4[selected_active_slot_only.surface_kind]
            return TavernL4Result(kind=l4, reason='active_slot', release_owners=[OWNER_TAVERN_NEGOT, OWNER_TAVERN_RUMOR], selected_surface_kind=selected_active_slot_only.surface_kind)
    if has_npc_response:
        return TavernL4Result(kind='npc_response', reason='npc_response', release_owners=[OWNER_TAVERN_YESNO, OWNER_TAVERN_NEGOT, OWNER_TAVERN_RUMOR])
    return TavernL4Result(kind='none', reason='no_visible_l4', release_owners=[OWNER_TAVERN_YESNO, OWNER_TAVERN_NEGOT, OWNER_TAVERN_RUMOR])
__all__ = ['L4ActiveSlotCandidate', 'TavernL4Result', 'classify_tavern_l4', 'OWNER_TAVERN_YESNO', 'OWNER_TAVERN_NEGOT', 'OWNER_TAVERN_RUMOR']
