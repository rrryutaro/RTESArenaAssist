from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
NEGOTIATION_IMG = 'NEGOTBUT.IMG'
CONFIRM_IMG = 'YESNO.IMG'
_TEMPLATE_TABLES: dict = {}

def own_template_table():
    if 'own' not in _TEMPLATE_TABLES:
        from active_template_reader import build_template_table
        from session.tavern_node import TavernNode
        _TEMPLATE_TABLES['own'] = build_template_table(TavernNode.template_declarations)
    return _TEMPLATE_TABLES['own']

def signal_template_table():
    if 'signal' not in _TEMPLATE_TABLES:
        from active_template_reader import COUNTER_OFFER_DECLARATIONS, build_template_table
        from session.tavern_node import TavernNode
        _TEMPLATE_TABLES['signal'] = build_template_table(TavernNode.template_declarations, COUNTER_OFFER_DECLARATIONS)
    return _TEMPLATE_TABLES['signal']

def yesno_menu_back_of(shop_state) -> bool:
    from active_template_reader import template_table_pointers
    from shop_popup_detector import yesno_menu_back
    return yesno_menu_back(shop_state, template_table_pointers(signal_template_table()))

def input_prompt_label(candidate) -> str:
    from active_template_reader import COUNTER_OFFER_TABLE, input_prompt_kind
    if input_prompt_kind(candidate, own_template_table()):
        return 'tavern'
    if input_prompt_kind(candidate, COUNTER_OFFER_TABLE):
        return 'negotiation'
    return ''
_LISTS_CACHE: list = [None, None]

def tavern_lists_of(shop_state, analyzer, anchor) -> tuple[list, object, list]:
    if shop_state is None or not getattr(shop_state, 'gate_open', False) or analyzer is None:
        return ([], None, [])
    cached = _LISTS_CACHE[0]
    if cached is not None and cached[0] is shop_state and (cached[1] is analyzer) and (cached[2] == anchor):
        return _LISTS_CACHE[1]
    from session.tavern_node import TAVERN_NODE
    buy_items, buy_span = TAVERN_NODE.read_shop_buy_span(analyzer, anchor)
    rooms = TAVERN_NODE.read_room_items(analyzer, anchor)
    result = (list(buy_items or []), buy_span, list(rooms or []))
    _LISTS_CACHE[0] = (shop_state, analyzer, anchor)
    _LISTS_CACHE[1] = result
    return result

def own_surface_of(shop_state, analyzer, anchor, *, l3_by_mif: bool) -> tuple[str, str, bool]:
    if shop_state is None or not getattr(shop_state, 'gate_open', False):
        return ('none', '', False)
    from session.tavern_node import TAVERN_NODE, TavernNode
    from shop_popup_detector import ptr_group_signature_entry_of
    entry = ptr_group_signature_entry_of(shop_state, TavernNode.menu_signatures, menu_back_on_yesno=yesno_menu_back_of(shop_state))
    newpop = bool(getattr(shop_state, 'newpop_fg', False))
    on_menu = entry is not None and entry[0] == 'shop_menu'
    drinks = getattr(shop_state, 'price_cache', None) == TAVERN_NODE.DRINKS_PRICE_CACHE_SIG
    buy_items, _buy_span, room_items = tavern_lists_of(shop_state, analyzer, anchor) if newpop else ([], None, [])
    if newpop and on_menu and drinks and buy_items:
        return ('shop_buy', '', True)
    if newpop and (not drinks) and room_items:
        if on_menu and is_room_list_context(shop_state, l3_by_mif=l3_by_mif):
            return ('shop_rooms', '', True)
        return ('none', '', False)
    if entry is not None:
        return (entry[0], entry[1], True)
    return ('none', '', False)

def is_room_list_context(shop_state, *, l3_by_mif: bool) -> bool:
    active = (getattr(shop_state, 'active_facility_name', '') or '').lower()
    other_facility_conversation = bool(active) and active != 'tavern'
    return not other_facility_conversation and (active == 'tavern' or bool(l3_by_mif))

def shop_kind_facility_of(shop_state, analyzer, anchor, *, l3_by_mif: bool) -> tuple[str, str]:
    return kind_facility_of_surface(own_surface_of(shop_state, analyzer, anchor, l3_by_mif=l3_by_mif))

def kind_facility_of_surface(surface) -> tuple[str, str]:
    kind = surface[0]
    if kind == 'none':
        return ('none', '')
    return (kind, 'tavern')

def tavern_surface_of(w, shop_state) -> tuple[str, str, bool]:
    seq = getattr(w, '_poll_seq', None)
    memo = getattr(w, '_tavern_surface_memo', None)
    if isinstance(seq, int) and isinstance(memo, tuple) and (len(memo) == 3) and (memo[0] == seq) and (memo[1] is shop_state):
        return memo[2]
    from l3_facility import l3_decided_by_mif
    surface = own_surface_of(shop_state, getattr(w, '_analyzer', None), getattr(w, '_anchor', 0), l3_by_mif=l3_decided_by_mif(w))
    if isinstance(seq, int):
        w._tavern_surface_memo = (seq, shop_state, surface)
    return surface

@dataclass
class TavernSignals:
    in_interior: bool = False
    facility_tavern: bool = False
    shop_kind: str = 'none'
    shop_facility: str = ''
    img: str = ''
    active_surfaces: frozenset = field(default_factory=frozenset)
    cur_ptr_surface: str = ''
    negotiation_body: bool = False
    counter_active: bool = False
    npc_response_hit: bool = False
    rumor_marker: bool = False

    @property
    def img_negotiation(self) -> bool:
        return (self.img or '').upper() == NEGOTIATION_IMG

    @property
    def img_confirm(self) -> bool:
        return (self.img or '').upper() == CONFIRM_IMG

def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default

def observe_ask_about(analyzer, anchor):
    try:
        from arena_bridge import read_ask_about_menu
        from ask_about_menu_parser import parse_menu, detect_active_sub_menu_title
        from popup11_list_detector import read_active_menu_marker
        marker = read_active_menu_marker(analyzer, anchor)
        raw = read_ask_about_menu(analyzer, anchor)
        parsed = parse_menu(raw)
        title = detect_active_sub_menu_title(parsed, marker)
        return (marker, parsed, title)
    except Exception:
        return (None, None, None)

def gather_tavern_signals(analyzer, anchor: int, *, shop_kind: str, shop_facility: str, img: str, in_interior: bool, facility_tavern: bool, npc_phase: Optional[int]=None, ask_about_obs=None) -> TavernSignals:
    img_u = (img or '').upper()
    active_surfaces: set = set()
    cur_ptr_surface = ''
    try:
        from active_template_reader import read_active_template_candidates, template_surface_kind
        _table = signal_template_table()
        cands = read_active_template_candidates(analyzer, anchor)
        for c in cands:
            k = _safe(lambda: template_surface_kind(c, _table) or '', '')
            if k:
                active_surfaces.add(k)
                if getattr(c, 'source', '') == 'current_ptr' and (not cur_ptr_surface):
                    cur_ptr_surface = k
    except Exception:
        active_surfaces = set()
        cur_ptr_surface = ''
    counter_active = 'negotiation_counter' in active_surfaces
    negotiation_body = False
    try:
        from negotiation_reader import read_negotiation_diagnostic
        _raw, _canon, _rendered, _text = read_negotiation_diagnostic(analyzer, anchor)
        if _text:
            import npc_dialog_lookup as _ndl
            negotiation_body = bool(_safe(lambda: _ndl.lookup(_text), None))
    except Exception:
        negotiation_body = False
    npc_response_hit = False
    try:
        from popup11_response_reader import read_response_candidates_all, read_current_text_pointer as _rcp, candidate_contains_pointer
        _rc = read_response_candidates_all(analyzer, anchor)
        _ptr = _safe(lambda: _rcp(analyzer, anchor), None)
        npc_response_hit = any((c.text and c.lookup_hit and candidate_contains_pointer(c, _ptr) for c in _rc))
    except Exception:
        npc_response_hit = False
    rumor_marker = False
    try:
        from .npc_chat_session import NPC_PHASE_ASKING
        if npc_phase == NPC_PHASE_ASKING:
            obs = ask_about_obs if ask_about_obs is not None else observe_ask_about(analyzer, anchor)
            marker, _parsed, title = obs
            rumor_marker = bool(marker) and title == 'Rumor Type'
    except Exception:
        rumor_marker = False
    return TavernSignals(in_interior=bool(in_interior), facility_tavern=bool(facility_tavern), shop_kind=shop_kind or 'none', shop_facility=shop_facility or '', img=img_u, active_surfaces=frozenset(active_surfaces), cur_ptr_surface=cur_ptr_surface, negotiation_body=negotiation_body, counter_active=counter_active, npc_response_hit=npc_response_hit, rumor_marker=rumor_marker)
__all__ = ['TavernSignals', 'NEGOTIATION_IMG', 'CONFIRM_IMG', 'gather_tavern_signals', 'observe_ask_about']
