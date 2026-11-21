from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
from .tavern_signals import TavernSignals
_L4_OWNER_BAR: dict[str, tuple[str, str]] = {'menu': ('shop_menu', 'recognition.tavern_sub_menu'), 'drinks': ('shop_buy', 'recognition.tavern_sub_drinks'), 'rooms': ('shop_buy', 'recognition.tavern_sub_rooms'), 'rumor_type': ('', 'recognition.tavern_sub_rumor_type'), 'stay_days': ('active_template', 'recognition.tavern_sub_stay_days'), 'sneak_confirm': ('active_template', 'recognition.tavern_sub_sneak_confirm'), 'sneak_result': ('active_template', 'recognition.tavern_sub_sneak_result'), 'room_contract': ('active_template', 'recognition.tavern_sub_room_contract'), 'cost_show': ('active_template', 'recognition.tavern_sub_cost_show'), 'cost_confirm': ('active_template', 'recognition.tavern_sub_cost_confirm'), 'amount_present': ('negotiation', 'recognition.tavern_sub_amount_present'), 'amount_counter': ('negotiation', 'recognition.tavern_sub_amount_counter'), 'final_confirm': ('negotiation', 'recognition.tavern_sub_final_confirm'), 'response': ('npc_dialog', 'recognition.tavern_sub_response'), 'none': ('', '')}
SESSION_RUMOR_TYPE_OWNER = 'tavern_rumor_type'
_SHOP_KIND_TO_L4 = {'shop_menu': 'menu', 'shop_buy': 'drinks', 'shop_rooms': 'rooms', 'shop_rumor_type': 'rumor_type'}
_SURFACE_TO_L4 = {'tavern_stay_days': 'stay_days', 'tavern_sneak_confirm': 'sneak_confirm', 'tavern_sneak_result': 'sneak_result', 'tavern_room_contract': 'room_contract', 'tavern_cost_show': 'cost_show', 'tavern_cost_confirm': 'cost_confirm'}
_SURFACE_PRIORITY = ('tavern_sneak_confirm', 'tavern_cost_confirm', 'tavern_sneak_result', 'tavern_room_contract', 'tavern_cost_show', 'tavern_stay_days')
_AT_YESNO_SURFACES = frozenset({'tavern_sneak_confirm', 'tavern_cost_confirm', 'tavern_sneak_result', 'tavern_room_contract', 'tavern_cost_show'})

@dataclass
class TavernView:
    l4_kind: str
    render_owner: str
    bar_key: str
    l4_visible: bool
    l4_start: bool
    reason: str = ''
    continues: bool = False
    session_draws_rumor_type: bool = False

def _pick_surface(s: TavernSignals) -> str:
    if s.cur_ptr_surface in _SURFACE_TO_L4:
        return s.cur_ptr_surface
    for k in _SURFACE_PRIORITY:
        if k in s.active_surfaces:
            return k
    return ''

def _shop_l4(s: TavernSignals) -> str:
    return _SHOP_KIND_TO_L4.get(s.shop_kind, '')

def conversation_starts(shop_kind: str, shop_facility: str) -> bool:
    return shop_facility == 'tavern' and (shop_kind or '') in _SHOP_KIND_TO_L4

def l4_of_shop_kind(shop_kind: str) -> str:
    return _SHOP_KIND_TO_L4.get(shop_kind or '', '')

def shop_row_owner_of(l4_kind: str) -> str:
    if l4_kind not in _SHOP_KIND_TO_L4.values():
        return ''
    if l4_kind == 'rumor_type':
        return 'shop_rumor_type'
    return _L4_OWNER_BAR[l4_kind][0]

def _has_at_yesno(s: TavernSignals) -> bool:
    return bool(s.active_surfaces & _AT_YESNO_SURFACES)
TAVERN_DECISION_TABLE = (('not_in_tavern', lambda s: not s.in_interior or not s.facility_tavern, 'none', None), ('shop_kind', lambda s: conversation_starts(s.shop_kind, s.shop_facility), _shop_l4, lambda s: shop_row_owner_of(_shop_l4(s))), ('counter', lambda s: s.counter_active, 'amount_counter', None), ('negotiation_negotbut', lambda s: s.negotiation_body and s.img_negotiation, 'amount_present', None), ('negotiation_yesno', lambda s: s.negotiation_body and s.img_confirm and (not _has_at_yesno(s)), 'final_confirm', None), ('surface', lambda s: bool(_pick_surface(s)), lambda s: _SURFACE_TO_L4[_pick_surface(s)], None), ('rumor_marker', lambda s: s.rumor_marker, 'rumor_type', SESSION_RUMOR_TYPE_OWNER), ('npc_response', lambda s: s.npc_response_hit, 'response', None), ('no_visible_l4', lambda s: True, 'none', None))

def conversation_continues(s: TavernSignals, l4_kind: str) -> bool:
    return l4_kind != 'none' or s.img_negotiation

def classify_tavern_signals(signals: TavernSignals) -> TavernView:
    s = signals
    img = (s.img or '').upper()
    if img != s.img:
        s = TavernSignals(**{**s.__dict__, 'img': img})
    l4_start = conversation_starts(s.shop_kind, s.shop_facility)
    for name, cond, kind_of, owner_of in TAVERN_DECISION_TABLE:
        if not cond(s):
            continue
        kind = kind_of(s) if callable(kind_of) else kind_of
        owner, bar = _L4_OWNER_BAR[kind]
        override = owner_of(s) if callable(owner_of) else owner_of
        if override is not None:
            owner = override
        reason = name if name != 'surface' else f'surface:{_pick_surface(s)}'
        return TavernView(l4_kind=kind, render_owner=owner, bar_key=bar, l4_visible=kind != 'none', l4_start=l4_start, reason=reason, continues=conversation_continues(s, kind), session_draws_rumor_type=name == 'rumor_marker')
    raise AssertionError('TAVERN_DECISION_TABLE の終端行が成立しない')
__all__ = ['TavernSignals', 'TavernView', 'TAVERN_DECISION_TABLE', 'classify_tavern_signals', 'conversation_continues', 'conversation_starts']
