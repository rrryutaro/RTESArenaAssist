from __future__ import annotations
from types import SimpleNamespace
FRAME_OFFSET = 36724
CURRENT_TEXT_PTR_OFFSET = 43076
SELECT_OFFSET = 43067
DIALOG_ACTIVE_OFFSET = 43079
MODE_OFFSET = 43085
DIAG_DESC_OFFSET = 36718
FRAME_POPUP = 0
FAMILY_TEMPLE = 117
SELECT_ACTIVE = 117
DIALOG_NORMAL = 61
BLESSING_TEMPLATE_PTR = 30115
DONATE_TEMPLATE_PTR = 30199
BLESSING_TEXT_PREFIX = 'Receive our blessings'
COST_TEXT_PREFIX = 'This service will cost'
DONATE_TEXT_PREFIX = 'How much do you wish to donate?'
MENU_IMG = 'MENU_RT.IMG'
LIST_POPUP_IMG = 'NEWPOP.IMG'
CONFIRM_IMG = 'YESNO.IMG'
COST_SURFACE_KINDS = frozenset({'tavern_cost_show', 'tavern_cost_confirm'})
COST_IMG_ALLOWED = {CONFIRM_IMG: frozenset({'tavern_cost_confirm'}), LIST_POPUP_IMG: frozenset({'tavern_cost_show'}), MENU_IMG: frozenset({'tavern_cost_show'})}
_CURRENT_PTR_UNSET = object()
RESULT_BASELINE_ATTR = '_temple_result_baseline'

def _bytes(analyzer, anchor: int, off: int, length: int):
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

def _norm(text: str) -> str:
    return ' '.join((text or '').split())

def is_cost_text(text: str) -> bool:
    return _norm(text).startswith(COST_TEXT_PREFIX)

def is_donate_text(text: str) -> bool:
    return _norm(text).startswith(DONATE_TEXT_PREFIX)

def is_blessing_text(text: str) -> bool:
    return _norm(text).startswith(BLESSING_TEXT_PREFIX)

def is_result_text(text: str) -> bool:
    s = _norm(text)
    if not s or is_cost_text(s) or is_donate_text(s) or is_blessing_text(s):
        return False
    if s.startswith('Curing '):
        return False
    return True

def select_cost_candidate(candidates, img: str):
    from active_template_reader import template_surface_kind
    allowed = COST_IMG_ALLOWED.get((img or '').upper())
    for want_source in ('current_ptr', 'active_slot'):
        for c in candidates:
            if getattr(c, 'source', '') != want_source:
                continue
            kind = template_surface_kind(c)
            if kind not in COST_SURFACE_KINDS:
                continue
            if allowed is not None and kind not in allowed:
                continue
            return (c, kind)
    return (None, '')

def reset_result_baseline(window) -> None:
    try:
        if hasattr(window, RESULT_BASELINE_ATTR):
            delattr(window, RESULT_BASELINE_ATTR)
    except AttributeError:
        pass

def read_signals(analyzer, anchor: int, *, foreground_ptr=_CURRENT_PTR_UNSET, img: str='', shop_state=None, window=None) -> dict:
    img_up = (img or '').upper()
    gate = _u8(analyzer, anchor, FRAME_OFFSET)
    ptr = _u16(analyzer, anchor, CURRENT_TEXT_PTR_OFFSET) if foreground_ptr is _CURRENT_PTR_UNSET else foreground_ptr
    ptr = ptr if isinstance(ptr, int) else None
    family = ptr >> 8 & 255 if ptr is not None else None
    sel = _u8(analyzer, anchor, SELECT_OFFSET)
    aux = _u8(analyzer, anchor, DIALOG_ACTIVE_OFFSET)
    mode = _u8(analyzer, anchor, MODE_OFFSET)
    desc = _u16(analyzer, anchor, DIAG_DESC_OFFSET)
    ptr_menu = bool(shop_state is not None and getattr(shop_state, 'kind', '') == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'temple'))
    out = family == 0 and sel == 0 and (aux == 0)
    menu_box = gate not in (FRAME_POPUP, None)
    cure_view = None
    try:
        from normal_play.temple_cure_module import cure_foreground_view
        cure_view = cure_foreground_view(SimpleNamespace(_analyzer=analyzer, _anchor=anchor), img=img_up, shop_state=shop_state)
    except Exception:
        cure_view = None
    donate_slot = None
    blessing_slot = None
    cost_candidate = None
    cost_surface = ''
    try:
        from active_template_reader import read_active_template_candidates
        cands = read_active_template_candidates(analyzer, anchor)
    except Exception:
        cands = None
    if cands is not None:
        for c in cands:
            if c.ptr == DONATE_TEMPLATE_PTR and donate_slot is None:
                donate_slot = c
            elif c.ptr == BLESSING_TEMPLATE_PTR and blessing_slot is None and is_blessing_text(c.text):
                blessing_slot = c
        cost_candidate, cost_surface = select_cost_candidate(cands, img_up)
    cost_text = None
    result_texts = None
    try:
        from temple_dialog_reader import read_temple_response_candidates
        read = read_temple_response_candidates(analyzer, anchor)
    except Exception:
        read = None
    if read is not None:
        result_texts = {}
        for c in read.candidates:
            if is_cost_text(c.text):
                if cost_text is None:
                    cost_text = c.text
            elif is_result_text(c.text):
                result_texts[c.source_offset] = c.text
    result_new = None
    if window is not None and result_texts is not None:
        baseline = getattr(window, RESULT_BASELINE_ATTR, None)
        if baseline is None or menu_box:
            baseline = dict(result_texts)
            setattr(window, RESULT_BASELINE_ATTR, baseline)
        changed = sorted(((off, text) for off, text in result_texts.items() if baseline.get(off) != text))
        result_new = changed[0] if changed else False
    return {'img': img_up, 'gate': gate, 'menu_box': menu_box, 'ptr': ptr, 'family': family, 'ptr_menu': ptr_menu, 'sel': sel, 'aux': aux, 'out': out, 'in_conversation': family == FAMILY_TEMPLE or sel == SELECT_ACTIVE, 'cure_view': cure_view, 'donate_slot': donate_slot, 'blessing_slot': blessing_slot, 'cost_candidate': cost_candidate, 'cost_surface': cost_surface or None, 'cost_text': cost_text, 'result_texts': result_texts, 'result_new': result_new, 'mode': mode, 'desc': desc}
__all__ = ['FRAME_OFFSET', 'CURRENT_TEXT_PTR_OFFSET', 'SELECT_OFFSET', 'DIALOG_ACTIVE_OFFSET', 'MODE_OFFSET', 'DIAG_DESC_OFFSET', 'FRAME_POPUP', 'FAMILY_TEMPLE', 'SELECT_ACTIVE', 'DIALOG_NORMAL', 'BLESSING_TEMPLATE_PTR', 'DONATE_TEMPLATE_PTR', 'BLESSING_TEXT_PREFIX', 'COST_TEXT_PREFIX', 'DONATE_TEXT_PREFIX', 'COST_SURFACE_KINDS', 'COST_IMG_ALLOWED', 'RESULT_BASELINE_ATTR', 'MENU_IMG', 'LIST_POPUP_IMG', 'CONFIRM_IMG', 'is_cost_text', 'is_donate_text', 'is_blessing_text', 'is_result_text', 'select_cost_candidate', 'reset_result_baseline', 'read_signals']
