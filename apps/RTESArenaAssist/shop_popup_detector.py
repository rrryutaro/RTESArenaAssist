from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from arena_bridge import ArenaMemoryAnalyzer
from shop_menu_reader import SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_MAXLEN, parse_menu_groups, select_menu_group_by_ptr, MenuGroup
CURRENT_TEXT_PTR_OFFSET = 43076
NEWPOP_GATE_OFFSET = 47044
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
    kind: str = 'none'
    owner_kind: str = ''
    reason: str = ''
    ptr: Optional[int] = None
    ptr_hi: Optional[int] = None
    menu_span: Optional[tuple[int, int]] = None
    buy_span: Optional[tuple[int, int]] = None
    menu_items: list[str] = field(default_factory=list)
    menu_item_hotkeys: list[str] = field(default_factory=list)
    menu_title_en: str = ''
    buy_items: list[dict] = field(default_factory=list)
    room_items: list[dict] = field(default_factory=list)
    b7c4: Optional[int] = None
    ff2: Optional[int] = None
    price_cache: Optional[bytes] = None
    menu_group_count: Optional[int] = None
    active_menu_group_index: Optional[int] = None
    active_menu_item_spans: Optional[tuple[tuple[int, int], ...]] = None
    img_name: str = ''
    top_level_state: str = ''
    screen_id: str = ''
    in_interior: bool = False
_CONTROL_GROUP_TEXTS: frozenset[frozenset[str]] = frozenset({frozenset({'Yes', 'No'}), frozenset({'Yes', 'No', 'Cancel'}), frozenset({'YES', 'NO'}), frozenset({'YES', 'NO', 'CANCEL'}), frozenset({'ACCEPT', 'COUNTER', 'REJECT'}), frozenset({'Accept', 'Counter', 'Reject'})})

def _is_control_group(items: list[str]) -> bool:
    if not items:
        return False
    return frozenset(items) in _CONTROL_GROUP_TEXTS
_MENU_GROUP_KIND_TITLE_CACHE: Optional[dict] = None

def _menu_group_table() -> dict:
    global _MENU_GROUP_KIND_TITLE_CACHE
    if _MENU_GROUP_KIND_TITLE_CACHE is None:
        from session import facility_nodes as _fn
        from session.facility_node import build_menu_signature_table
        _MENU_GROUP_KIND_TITLE_CACHE = build_menu_signature_table()
    return _MENU_GROUP_KIND_TITLE_CACHE

def _classify_menu_group(items: list[str]) -> tuple[str, str, str]:
    key = frozenset(items)
    return _menu_group_table().get(key, ('shop_menu', '', ''))

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

def detect_shop_popup_state(analyzer: 'ArenaMemoryAnalyzer', anchor: int, *, top_level_state: str, img_name: str, in_interior: bool, screen_id: str='', allow_yesno_menu_recovery: bool=False, interior_mif_name: str='', active_facility_name: str='') -> ShopPopupState:
    state = ShopPopupState(kind='none', img_name=img_name, top_level_state=top_level_state, screen_id=screen_id, in_interior=in_interior)
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
    state.b7c4 = _read_u8(analyzer, anchor + NEWPOP_GATE_OFFSET)
    state.ff2 = _read_u8(analyzer, anchor + NEWPOP_COUNT_OFFSET)
    try:
        state.price_cache = analyzer.read_bytes(anchor + POPUP_PRICE_CACHE_OFFSET, 4)
    except (OSError, AttributeError):
        state.price_cache = None
    from session.tavern_node import TAVERN_NODE as _TAVERN_NODE
    buy_items, buy_span = _TAVERN_NODE.read_shop_buy_span(analyzer, anchor)
    state.buy_span = buy_span
    state.buy_items = buy_items
    menu_groups = _parse_shop_menu_groups(analyzer, anchor)
    state.menu_group_count = len(menu_groups)
    if menu_groups:
        state.menu_span = (SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_OFFSET + SHOP_MENU_BUFFER_MAXLEN)
    ptr = read_current_text_pointer(analyzer, anchor)
    state.ptr = ptr
    if ptr is not None:
        state.ptr_hi = ptr >> 8 & 255
    active_group = None
    active_group_list = menu_groups
    active_items_text: list[str] = []
    active_kind = ''
    active_owner = ''
    active_title_en = ''
    if ptr is not None and ptr not in _RESPONSE_BUFFER_PTRS:
        active_group = select_menu_group_by_ptr(menu_groups, ptr)
        if active_group is None and (not _in_span(ptr, _MENU_SPAN)) and (ptr >= _PTR_MENU_WINDOW_BACK):
            near_groups, _near_base = _parse_menu_groups_near_ptr(analyzer, anchor, ptr)
            near_active = select_menu_group_by_ptr(near_groups, ptr)
            if near_active is not None:
                active_group = near_active
                active_group_list = near_groups
        if active_group is not None:
            active_items_text = [it.text for it in active_group.items]
            active_kind, active_owner, active_title_en = _classify_menu_group(active_items_text)
    room_items_raw = _TAVERN_NODE.read_room_items(analyzer, anchor)
    state.room_items = room_items_raw
    _newpop_fg = img_name == 'NEWPOP.IMG' and state.b7c4 == 0 and ((state.ff2 or 0) == 0)
    _is_drinks_sig = state.price_cache == _TAVERN_NODE.DRINKS_PRICE_CACHE_SIG
    if _newpop_fg and _is_drinks_sig and buy_items:
        state.kind = 'shop_buy'
        state.owner_kind = 'tavern'
        state.reason = f'NEWPOP fg + drinks_sig + buy_count={len(buy_items)}'
        return state
    if _newpop_fg and (not _is_drinks_sig) and (active_owner == 'equipment'):
        try:
            from session.equipment_node import EQUIPMENT_NODE
            equipment_items = EQUIPMENT_NODE.read_sell_repair_items(analyzer, anchor)
        except Exception:
            equipment_items = []
        if equipment_items:
            state.kind = 'equipment_list'
            state.owner_kind = 'equipment'
            state.menu_items = active_items_text
            state.menu_item_hotkeys = [it.hotkey for it in active_group.items]
            state.active_menu_group_index = active_group_list.index(active_group)
            state.active_menu_item_spans = tuple(((it.start, it.end) for it in active_group.items))
            state.menu_title_en = active_title_en
            state.reason = f'NEWPOP fg + equipment menu ptr=0x{ptr:04X} + sell_items={len(equipment_items)}'
            return state
    if _newpop_fg and (not _is_drinks_sig) and room_items_raw:
        _mif_u = (interior_mif_name or '').upper()
        _active_facility = (active_facility_name or '').lower()
        _tavern_room_ctx = _TAVERN_NODE.is_room_list_context(interior_mif_name=interior_mif_name, active_facility_name=active_facility_name)
        if _tavern_room_ctx:
            state.kind = 'shop_rooms'
            state.owner_kind = 'tavern'
            state.reason = f'NEWPOP fg + no drinks_sig (cache=%r) + rooms=%d' % (state.price_cache, len(room_items_raw))
            return state
        state.kind = 'none'
        state.owner_kind = ''
        state.reason = f'NEWPOP fg + no drinks_sig but non-tavern interior (mif={_mif_u!r} active={_active_facility!r}); facility list unimplemented'
        return state
    if ptr is None:
        state.reason = 'ptr read failed'
        return state
    if ptr in _RESPONSE_BUFFER_PTRS:
        state.reason = f'ptr=0x{ptr:04X} is response buffer'
        return state
    if active_group is not None:
        if _is_control_group(active_items_text):
            state.reason = f'ptr=0x{ptr:04X} in control group items={active_items_text}, defer to negotiation/active_template'
            return state
        if (img_name or '').upper() == 'YESNO.IMG' and (not allow_yesno_menu_recovery):
            state.reason = f'ptr=0x{ptr:04X} in non-control group items={active_items_text}, defer YESNO.IMG to active_template'
            return state
        state.menu_items = active_items_text
        state.menu_item_hotkeys = [it.hotkey for it in active_group.items]
        state.active_menu_group_index = active_group_list.index(active_group)
        state.active_menu_item_spans = tuple(((it.start, it.end) for it in active_group.items))
        state.kind = active_kind
        state.owner_kind = active_owner
        state.menu_title_en = active_title_en
        state.reason = f'ptr=0x{ptr:04X} in group[{state.active_menu_group_index}] ({len(active_items_text)} items) kind={active_kind} owner={active_owner!r} title={active_title_en!r}'
        return state
    state.reason = f"no shop active (img={img_name!r} b7c4={state.b7c4} ptr={('0x%04X' % ptr if ptr is not None else '?')} menu_groups={len(menu_groups)} buy_items={len(buy_items)} room_items={len(room_items_raw)})"
    return state
__all__ = ['CURRENT_TEXT_PTR_OFFSET', 'ShopPopupState', 'read_current_text_pointer', 'detect_shop_popup_state']
