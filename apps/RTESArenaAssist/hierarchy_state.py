from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
L1_TO_CODE_NAME = {'pregame': ('A', '起動中'), 'chargen': ('B', 'キャラクター作成中'), 'normal-play': ('C', '通常ゲーム中')}
AREA_TO_BASE_KEY = {'dungeon': 'dungeon', 'city': 'city', 'wilderness': 'wilderness'}
BASE_KEY_TO_AREA = {'dungeon': 'dungeon', 'city': 'city', 'wilderness': 'wilderness'}
AREA_TO_C_CODE_NAME = {'dungeon': ('C1', 'ダンジョン'), 'city': ('C2', '街'), 'wilderness': ('C3', 'フィールド')}
FACILITY_SESSION_BLOCKED_AREAS = frozenset({'dungeon', 'wilderness'})

def is_facility_session_area_blocked(area: Optional[str]) -> bool:
    return (area or '') in FACILITY_SESSION_BLOCKED_AREAS
CONVERSATION_PANEL_OWNERS = frozenset({'npc_dialog', 'npc_conversation', 'npc_message', 'active_template', 'travel_hover_location', 'travel_estimate', 'travel_table', 'travel_search', 'camp_menu', 'camp_prompt', 'equipment_detail', 'equipment_drop_confirm'})
_FACILITY_L4_PANEL_OWNERS: set = set()

def register_facility_l4_panel_owners(owners) -> None:
    _FACILITY_L4_PANEL_OWNERS.update(owners or ())
_REGISTERED_CONVERSATION_PANEL_OWNERS: set = set()

def register_conversation_panel_owners(owners) -> None:
    _REGISTERED_CONVERSATION_PANEL_OWNERS.update((o for o in owners or () if o))

def conversation_panel_owners() -> frozenset:
    return CONVERSATION_PANEL_OWNERS | frozenset(_REGISTERED_CONVERSATION_PANEL_OWNERS)

def area_from_base_location_key(key: Optional[str]) -> str:
    return BASE_KEY_TO_AREA.get(key or '', '')

def base_location_key_from_area(area: Optional[str]) -> str:
    return AREA_TO_BASE_KEY.get(area or '', '')

def _active_session(window, *, require_active: bool=True):
    try:
        session = window._session_manager.active_session()
    except (AttributeError, RuntimeError):
        return None
    if session is None:
        return None
    if require_active:
        try:
            if not session.is_active():
                return None
        except AttributeError:
            pass
        except RuntimeError:
            return None
    return session

def active_session_name(window, *, require_active: bool=True) -> str:
    session = _active_session(window, require_active=require_active)
    return getattr(session, 'name', '') if session is not None else ''

def is_facility_session(session) -> bool:
    return getattr(session, 'is_facility_session', False) is True

def active_facility_session(window, *, require_active: bool=True):
    session = _active_session(window, require_active=require_active)
    return session if is_facility_session(session) else None

def active_facility_session_name(window, *, require_active: bool=True) -> str:
    session = active_facility_session(window, require_active=require_active)
    return getattr(session, 'name', '') if session is not None else ''

def is_conversation_session(session) -> bool:
    return is_facility_session(session) or getattr(session, 'name', '') == 'npc_chat'

def is_facility_conversation_owner(owner: str) -> bool:
    return (owner or '') in _FACILITY_L4_PANEL_OWNERS

def _base_location_key_from_window(window) -> str:
    return base_location_key_from_area(getattr(window, '_last_non_interior_area', '') or '')

@dataclass(frozen=True)
class SeparationHierarchy:
    l1_state: str = 'pregame'
    l1_code: str = 'A'
    l1_name: str = '起動中'
    l2_code: str = ''
    l2_name: str = ''
    l3_code: str = ''
    l3_name: str = ''
    l4_code: str = ''
    l4_name: str = ''

    @classmethod
    def from_parts(cls, *, top_level_state: str='pregame', c_area: Optional[str]=None, base_location_key: Optional[str]=None, in_interior: bool=False, npc_active: bool=False) -> 'SeparationHierarchy':
        l1_code, l1_name = L1_TO_CODE_NAME.get(top_level_state, ('', top_level_state or ''))
        if top_level_state != 'normal-play':
            return cls(l1_state=top_level_state, l1_code=l1_code, l1_name=l1_name)
        area = c_area or area_from_base_location_key(base_location_key)
        if in_interior and (not area):
            area = 'city'
        l2_code, l2_name = AREA_TO_C_CODE_NAME.get(area or '', ('', ''))
        l3_code = l3_name = l4_code = l4_name = ''
        if in_interior and l2_code in ('C2', 'C3'):
            l3_code = 'L3'
            l3_name = '店内'
            if npc_active:
                l4_code = 'L4'
                l4_name = 'NPC会話系'
        elif npc_active and l2_code in ('C2', 'C3'):
            l3_code = 'L3'
            l3_name = 'NPC会話系'
        return cls(l1_state=top_level_state, l1_code=l1_code, l1_name=l1_name, l2_code=l2_code, l2_name=l2_name, l3_code=l3_code, l3_name=l3_name, l4_code=l4_code, l4_name=l4_name)

    @classmethod
    def from_window(cls, window, *, top_level_state: Optional[str]=None, in_interior: Optional[bool]=None, npc_active: Optional[bool]=None, c_area: Optional[str]=None, base_location_key: Optional[str]=None) -> 'SeparationHierarchy':
        top = top_level_state if top_level_state is not None else getattr(window, '_top_level_state', 'pregame')
        interior = bool(in_interior if in_interior is not None else getattr(window, '_in_interior', False))
        if npc_active is None:
            npc_active = bool(getattr(window, '_npc_conversation_active', False)) or is_conversation_session(_active_session(window))
        key = base_location_key if base_location_key is not None else _base_location_key_from_window(window)
        return cls.from_parts(top_level_state=top, c_area=c_area, base_location_key=key, in_interior=interior, npc_active=bool(npc_active))

    @property
    def indicator(self) -> str:
        code = self.l2_code or self.l1_code
        return f'[{code}]' if code else ''

    @property
    def path_codes(self) -> tuple[str, ...]:
        return tuple((code for code in (self.l1_code, self.l2_code, self.l3_code, self.l4_code) if code))

    @property
    def path_names(self) -> tuple[str, ...]:
        return tuple((name for name in (self.l1_name, self.l2_name, self.l3_name, self.l4_name) if name))

@dataclass(frozen=True)
class HierarchyRecognitionInput:
    top_level_state: str = 'pregame'
    c_area: str = ''
    in_interior: bool = False
    npc_active: bool = False
    npc_phase: Optional[int] = None
    mif_name: str = ''
    img_name: str = ''
    screen_id: Optional[str] = None
    panel_owner: str = ''
    active_session: str = ''
    facility_session_active: bool = False
    interior_mif_name: str = ''
    interior_raw: Optional[int] = None

    def transition_key(self, hierarchy: SeparationHierarchy) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (hierarchy.path_codes, hierarchy.path_names)

    def anomaly_key(self) -> tuple:
        if self.top_level_state == 'normal-play' and self.c_area == 'dungeon' and (self.facility_session_active or is_facility_conversation_owner(self.panel_owner)):
            return ('dungeon_facility_rejected', self.top_level_state, self.c_area, self.active_session, self.panel_owner, self.mif_name)
        if self.top_level_state == 'normal-play' and (not self.c_area):
            return ('normal_play_area_unknown', self.top_level_state, self.mif_name, self.img_name, self.screen_id)
        return ()

    def anomaly_kind(self) -> str:
        key = self.anomaly_key()
        return key[0] if key else ''

    def values_for_log(self) -> dict:
        return {'top': self.top_level_state, 'area': self.c_area or '', 'interior': self.in_interior, 'npc_active': self.npc_active, 'npc_phase': self.npc_phase, 'mif': self.mif_name or '', 'img': self.img_name or '', 'screen': self.screen_id or '', 'owner': self.panel_owner or '', 'session': self.active_session or '', 'interior_mif': self.interior_mif_name or '', 'interior_raw': self.interior_raw}
__all__ = ['AREA_TO_C_CODE_NAME', 'BASE_KEY_TO_AREA', 'CONVERSATION_PANEL_OWNERS', 'FACILITY_SESSION_BLOCKED_AREAS', 'conversation_panel_owners', 'register_conversation_panel_owners', 'register_facility_l4_panel_owners', 'is_facility_session', 'is_conversation_session', 'active_facility_session', 'is_facility_session_area_blocked', 'HierarchyRecognitionInput', 'L1_TO_CODE_NAME', 'SeparationHierarchy', 'active_facility_session_name', 'active_session_name', 'area_from_base_location_key', 'base_location_key_from_area', 'is_facility_conversation_owner']
