from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
_L4_OWNER_BAR: dict[str, tuple[str, str]] = {'menu': ('shop_menu', 'recognition.tavern_sub_menu'), 'drinks': ('shop_buy', 'recognition.tavern_sub_drinks'), 'rooms': ('shop_buy', 'recognition.tavern_sub_rooms'), 'rumor_type': ('', 'recognition.tavern_sub_rumor_type'), 'stay_days': ('active_template', 'recognition.tavern_sub_stay_days'), 'sneak_confirm': ('active_template', 'recognition.tavern_sub_sneak_confirm'), 'sneak_result': ('active_template', 'recognition.tavern_sub_sneak_result'), 'room_contract': ('active_template', 'recognition.tavern_sub_room_contract'), 'cost_show': ('active_template', 'recognition.tavern_sub_cost_show'), 'cost_confirm': ('active_template', 'recognition.tavern_sub_cost_confirm'), 'amount_present': ('negotiation', 'recognition.tavern_sub_amount_present'), 'amount_counter': ('negotiation', 'recognition.tavern_sub_amount_counter'), 'final_confirm': ('negotiation', 'recognition.tavern_sub_final_confirm'), 'response': ('npc_dialog', 'recognition.tavern_sub_response'), 'none': ('', '')}
_SHOP_KIND_TO_L4 = {'shop_menu': 'menu', 'shop_buy': 'drinks', 'shop_rooms': 'rooms', 'shop_rumor_type': 'rumor_type'}
_SURFACE_TO_L4 = {'tavern_stay_days': 'stay_days', 'tavern_sneak_confirm': 'sneak_confirm', 'tavern_sneak_result': 'sneak_result', 'tavern_room_contract': 'room_contract', 'tavern_cost_show': 'cost_show', 'tavern_cost_confirm': 'cost_confirm'}
_SURFACE_PRIORITY = ('tavern_sneak_confirm', 'tavern_cost_confirm', 'tavern_sneak_result', 'tavern_room_contract', 'tavern_cost_show', 'tavern_stay_days')
_TAVERN_MENU_SHOP_KINDS = frozenset({'shop_menu', 'shop_buy', 'shop_rooms', 'shop_rumor_type'})
_AT_YESNO_SURFACES = frozenset({'tavern_sneak_confirm', 'tavern_cost_confirm', 'tavern_sneak_result', 'tavern_room_contract', 'tavern_cost_show'})

@dataclass
class TavernSignals:
    in_interior: bool = False
    facility_tavern: bool = False
    shop_kind: str = 'none'
    shop_owner: str = ''
    img: str = ''
    active_surfaces: frozenset = field(default_factory=frozenset)
    cur_ptr_surface: str = ''
    negotiation_body: bool = False
    negotiation_prompts: bool = False
    counter_active: bool = False
    npc_response_hit: bool = False
    rumor_marker: bool = False

@dataclass
class TavernView:
    l4_kind: str
    render_owner: str
    bar_key: str
    l4_visible: bool
    l3_start: bool
    reason: str = ''

def _pick_surface(signals: TavernSignals) -> str:
    if signals.cur_ptr_surface in _SURFACE_TO_L4:
        return signals.cur_ptr_surface
    for s in _SURFACE_PRIORITY:
        if s in signals.active_surfaces:
            return s
    return ''

def classify_tavern_view(signals: TavernSignals) -> TavernView:

    def _mk(kind: str, owner: Optional[str]=None, reason: str='') -> TavernView:
        _owner, _bar = _L4_OWNER_BAR[kind]
        if owner is not None:
            _owner = owner
        return TavernView(l4_kind=kind, render_owner=_owner, bar_key=_bar, l4_visible=kind != 'none', l3_start=signals.shop_owner == 'tavern' and signals.shop_kind in _TAVERN_MENU_SHOP_KINDS, reason=reason)
    if not signals.in_interior or not signals.facility_tavern:
        return _mk('none', reason='not_in_tavern')
    img = (signals.img or '').upper()
    if signals.shop_owner == 'tavern' and signals.shop_kind in _SHOP_KIND_TO_L4:
        l4 = _SHOP_KIND_TO_L4[signals.shop_kind]
        owner = 'shop_rumor_type' if l4 == 'rumor_type' else None
        return _mk(l4, owner=owner, reason='shop_kind')
    if signals.counter_active:
        return _mk('amount_counter', reason='counter')
    _has_at_yesno = bool(signals.active_surfaces & _AT_YESNO_SURFACES)
    if signals.negotiation_body or signals.negotiation_prompts:
        if img == 'NEGOTBUT.IMG':
            return _mk('amount_present', reason='negotiation_negotbut')
        if img == 'YESNO.IMG' and (not _has_at_yesno):
            return _mk('final_confirm', reason='negotiation_yesno')
    _surface = _pick_surface(signals)
    if _surface:
        return _mk(_SURFACE_TO_L4[_surface], reason=f'surface:{_surface}')
    if signals.rumor_marker:
        return _mk('rumor_type', owner='tavern_rumor_type', reason='rumor_marker')
    if signals.npc_response_hit:
        return _mk('response', reason='npc_response')
    return _mk('none', reason='no_visible_l4')
__all__ = ['TavernSignals', 'TavernView', 'classify_tavern_view']
