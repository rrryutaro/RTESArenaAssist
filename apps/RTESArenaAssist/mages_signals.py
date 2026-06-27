from __future__ import annotations
VIEW_FLAG_OFFSET = 36724
VIEW_TYPE_OFFSET = 36730
LIST_FLAG_OFFSET = 47044
DIALOG_ACTIVE_OFFSET = 43079
TEXT_FAMILY_OFFSET = 43077
SUBSTATE_OFFSET = 43067
VIEW_DESC_OFFSET = 36718
RESULT_HINT_OFFSET = 44470
CURRENT_TEXT_PTR_OFFSET = 43076
RESPONSE_TEXT_OFFSET = 4164
MAGES_MENU_TEXT_OFFSET = 28508
NEGOTIATION_TEXT_OFFSET = 37534
VIEW_MENU = 81
VIEW_SUBMENU = 101
VIEW_EDIT_EFFECTS = 129
VIEW_POPUP = 0
TYPE_BUY_SUB = 151
TYPE_STEAL = 138
TYPE_POPUP = 199
LIST_ON = 0
DIALOG_NEGOTIATION = 0
DIALOG_NORMAL = 61
FAMILY_MENU_DETECT_CREATE = 111
DETECT_KNOWN_HINT = 154
DETECT_COST_HINT = 10
MAGES_MENU_PTR_START = 28416
MAGES_MENU_PTR_END = 28736
DETECT_MAGIC_QUOTE_PREFIX = 'I can tell you if that is magical'
DETECT_MAGIC_ALREADY_KNOWN = 'You already know what that is!'
DETECT_MAGIC_IDENTIFIED = 'The item is now identified in your inventory.'
MENU_STATES = frozenset({'main_menu', 'buy_submenu', 'steal_menu', 'edit_effects_menu'})

def _u8(analyzer, anchor: int, off: int):
    try:
        raw = analyzer.read_bytes(anchor + off, 1)
    except (OSError, AttributeError):
        return None
    return raw[0] if raw else None

def _u16(analyzer, anchor: int, off: int):
    try:
        raw = analyzer.read_bytes(anchor + off, 2)
    except (OSError, AttributeError):
        return None
    if len(raw) < 2:
        return None
    return raw[0] | raw[1] << 8

def _ascii_cstr(analyzer, anchor: int, off: int, length: int=128) -> str:
    try:
        raw = analyzer.read_bytes(anchor + off, length)
    except (OSError, AttributeError):
        return ''
    return raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()

def _normalize_text(text: str) -> str:
    return ' '.join((text or '').replace('\r', ' ').replace('\n', ' ').split())

def _contains_normalized(analyzer, anchor: int, off: int, length: int, needle: str) -> bool:
    try:
        raw = analyzer.read_bytes(anchor + off, length)
    except (OSError, AttributeError):
        return False
    text = raw.decode('ascii', errors='replace').replace('\x00', ' ')
    return needle in _normalize_text(text)

def read_signals(analyzer, anchor: int) -> dict:
    view_desc = _u16(analyzer, anchor, VIEW_DESC_OFFSET)
    return {'view': _u8(analyzer, anchor, VIEW_FLAG_OFFSET), 'type': _u8(analyzer, anchor, VIEW_TYPE_OFFSET), 'list': _u8(analyzer, anchor, LIST_FLAG_OFFSET), 'dialog': _u8(analyzer, anchor, DIALOG_ACTIVE_OFFSET), 'family': _u8(analyzer, anchor, TEXT_FAMILY_OFFSET), 'sub': _u8(analyzer, anchor, SUBSTATE_OFFSET), 'view_desc': view_desc, 'view_desc_lo': view_desc & 255 if view_desc is not None else None, 'result_hint': _u8(analyzer, anchor, RESULT_HINT_OFFSET)}

def classify(sig: dict) -> str:
    view = sig.get('view')
    if view == VIEW_MENU:
        return 'main_menu'
    if view == VIEW_SUBMENU:
        if sig.get('type') == TYPE_STEAL:
            return 'steal_menu'
        return 'buy_submenu'
    if view == VIEW_EDIT_EFFECTS:
        return 'edit_effects_menu'
    if view == VIEW_POPUP:
        if sig.get('list') == LIST_ON:
            return 'list'
        if sig.get('dialog') == DIALOG_NEGOTIATION:
            return 'negotiation'
        return 'reply'
    return 'unknown'

def detect_magic_reply_kind(sig: dict, img_name: str='') -> str:
    img = (img_name or '').upper()
    if img not in ('NEWPOP.IMG', 'YESNO.IMG', ''):
        return ''
    if sig.get('view') != VIEW_POPUP:
        return ''
    if sig.get('type') not in (None, TYPE_POPUP):
        return ''
    if sig.get('list') in (None, LIST_ON):
        return ''
    if sig.get('dialog') != DIALOG_NORMAL:
        return ''
    if sig.get('family') != FAMILY_MENU_DETECT_CREATE:
        return ''
    if sig.get('sub') not in (None, 0):
        return ''
    if sig.get('view_desc_lo') != 47:
        return ''
    hint = sig.get('result_hint')
    if img == 'NEWPOP.IMG' and hint == DETECT_KNOWN_HINT:
        return 'detect_known'
    if img == 'YESNO.IMG' and hint == DETECT_COST_HINT:
        return 'detect_cost'
    return ''

def is_detect_magic_reply_foreground(sig: dict, img_name: str='') -> bool:
    return bool(detect_magic_reply_kind(sig, img_name))

def detect_magic_reply_kind_from_memory(analyzer, anchor: int, img_name: str='', sig: dict | None=None) -> str:
    sig = sig if sig is not None else read_signals(analyzer, anchor)
    img = (img_name or '').upper()
    if img not in ('NEWPOP.IMG', 'YESNO.IMG', ''):
        return ''
    if sig.get('dialog') != DIALOG_NORMAL:
        return ''
    state = classify(sig)
    if state == 'list':
        return ''
    if state in MENU_STATES:
        return ''
    is_popup_reply = sig.get('view') == VIEW_POPUP and sig.get('type') in (None, TYPE_POPUP) and (sig.get('list') not in (None, LIST_ON))
    if img == 'YESNO.IMG' and is_popup_reply and _contains_normalized(analyzer, anchor, NEGOTIATION_TEXT_OFFSET, 256, DETECT_MAGIC_IDENTIFIED):
        return 'detect_result'
    if sig.get('family') != FAMILY_MENU_DETECT_CREATE:
        return ''
    old_kind = detect_magic_reply_kind(sig, img_name)
    if old_kind:
        return old_kind
    current_ptr = _u16(analyzer, anchor, CURRENT_TEXT_PTR_OFFSET)
    known_text = _ascii_cstr(analyzer, anchor, MAGES_MENU_TEXT_OFFSET, 96)
    response_text = _normalize_text(_ascii_cstr(analyzer, anchor, RESPONSE_TEXT_OFFSET, 160))
    if img == 'NEWPOP.IMG' and sig.get('list') not in (None, LIST_ON) and isinstance(current_ptr, int) and (MAGES_MENU_PTR_START <= current_ptr < MAGES_MENU_PTR_END) and (known_text == DETECT_MAGIC_ALREADY_KNOWN):
        return 'detect_known'
    if img == 'YESNO.IMG' and is_popup_reply and (DETECT_MAGIC_QUOTE_PREFIX in response_text):
        return 'detect_cost'
    return ''
__all__ = ['VIEW_FLAG_OFFSET', 'VIEW_TYPE_OFFSET', 'LIST_FLAG_OFFSET', 'DIALOG_ACTIVE_OFFSET', 'TEXT_FAMILY_OFFSET', 'SUBSTATE_OFFSET', 'VIEW_DESC_OFFSET', 'RESULT_HINT_OFFSET', 'CURRENT_TEXT_PTR_OFFSET', 'RESPONSE_TEXT_OFFSET', 'MAGES_MENU_TEXT_OFFSET', 'NEGOTIATION_TEXT_OFFSET', 'VIEW_MENU', 'VIEW_SUBMENU', 'VIEW_EDIT_EFFECTS', 'VIEW_POPUP', 'TYPE_POPUP', 'DIALOG_NORMAL', 'FAMILY_MENU_DETECT_CREATE', 'DETECT_KNOWN_HINT', 'DETECT_COST_HINT', 'DETECT_MAGIC_QUOTE_PREFIX', 'DETECT_MAGIC_ALREADY_KNOWN', 'DETECT_MAGIC_IDENTIFIED', 'MENU_STATES', 'read_signals', 'classify', 'detect_magic_reply_kind', 'detect_magic_reply_kind_from_memory', 'is_detect_magic_reply_foreground']
