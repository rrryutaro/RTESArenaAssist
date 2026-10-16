from __future__ import annotations
FRAME_OFFSET = 36724
CURRENT_TEXT_PTR_OFFSET = 43076
LIST_FLAG_OFFSET = 47044
RAW_TEMPLATE_OFFSET = 4164
RAW_TEMPLATE_READ_LEN = 192
DIALOG_PTR = 30
FRAME_POPUP = 0
LIST_FLAG_LIST = 0
ESTIMATE_TEMPLATE_PREFIXES = ('Sure I could fix that ', 'Fixing that ')
REPAIR_ENTRY_PROMPT = 'Which job do you wish to inspect?'
STATUS_SLOT_WINDOW_BEFORE = 16
STATUS_SLOT_WINDOW_AFTER = 96
MENU_IMG = 'MENU_RT.IMG'
WEAPON_LIST_IMG = 'POPUP3.IMG'
ARMOR_LIST_IMG = 'POPUP4.IMG'
INVENTORY_LIST_IMG = 'NEWPOP.IMG'
REPAIR_MANAGE_IMG = 'NEWOLD.IMG'
CONFIRM_IMG = 'YESNO.IMG'
NEGOTIATION_IMG = 'NEGOTBUT.IMG'
LIST_IMGS = (WEAPON_LIST_IMG, ARMOR_LIST_IMG, INVENTORY_LIST_IMG)
BUY_LIST_IMGS = frozenset({WEAPON_LIST_IMG, ARMOR_LIST_IMG})
REPAIR_POPUP_IMGS = frozenset({INVENTORY_LIST_IMG, REPAIR_MANAGE_IMG})
REPLY_ALLOWED_IMGS = frozenset({MENU_IMG, CONFIRM_IMG, INVENTORY_LIST_IMG, REPAIR_MANAGE_IMG})
ACTIVE_REPLY_PREFIXES = ("Can't you afford it?", "Can't you wait that long?", "Maybe you're not interested?", 'Which job do you wish to inspect?', 'Sorry, I already have my hands full.')
PRESENCE_REPLY_PREFIXES = ('I can cut down the time', 'I can cut the cost', "Then I'll get started", "Good, I'll get to it", 'I understand. You might consider', 'Well, if you change your mind', 'Sorry, I already have my hands full.')
PRESENCE_IMGS = frozenset({INVENTORY_LIST_IMG, REPAIR_MANAGE_IMG, CONFIRM_IMG})

def img_columns(img_up: str) -> dict:
    img_up = (img_up or '').upper()
    return {'img_repair_popup': img_up in REPAIR_POPUP_IMGS, 'img_repair_entry': img_up == REPAIR_MANAGE_IMG, 'img_inventory': img_up == INVENTORY_LIST_IMG, 'img_confirm': img_up == CONFIRM_IMG, 'img_negotiation': img_up == NEGOTIATION_IMG, 'img_reply_allowed': img_up in REPLY_ALLOWED_IMGS, 'img_buy_list': img_up in BUY_LIST_IMGS}
_CURRENT_PTR_UNSET = object()
REPLY_BASELINE_ATTR = '_equipment_reply_baseline'

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

def is_no_repair_reply_text(text: str) -> bool:
    text = (text or '').strip()
    return text.startswith('Your ') and 'does not need any repairing' in text

def is_estimate_template(head: str) -> bool:
    return bool(head) and head.startswith(ESTIMATE_TEMPLATE_PREFIXES)

def is_estimate_rendered(text: str) -> bool:
    s = (text or '').strip()
    return bool(s) and '%' not in s and s.startswith(ESTIMATE_TEMPLATE_PREFIXES)

def ptr_menu_of(shop_state, ptr) -> bool:
    if not (shop_state is not None and getattr(shop_state, 'kind', '') == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'equipment')):
        return False
    state_ptr = getattr(shop_state, 'ptr', None)
    try:
        if state_ptr is not None and int(state_ptr) == DIALOG_PTR:
            return False
    except (TypeError, ValueError):
        pass
    return not (isinstance(ptr, int) and ptr == DIALOG_PTR)

def reset_reply_baseline(window) -> None:
    try:
        if hasattr(window, REPLY_BASELINE_ATTR):
            delattr(window, REPLY_BASELINE_ATTR)
    except AttributeError:
        pass

def _read_raw_template_head(analyzer, anchor: int) -> str:
    raw = _bytes(analyzer, anchor, RAW_TEMPLATE_OFFSET, RAW_TEMPLATE_READ_LEN)
    if not raw:
        return ''
    end = raw.find(b'\x00')
    if end == -1:
        end = len(raw)
    return raw[:end].decode('ascii', errors='replace')

def _read_active_slots(analyzer, anchor: int) -> list:
    try:
        from active_template_reader import ACTIVE_TEMPLATE_PTR_OFFSETS
    except ImportError:
        return []
    out = []
    for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
        val = _u16(analyzer, anchor, off)
        if val is not None:
            out.append(val)
    return out

def _negotiation_body_live(analyzer, anchor: int, cands) -> bool:
    try:
        from negotiation_reader import NEGOT_RENDERED_OFFSET, read_negotiation_diagnostic
        _raw, _canon, _rendered, matched = read_negotiation_diagnostic(analyzer, anchor)
    except Exception:
        return False
    if not matched or cands is None:
        return False
    for c in cands:
        if getattr(c, 'ptr', None) != NEGOT_RENDERED_OFFSET:
            continue
        text = (getattr(c, 'text', '') or '').strip()
        if not text:
            return True
        head = text[:min(len(text), 48)]
        if matched.startswith(head) or text.startswith(matched[:48]):
            return True
    return False

def _negotiation_img(img_up: str) -> bool:
    try:
        from negotiation_reader import get_negotiation_profile
    except ImportError:
        return False
    return get_negotiation_profile(img_up) is not None

def _status_reply(analyzer, anchor: int, slots: list):
    try:
        from normal_play.equipment_repair_reader import read_repair_status_reply
        sr = read_repair_status_reply(analyzer, anchor)
    except Exception:
        return None
    if sr is None:
        return None
    start = sr[3]
    lo = start - STATUS_SLOT_WINDOW_BEFORE
    hi = start + STATUS_SLOT_WINDOW_AFTER
    if any((lo <= v <= hi for v in slots)):
        return tuple(sr[:3])
    return None

def _entry_prompt(cands):
    if cands is None:
        return None
    for c in cands:
        text = (getattr(c, 'text', '') or '').strip()
        if text.startswith(REPAIR_ENTRY_PROMPT):
            return (REPAIR_ENTRY_PROMPT, getattr(c, 'ptr', 0) or 0)
    return None

def _item_list_slot(slots: list) -> bool:
    try:
        from equipment_shop_list_reader import SELL_REPAIR_ITEM_LIST_OFFSET
    except ImportError:
        return False
    return any((v == SELL_REPAIR_ITEM_LIST_OFFSET for v in slots))

def _repair_jobs(analyzer, anchor: int) -> tuple:
    try:
        from normal_play.equipment_repair_reader import read_repair_jobs
        jobs = read_repair_jobs(analyzer, anchor)
    except Exception:
        return ()
    return tuple((j['en'] for j in jobs))

def _active_reply_candidates(cands) -> list:
    out = []
    if cands is None:
        return out
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        return out
    seen = set()
    for c in cands:
        text = (getattr(c, 'text', '') or '').strip()
        ptr = getattr(c, 'ptr', None)
        if not text or not isinstance(ptr, int):
            continue
        if not text.startswith(ACTIVE_REPLY_PREFIXES):
            continue
        try:
            if ndl.lookup(text) is None:
                continue
        except Exception:
            continue
        key = (ptr, text)
        if key in seen:
            continue
        out.append((text, ptr))
        seen.add(key)
    return out

def _is_composite_reply_text(text: str) -> bool:
    try:
        import npc_dialog_lookup as ndl
        return ndl.lookup_composite(text) is not None
    except Exception:
        return False

def read_signals(analyzer, anchor: int, *, foreground_ptr=_CURRENT_PTR_UNSET, img: str='', shop_state=None, window=None) -> dict:
    img_up = (img or '').upper()
    gate = _u8(analyzer, anchor, FRAME_OFFSET)
    ptr = _u16(analyzer, anchor, CURRENT_TEXT_PTR_OFFSET) if foreground_ptr is _CURRENT_PTR_UNSET else foreground_ptr
    ptr = ptr if isinstance(ptr, int) else None
    family = ptr >> 8 & 255 if ptr is not None else None
    list_flag = _u8(analyzer, anchor, LIST_FLAG_OFFSET)
    menu_box = gate not in (FRAME_POPUP, None)
    ptr_menu = ptr_menu_of(shop_state, ptr)
    slots = _read_active_slots(analyzer, anchor)
    try:
        from active_template_reader import read_active_template_candidates
        cands = read_active_template_candidates(analyzer, anchor)
    except Exception:
        cands = None
    negot_img = _negotiation_img(img_up)
    negot_body = _negotiation_body_live(analyzer, anchor, cands) if negot_img else False
    status = _status_reply(analyzer, anchor, slots)
    entry = _entry_prompt(cands)
    item_slot = _item_list_slot(slots)
    template_head = _read_raw_template_head(analyzer, anchor)
    estimate_template = is_estimate_template(template_head)
    jobs = _repair_jobs(analyzer, anchor) if img_up == INVENTORY_LIST_IMG else ()
    try:
        from popup11_response_reader import candidate_contains_pointer, read_response_candidates_all
        resp = read_response_candidates_all(analyzer, anchor)
    except Exception:
        resp = None
        candidate_contains_pointer = None
    hits = [c for c in resp if c.text and c.lookup_hit] if resp is not None else None
    estimate_text = ''
    reply_ptr = None
    reply_presence = None
    reply_changed = None
    if hits is not None:
        for c in hits:
            if is_estimate_rendered(c.text):
                estimate_text = c.text.strip()
                break
        for c in hits:
            if candidate_contains_pointer(c, ptr):
                reply_ptr = (c.text, c.source_offset)
                break
        if img_up in PRESENCE_IMGS:
            for c in hits:
                if c.text.startswith(PRESENCE_REPLY_PREFIXES) or is_no_repair_reply_text(c.text) or _is_composite_reply_text(c.text):
                    reply_presence = (c.text, c.source_offset)
                    break
    reply_active = _active_reply_candidates(cands)
    reply_active = reply_active[0] if reply_active else None
    basis_live = bool(menu_box or item_slot or negot_body or entry or status or (img_up == NEGOTIATION_IMG))
    if window is not None and resp is not None:
        now = {c.source_offset: c.text for c in resp if c.text}
        baseline = getattr(window, REPLY_BASELINE_ATTR, None)
        if baseline is None or basis_live:
            baseline = dict(now)
            setattr(window, REPLY_BASELINE_ATTR, baseline)
        changed = [c for c in hits or [] if baseline.get(c.source_offset) != c.text]
        reply_changed = (changed[0].text, changed[0].source_offset) if changed else False
    return {'img': img_up, **img_columns(img_up), 'gate': gate, 'menu_box': menu_box, 'ptr': ptr, 'family': family, 'ptr_menu': ptr_menu, 'list_flag': list_flag, 'list_fg': list_flag == LIST_FLAG_LIST if list_flag is not None else None, 'negot_img': negot_img, 'negot_body': negot_body, 'status': status, 'entry': entry, 'item_slot': item_slot, 'estimate_template': estimate_template, 'estimate_text': estimate_text, 'jobs': jobs, 'reply_ptr': reply_ptr, 'reply_active': reply_active, 'reply_presence': reply_presence, 'reply_changed': reply_changed}
__all__ = ['FRAME_OFFSET', 'CURRENT_TEXT_PTR_OFFSET', 'LIST_FLAG_OFFSET', 'RAW_TEMPLATE_OFFSET', 'DIALOG_PTR', 'FRAME_POPUP', 'LIST_FLAG_LIST', 'ESTIMATE_TEMPLATE_PREFIXES', 'REPAIR_ENTRY_PROMPT', 'REPLY_ALLOWED_IMGS', 'ACTIVE_REPLY_PREFIXES', 'PRESENCE_REPLY_PREFIXES', 'PRESENCE_IMGS', 'BUY_LIST_IMGS', 'NEGOTIATION_IMG', 'REPLY_BASELINE_ATTR', 'MENU_IMG', 'WEAPON_LIST_IMG', 'ARMOR_LIST_IMG', 'INVENTORY_LIST_IMG', 'REPAIR_MANAGE_IMG', 'CONFIRM_IMG', 'LIST_IMGS', 'REPAIR_POPUP_IMGS', 'img_columns', 'is_no_repair_reply_text', 'is_estimate_template', 'is_estimate_rendered', 'ptr_menu_of', 'reset_reply_baseline', 'read_signals']
