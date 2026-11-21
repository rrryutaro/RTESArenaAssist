from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from arena_bridge import ArenaMemoryAnalyzer
from shop_menu_reader import SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_MAXLEN, parse_menu_groups, select_menu_group_by_ptr, MenuGroup
CURRENT_TEXT_PTR_OFFSET = 43076
NEWPOP_GATE_OFFSET = 47044
POPUP_FRAME_OFFSET = 36724
NEWPOP_COUNT_OFFSET = 4082
POPUP_PRICE_CACHE_OFFSET = 43062
_RESPONSE_BUFFER_PTRS = frozenset({4164, 37534, 39582})
_MENU_SPAN = (SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_OFFSET + SHOP_MENU_BUFFER_MAXLEN)
_PTR_MENU_WINDOW_BACK = 512
_PTR_MENU_WINDOW_LEN = 1024
_SHOP_BLOCKED_TOP_LEVELS = frozenset({'pregame', 'chargen'})
_SHOP_BLOCKED_IMGS = frozenset({'OP.IMG', 'LOADSAVE.IMG', 'MENU.IMG', 'SCROLL01.IMG', 'SCROLL02.IMG', 'QUOTE.IMG'})
_SHOP_BLOCKED_SCREEN_IDS = frozenset({'system_menu', 'loadsave', 'status_page', 'equipment', 'spellbook', 'spell_detail', 'bonus_screen', 'local_map', 'world_map', 'logbook'})

@dataclass
class ShopPopupState:
    reason: str = ''
    ptr: Optional[int] = None
    ptr_hi: Optional[int] = None
    menu_span: Optional[tuple[int, int]] = None
    b7c4: Optional[int] = None
    frame: Optional[int] = None
    ff2: Optional[int] = None
    price_cache: Optional[bytes] = None
    menu_group_count: Optional[int] = None
    img_name: str = ''
    top_level_state: str = ''
    screen_id: str = ''
    in_interior: bool = False
    gate_open: bool = False
    ptr_group_items: list[str] = field(default_factory=list)
    ptr_group_hotkeys: list[str] = field(default_factory=list)
    ptr_is_response: bool = False
    ptr_in_control_group: bool = False
    yesno_img: bool = False
    yesno_candidate_pointers: tuple = ()
    newpop_fg: bool = False
    interior_mif_name: str = ''
    active_facility_name: str = ''
_CONTROL_GROUP_TEXTS: frozenset[frozenset[str]] = frozenset({frozenset({'Yes', 'No'}), frozenset({'Yes', 'No', 'Cancel'}), frozenset({'YES', 'NO'}), frozenset({'YES', 'NO', 'CANCEL'}), frozenset({'ACCEPT', 'COUNTER', 'REJECT'}), frozenset({'Accept', 'Counter', 'Reject'})})

def _is_control_group(items: list[str]) -> bool:
    if not items:
        return False
    return frozenset(items) in _CONTROL_GROUP_TEXTS

def read_current_text_pointer(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> Optional[int]:
    try:
        raw = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
        if len(raw) < 2:
            return None
        return raw[0] | raw[1] << 8
    except (OSError, AttributeError):
        return None

def _parse_shop_menu_groups(analyzer, anchor) -> list[MenuGroup]:
    try:
        raw = analyzer.read_bytes(anchor + SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_menu_groups(raw, base_offset=SHOP_MENU_BUFFER_OFFSET)

def _parse_menu_groups_near_ptr(analyzer, anchor, ptr: int) -> tuple[list[MenuGroup], int]:
    base = ptr - _PTR_MENU_WINDOW_BACK
    try:
        raw = analyzer.read_bytes(anchor + base, _PTR_MENU_WINDOW_LEN)
    except (OSError, AttributeError):
        return ([], base)
    return (parse_menu_groups(raw, base_offset=base), base)
YESNO_MENU_BACK_POLLS = 2

def yesno_menu_back(shop_state, declared_pointers) -> bool:
    history = tuple(getattr(shop_state, 'yesno_candidate_pointers', ()) or ())
    if len(history) < YESNO_MENU_BACK_POLLS:
        return False
    declared = frozenset(declared_pointers)
    return not any((declared & frozenset(seen) for seen in history[-YESNO_MENU_BACK_POLLS:]))

def ptr_group_menu_items(shop_state, *, menu_back_on_yesno: bool=False) -> list[str]:
    if shop_state is None or not getattr(shop_state, 'gate_open', False):
        return []
    if getattr(shop_state, 'ptr_is_response', False) or getattr(shop_state, 'ptr_in_control_group', False) or (getattr(shop_state, 'yesno_img', False) and (not menu_back_on_yesno)):
        return []
    return list(getattr(shop_state, 'ptr_group_items', None) or [])

def ptr_group_signature_entry_of(shop_state, signatures, *, menu_back_on_yesno: bool=False) -> Optional[tuple[str, str]]:
    items = ptr_group_menu_items(shop_state, menu_back_on_yesno=menu_back_on_yesno)
    if not items:
        return None
    key = frozenset(items)
    for sig, kind, title in signatures:
        if frozenset(sig) == key:
            return (kind, title)
    return None

def ptr_group_signature_of(shop_state, signatures, *, menu_back_on_yesno: bool=False) -> tuple[bool, str]:
    entry = ptr_group_signature_entry_of(shop_state, signatures, menu_back_on_yesno=menu_back_on_yesno)
    if entry is None or entry[0] != 'shop_menu':
        return (False, '')
    return (True, entry[1])

def _in_span(ptr: Optional[int], span: Optional[tuple[int, int]]) -> bool:
    if ptr is None or span is None:
        return False
    lo, hi = span
    return lo <= ptr < hi

def _read_u8(analyzer, addr) -> Optional[int]:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return None

def detect_shop_popup_state(analyzer: 'ArenaMemoryAnalyzer', anchor: int, *, top_level_state: str, img_name: str, in_interior: bool, screen_id: str='', yesno_candidate_pointers: tuple=(), interior_mif_name: str='', active_facility_name: str='', area: Optional[str]=None) -> ShopPopupState:
    state = ShopPopupState(img_name=img_name, top_level_state=top_level_state, screen_id=screen_id, in_interior=in_interior, yesno_candidate_pointers=tuple(yesno_candidate_pointers or ()))
    if top_level_state in _SHOP_BLOCKED_TOP_LEVELS:
        state.reason = f'blocked top_level={top_level_state}'
        return state
    if img_name in _SHOP_BLOCKED_IMGS:
        state.reason = f'blocked img={img_name}'
        return state
    if screen_id in _SHOP_BLOCKED_SCREEN_IDS:
        state.reason = f'blocked screen={screen_id}'
        return state
    if not in_interior:
        state.reason = 'not in_interior'
        return state
    if area is not None and area != 'city':
        state.reason = f'blocked area={area!r} (facility/shop is city-only)'
        return state
    state.gate_open = True
    state.interior_mif_name = interior_mif_name or ''
    state.active_facility_name = active_facility_name or ''
    state.b7c4 = _read_u8(analyzer, anchor + NEWPOP_GATE_OFFSET)
    state.ff2 = _read_u8(analyzer, anchor + NEWPOP_COUNT_OFFSET)
    state.frame = _read_u8(analyzer, anchor + POPUP_FRAME_OFFSET)
    try:
        state.price_cache = analyzer.read_bytes(anchor + POPUP_PRICE_CACHE_OFFSET, 4)
    except (OSError, AttributeError):
        state.price_cache = None
    menu_groups = _parse_shop_menu_groups(analyzer, anchor)
    state.menu_group_count = len(menu_groups)
    if menu_groups:
        state.menu_span = (SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_OFFSET + SHOP_MENU_BUFFER_MAXLEN)
    ptr = read_current_text_pointer(analyzer, anchor)
    state.ptr = ptr
    if ptr is not None:
        state.ptr_hi = ptr >> 8 & 255
    active_group = None
    if ptr is not None and ptr not in _RESPONSE_BUFFER_PTRS:
        active_group = select_menu_group_by_ptr(menu_groups, ptr)
        from camp_rest_reader import ptr_in_camp_block as _ptr_in_camp_block
        if active_group is None and (not _in_span(ptr, _MENU_SPAN)) and (not _ptr_in_camp_block(ptr)) and (ptr >= _PTR_MENU_WINDOW_BACK):
            near_groups, _near_base = _parse_menu_groups_near_ptr(analyzer, anchor, ptr)
            near_active = select_menu_group_by_ptr(near_groups, ptr)
            if near_active is not None:
                active_group = near_active
    state.ptr_is_response = ptr is not None and ptr in _RESPONSE_BUFFER_PTRS
    if active_group is not None:
        state.ptr_group_items = [it.text for it in active_group.items]
        state.ptr_group_hotkeys = [it.hotkey for it in active_group.items]
        state.ptr_in_control_group = _is_control_group(state.ptr_group_items)
    state.yesno_img = (img_name or '').upper() == 'YESNO.IMG'
    state.newpop_fg = img_name == 'NEWPOP.IMG' and state.b7c4 == 0 and (state.frame == 0) and (not state.ptr_is_response)
    return state
__all__ = ['CURRENT_TEXT_PTR_OFFSET', 'ShopPopupState', 'read_current_text_pointer', 'detect_shop_popup_state']
