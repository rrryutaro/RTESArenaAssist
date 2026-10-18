from __future__ import annotations
FRAME_OFFSET = 36724
TYPE_OFFSET = 36730
LIST_FLAG_OFFSET = 47044
DIALOG_ACTIVE_OFFSET = 43079
SUBSTATE_OFFSET = 43067
CURRENT_TEXT_PTR_OFFSET = 43076
RESPONSE_TEXT_OFFSET = 4164
MAGES_MENU_TEXT_OFFSET = 28508
NEGOTIATION_TEXT_OFFSET = 37534
VIEW_DESC_OFFSET = 36718
RESULT_HINT_OFFSET = 44470
FRAME_POPUP = 0
FRAME_EDIT_EFFECTS = 129
FRAME_MAIN_MENU = 81
FRAME_SUB_MENU = 101
TYPE_POPUP = 199
LIST_ON = 0
DIALOG_NEGOTIATION = 0
DIALOG_NORMAL = 61
FAMILY_MENU_DETECT_CREATE = 111
CONFIRM_FAMILY = 75
SUB_IDENTIFIED = 1
DESC_LO_DETECT_REPLY = 47
DESC_LO_MENU_TO_LIST = frozenset({107, 108})
DETECT_KNOWN_HINT = 154
DETECT_COST_HINT = 10
MAGES_MENU_PTR_START = 28416
MAGES_MENU_PTR_END = 28736
DETECT_MAGIC_QUOTE_PREFIX = 'I can tell you if that is magical'
DETECT_MAGIC_ALREADY_KNOWN = 'You already know what that is!'
DETECT_MAGIC_IDENTIFIED = 'The item is now identified in your inventory.'
SPELLMAKER_LIST_TITLES = frozenset({'Targets', 'Effects', 'Effect Options'})
LIST_TITLE_ATTR = '_mages_list_title_en'
MENU_IMG = 'MENU_RT.IMG'
MAGIC_ITEM_LIST_IMG = 'POPUP7.IMG'
SPELL_LIST_IMG = 'POPUP.IMG'
INVENTORY_LIST_IMG = 'NEWPOP.IMG'
LIST_IMGS = (MAGIC_ITEM_LIST_IMG, SPELL_LIST_IMG, INVENTORY_LIST_IMG)
SPELLMAKER_IMG = 'SPELLMKR.IMG'
BUYSPELL_IMG = 'BUYSPELL.IMG'
CONFIRM_IMG = 'YESNO.IMG'
NEGOTIATION_IMG = 'NEGOTBUT.IMG'
NEGOTIATION_IMGS = (NEGOTIATION_IMG, CONFIRM_IMG)
GUILD_MODAL_IMGS = frozenset({MENU_IMG, SPELLMAKER_IMG, BUYSPELL_IMG, CONFIRM_IMG, NEGOTIATION_IMG, *LIST_IMGS})
_OUTSIDE_UI_SUFFIXES = ('.CIF', '.XMI')
_FORM_PREFIX = 'FORM'
_IMG_SUFFIX = '.IMG'
_CURRENT_PTR_UNSET = object()

def is_form_img(img: str) -> bool:
    up = (img or '').upper()
    return up.startswith(_FORM_PREFIX) and up.endswith(_IMG_SUFFIX)

def is_guild_modal_img(img: str) -> bool:
    up = (img or '').upper()
    return up in GUILD_MODAL_IMGS or is_form_img(up)

def is_outside_shop_ui_img(img: str) -> bool:
    return (img or '').upper().endswith(_OUTSIDE_UI_SUFFIXES)

def _bytes(analyzer, anchor: int, off: int, length: int) -> bytes | None:
    try:
        raw = analyzer.read_bytes(anchor + off, length)
    except (OSError, AttributeError, TypeError):
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    return bytes(raw)

def _u8(analyzer, anchor: int, off: int):
    raw = _bytes(analyzer, anchor, off, 1)
    return raw[0] if raw else None

def _u16(analyzer, anchor: int, off: int):
    raw = _bytes(analyzer, anchor, off, 2)
    if raw is None or len(raw) < 2:
        return None
    return raw[0] | raw[1] << 8

def _ascii_cstr(analyzer, anchor: int, off: int, length: int=128) -> str | None:
    raw = _bytes(analyzer, anchor, off, length)
    if raw is None:
        return None
    return raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()

def _normalize_text(text: str) -> str:
    return ' '.join((text or '').replace('\r', ' ').replace('\n', ' ').split())

def _contains_normalized(analyzer, anchor: int, off: int, length: int, needle: str) -> bool | None:
    raw = _bytes(analyzer, anchor, off, length)
    if raw is None:
        return None
    text = raw.decode('ascii', errors='replace').replace('\x00', ' ')
    return needle in _normalize_text(text)

def _ptr_area(ptr) -> str | None:
    if not isinstance(ptr, int):
        return None
    if MAGES_MENU_PTR_START <= ptr < MAGES_MENU_PTR_END:
        return 'menu'
    if RESPONSE_TEXT_OFFSET <= ptr < RESPONSE_TEXT_OFFSET + 512:
        return 'response'
    if NEGOTIATION_TEXT_OFFSET <= ptr < NEGOTIATION_TEXT_OFFSET + 512:
        return 'negotiation'
    if ptr in (38434, 33384) or 39582 <= ptr < 39582 + 512:
        return 'story'
    return 'other'

def read_signals(analyzer, anchor: int, *, foreground_ptr=_CURRENT_PTR_UNSET, img: str='', shop_state=None, cache_on=None) -> dict:
    img_up = (img or '').upper()
    frame = _u8(analyzer, anchor, FRAME_OFFSET)
    type_ = _u8(analyzer, anchor, TYPE_OFFSET)
    list_flag = _u8(analyzer, anchor, LIST_FLAG_OFFSET)
    dialog = _u8(analyzer, anchor, DIALOG_ACTIVE_OFFSET)
    sub = _u8(analyzer, anchor, SUBSTATE_OFFSET)
    view_desc = _u16(analyzer, anchor, VIEW_DESC_OFFSET)
    result_hint = _u8(analyzer, anchor, RESULT_HINT_OFFSET)
    ptr = _u16(analyzer, anchor, CURRENT_TEXT_PTR_OFFSET) if foreground_ptr is _CURRENT_PTR_UNSET else foreground_ptr
    ptr = ptr if isinstance(ptr, int) else None
    family = ptr >> 8 & 255 if ptr is not None else None
    ptr_menu = bool(shop_state is not None and getattr(shop_state, 'kind', '') == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'mages_guild'))
    cost_text = _contains_normalized(analyzer, anchor, RESPONSE_TEXT_OFFSET, 160, DETECT_MAGIC_QUOTE_PREFIX)
    ident_text = _contains_normalized(analyzer, anchor, NEGOTIATION_TEXT_OFFSET, 256, DETECT_MAGIC_IDENTIFIED)
    known_raw = _ascii_cstr(analyzer, anchor, MAGES_MENU_TEXT_OFFSET, 96)
    known_text = None if known_raw is None else known_raw == DETECT_MAGIC_ALREADY_KNOWN
    ident_at_ptr = None
    if img_up == CONFIRM_IMG and ident_text and (list_flag == LIST_ON) and (ptr is not None):
        at_ptr = _ascii_cstr(analyzer, anchor, ptr, 96)
        ident_at_ptr = None if at_ptr is None else _normalize_text(at_ptr) == DETECT_MAGIC_IDENTIFIED
    title = ''
    if cache_on is not None:
        title = (getattr(cache_on, LIST_TITLE_ATTR, '') or '').strip()
    spellmaker_list_title = title if title in SPELLMAKER_LIST_TITLES else ''
    prompt_text = None
    if img_up in LIST_IMGS and list_flag not in (None, LIST_ON) and (not spellmaker_list_title):
        try:
            from mages_prompt_reader import resolve_response_prompt
            prompt_text = resolve_response_prompt(analyzer, anchor, foreground_ptr=ptr, cache_on=cache_on)
        except Exception:
            prompt_text = None
    return {'img': img_up, 'outside_ui': is_outside_shop_ui_img(img_up), 'form': is_form_img(img_up), 'frame': frame, 'ptr': ptr, 'ptr_menu': ptr_menu, 'ptr_area': _ptr_area(ptr), 'ptr_in_menu_range': MAGES_MENU_PTR_START <= ptr < MAGES_MENU_PTR_END if ptr is not None else None, 'dialog': dialog, 'sub': sub, 'list_flag': list_flag, 'view_desc_lo': view_desc & 255 if view_desc is not None else None, 'result_hint': result_hint, 'confirm_family': family == CONFIRM_FAMILY if family is not None else None, 'cost_text': cost_text, 'ident_text': ident_text, 'ident_at_ptr': ident_at_ptr, 'known_text': known_text, 'spellmaker_list_title': spellmaker_list_title, 'prompt_text': prompt_text, 'view': frame, 'type': type_, 'list': list_flag, 'family': family, 'foreground_ptr': ptr}
__all__ = ['FRAME_OFFSET', 'TYPE_OFFSET', 'LIST_FLAG_OFFSET', 'DIALOG_ACTIVE_OFFSET', 'SUBSTATE_OFFSET', 'CURRENT_TEXT_PTR_OFFSET', 'RESPONSE_TEXT_OFFSET', 'MAGES_MENU_TEXT_OFFSET', 'NEGOTIATION_TEXT_OFFSET', 'VIEW_DESC_OFFSET', 'RESULT_HINT_OFFSET', 'FRAME_POPUP', 'FRAME_EDIT_EFFECTS', 'FRAME_MAIN_MENU', 'FRAME_SUB_MENU', 'TYPE_POPUP', 'LIST_ON', 'DIALOG_NEGOTIATION', 'DIALOG_NORMAL', 'FAMILY_MENU_DETECT_CREATE', 'CONFIRM_FAMILY', 'SUB_IDENTIFIED', 'DESC_LO_DETECT_REPLY', 'DESC_LO_MENU_TO_LIST', 'DETECT_KNOWN_HINT', 'DETECT_COST_HINT', 'MAGES_MENU_PTR_START', 'MAGES_MENU_PTR_END', 'SPELLMAKER_LIST_TITLES', 'LIST_TITLE_ATTR', 'DETECT_MAGIC_QUOTE_PREFIX', 'DETECT_MAGIC_ALREADY_KNOWN', 'DETECT_MAGIC_IDENTIFIED', 'LIST_IMGS', 'SPELLMAKER_IMG', 'BUYSPELL_IMG', 'CONFIRM_IMG', 'NEGOTIATION_IMGS', 'is_form_img', 'is_outside_shop_ui_img', 'MENU_IMG', 'MAGIC_ITEM_LIST_IMG', 'SPELL_LIST_IMG', 'INVENTORY_LIST_IMG', 'NEGOTIATION_IMG', 'GUILD_MODAL_IMGS', 'is_guild_modal_img', 'read_signals']
