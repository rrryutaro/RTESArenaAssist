from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
NEGOTIATION_IMG = 'NEGOTBUT.IMG'
CONFIRM_IMG = 'YESNO.IMG'

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
        cands = read_active_template_candidates(analyzer, anchor)
        for c in cands:
            k = _safe(lambda: template_surface_kind(c) or '', '')
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
