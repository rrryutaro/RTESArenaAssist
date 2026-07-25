from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
EQUIPMENT_OWNERS = frozenset({'equipment_menu', 'equipment_list', 'equipment_negotiation', 'equipment_reply', 'equipment_repair'})

class EquipmentL4State(str, Enum):
    MENU = 'menu'
    BUY_LIST = 'buy_list'
    ITEM_SELECT = 'item_select'
    REPAIR_ENTRY = 'repair_entry'
    REPAIR_JOBS = 'repair_jobs'
    REPAIR_STATUS_REPLY = 'repair_status_reply'
    REPAIR_DONE_REPLY = 'repair_done_reply'
    REPAIR_ESTIMATE = 'repair_estimate'
    REPLY = 'reply'
    NEGOTIATION = 'negotiation'
    NONE = 'none'
REPLY_STATES = frozenset({EquipmentL4State.REPAIR_ENTRY, EquipmentL4State.REPAIR_STATUS_REPLY, EquipmentL4State.REPAIR_DONE_REPLY, EquipmentL4State.REPAIR_ESTIMATE, EquipmentL4State.REPLY})

@dataclass(frozen=True)
class EquipmentL4Snapshot:
    state: EquipmentL4State = EquipmentL4State.NONE
    img: str = ''
    reason: str = ''
    repair_job_names: tuple = ()
    status_reply: tuple = ()
    reply_text: str = ''
    reply_source_offset: int = 0
VIEW_FLAG_OFFSET = 36724
VIEW_FLAG_MENU = 81
VIEW_FLAG_POPUP = 0
_MENU_FLAG_STABLE_POLLS = 2
_NONE_STABLE_POLLS = 2
_RAW_TEMPLATE_OFFSET = 4164
_RAW_TEMPLATE_READ_LEN = 192
_ESTIMATE_TEMPLATE_PREFIXES = ('Sure I could fix that ', 'Fixing that ')
_REPAIR_ENTRY_PROMPT = 'Which job do you wish to inspect?'
_STATUS_SLOT_WINDOW_BEFORE = 16
_STATUS_SLOT_WINDOW_AFTER = 96
_REPLY_ALLOWED_IMGS = frozenset({'MENU_RT.IMG', 'YESNO.IMG', 'NEWPOP.IMG', 'NEWOLD.IMG'})
_ACTIVE_REPLY_PREFIXES = ("Can't you afford it?", "Can't you wait that long?", "Maybe you're not interested?", 'Which job do you wish to inspect?', 'Sorry, I already have my hands full.')
_PRESENCE_REPLY_PREFIXES = ('I can cut down the time', 'I can cut the cost', "Then I'll get started", "Good, I'll get to it", 'I understand. You might consider', 'Well, if you change your mind', 'Sorry, I already have my hands full.')

def _is_no_repair_reply_text(text: str) -> bool:
    text = (text or '').strip()
    return text.startswith('Your ') and 'does not need any repairing' in text

def _is_composite_reply_text(text: str) -> bool:
    try:
        import npc_dialog_lookup as ndl
        return ndl.lookup_composite(text) is not None
    except Exception:
        return False

def read_view_flag(w):
    try:
        raw = w._analyzer.read_bytes(w._anchor + VIEW_FLAG_OFFSET, 1)
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            return None
        return raw[0]
    except Exception:
        return None

def _track_menu_flag(w):
    val = read_view_flag(w)
    if val is None:
        return (getattr(w, '_equipment_l4_flag_value', None), bool(getattr(w, '_equipment_l4_menu_stable', False)))
    w._equipment_l4_flag_value = val
    if val == VIEW_FLAG_MENU:
        w._equipment_l4_menu_flag_polls = int(getattr(w, '_equipment_l4_menu_flag_polls', 0) or 0) + 1
    else:
        w._equipment_l4_menu_flag_polls = 0
    stable = int(getattr(w, '_equipment_l4_menu_flag_polls', 0) or 0) >= _MENU_FLAG_STABLE_POLLS
    w._equipment_l4_menu_stable = stable
    return (val, stable)

def _read_raw_template_head(w) -> str:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _RAW_TEMPLATE_OFFSET, _RAW_TEMPLATE_READ_LEN)
    except Exception:
        return ''
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return ''
    end = raw.find(b'\x00')
    if end == -1:
        end = len(raw)
    return raw[:end].decode('ascii', errors='replace')

def _estimate_template_active(w) -> bool:
    head = _read_raw_template_head(w)
    return bool(head) and head.startswith(_ESTIMATE_TEMPLATE_PREFIXES)

def _active_slot_points_item_list(w) -> bool:
    try:
        from equipment_shop_list_reader import SELL_REPAIR_ITEM_LIST_OFFSET
        from active_template_reader import ACTIVE_TEMPLATE_PTR_OFFSETS
        for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
            raw = w._analyzer.read_bytes(w._anchor + off, 2)
            if len(raw) == 2 and raw[0] | raw[1] << 8 == SELL_REPAIR_ITEM_LIST_OFFSET:
                return True
    except Exception:
        return False
    return False

def _active_slot_hits_status_window(w, start: int) -> bool:
    try:
        from active_template_reader import ACTIVE_TEMPLATE_PTR_OFFSETS
        lo = start - _STATUS_SLOT_WINDOW_BEFORE
        hi = start + _STATUS_SLOT_WINDOW_AFTER
        for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
            raw = w._analyzer.read_bytes(w._anchor + off, 2)
            if len(raw) == 2 and lo <= raw[0] | raw[1] << 8 <= hi:
                return True
    except Exception:
        return False
    return False

def _entry_prompt_candidate(w):
    try:
        from active_template_reader import read_active_template_candidates
        for c in read_active_template_candidates(w._analyzer, w._anchor):
            text = (getattr(c, 'text', '') or '').strip()
            if text.startswith(_REPAIR_ENTRY_PROMPT):
                return (_REPAIR_ENTRY_PROMPT, getattr(c, 'ptr', 0) or 0)
    except Exception:
        return None
    return None

def _read_repair_jobs(w) -> list:
    try:
        from normal_play.equipment_repair_reader import read_repair_jobs
        return read_repair_jobs(w._analyzer, w._anchor)
    except Exception:
        return []

def has_equipment_negotiation_foreground(w) -> bool:
    try:
        from negotiation_reader import NEGOT_RENDERED_OFFSET, read_negotiation_diagnostic
        _raw, _canon, _rendered, matched = read_negotiation_diagnostic(w._analyzer, w._anchor)
        if not matched:
            return False
        from active_template_reader import read_active_template_candidates
        for c in read_active_template_candidates(w._analyzer, w._anchor):
            if getattr(c, 'ptr', None) != NEGOT_RENDERED_OFFSET:
                continue
            text = (getattr(c, 'text', '') or '').strip()
            if not text:
                return True
            head = text[:min(len(text), 48)]
            if matched.startswith(head) or text.startswith(matched[:48]):
                return True
    except Exception:
        return False
    return False

def _is_negotiation_img(img: str) -> bool:
    try:
        from negotiation_reader import get_negotiation_profile
    except ImportError:
        return False
    return get_negotiation_profile(img) is not None

def _read_active_reply_candidates(w):
    out = []
    try:
        from popup11_response_reader import ResponseCandidate
        from active_template_reader import read_active_template_candidates
        import npc_dialog_lookup as ndl
        seen = set()
        for c in read_active_template_candidates(w._analyzer, w._anchor):
            text = (getattr(c, 'text', '') or '').strip()
            ptr = getattr(c, 'ptr', None)
            if not text or not isinstance(ptr, int):
                continue
            if not text.startswith(_ACTIVE_REPLY_PREFIXES):
                continue
            try:
                if ndl.lookup(text) is None:
                    continue
            except Exception:
                continue
            key = (ptr, text)
            if key in seen:
                continue
            out.append(ResponseCandidate(text=text, lookup_hit=True, source_offset=ptr))
            seen.add(key)
    except Exception:
        return []
    return out

def _update_and_select_reply(w, img: str):
    try:
        from popup11_response_reader import candidate_contains_pointer, read_current_text_pointer, read_response_candidates_all
        candidates = read_response_candidates_all(w._analyzer, w._anchor)
        current_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        candidates = []
        current_ptr = None
    active_candidates = _read_active_reply_candidates(w)
    prev_by_offset = dict(getattr(w, '_equipment_l4_resp_prev_by_offset', {}) or {})
    baselined = bool(getattr(w, '_equipment_l4_resp_baselined', False))
    hits = [c for c in candidates if c.text and c.lookup_hit]
    ptr_hits = [c for c in hits if candidate_contains_pointer(c, current_ptr)]
    presence_hits = []
    if img in ('NEWPOP.IMG', 'NEWOLD.IMG', 'YESNO.IMG'):
        presence_hits = [c for c in hits if c.text.startswith(_PRESENCE_REPLY_PREFIXES) or _is_no_repair_reply_text(c.text) or _is_composite_reply_text(c.text)]
    changed_hits = [c for c in hits if baselined and prev_by_offset.get(c.source_offset) != c.text]
    now_by_offset = dict(prev_by_offset)
    for c in candidates:
        if c.text:
            now_by_offset[c.source_offset] = c.text
    w._equipment_l4_resp_prev_by_offset = now_by_offset
    w._equipment_l4_resp_baselined = True
    prev_reply_text = getattr(w, '_equipment_l4_prev_reply_text', '') or ''
    prev_was_reply = getattr(w, '_equipment_l4_prev_state', None) is EquipmentL4State.REPLY
    continuation_hits = [c for c in hits if prev_was_reply and prev_reply_text and (c.text == prev_reply_text)]
    if ptr_hits:
        return ptr_hits[0]
    if active_candidates:
        return active_candidates[0]
    if presence_hits:
        return presence_hits[0]
    if changed_hits:
        return changed_hits[0]
    if continuation_hits:
        return continuation_hits[0]
    return None

def _decide(w, img: str) -> EquipmentL4Snapshot:
    S = EquipmentL4State
    flag_value, menu_stable = _track_menu_flag(w)
    if menu_stable:
        return EquipmentL4Snapshot(state=S.MENU, img=img, reason='view_flag')
    if img == 'NEGOTBUT.IMG' or (_is_negotiation_img(img) and has_equipment_negotiation_foreground(w)):
        return EquipmentL4Snapshot(state=S.NEGOTIATION, img=img, reason='negotiation')
    if img == 'YESNO.IMG' and _estimate_template_active(w):
        return EquipmentL4Snapshot(state=S.REPAIR_ESTIMATE, img=img, reason='estimate_template')
    if flag_value == VIEW_FLAG_POPUP and img in ('NEWPOP.IMG', 'NEWOLD.IMG'):
        try:
            from normal_play.equipment_repair_reader import read_repair_status_reply
            sr = read_repair_status_reply(w._analyzer, w._anchor)
        except Exception:
            sr = None
        if sr is not None and _active_slot_hits_status_window(w, sr[3]):
            state = S.REPAIR_DONE_REPLY if sr[0] == 'done' else S.REPAIR_STATUS_REPLY
            return EquipmentL4Snapshot(state=state, img=img, reason='rendered_band', status_reply=tuple(sr[:3]))
    if img == 'NEWOLD.IMG':
        entry = _entry_prompt_candidate(w)
        if entry is not None:
            return EquipmentL4Snapshot(state=S.REPAIR_ENTRY, img=img, reason='entry_prompt', reply_text=entry[0], reply_source_offset=entry[1])
    if img == 'NEWPOP.IMG' and _active_slot_points_item_list(w):
        return EquipmentL4Snapshot(state=S.ITEM_SELECT, img=img, reason='item_list_slot')
    if img == 'NEWPOP.IMG':
        jobs = _read_repair_jobs(w)
        if jobs:
            return EquipmentL4Snapshot(state=S.REPAIR_JOBS, img=img, reason='repair_struct', repair_job_names=tuple((j['en'] for j in jobs)))
    if img in _REPLY_ALLOWED_IMGS:
        chosen = _update_and_select_reply(w, img)
        if chosen is not None:
            return EquipmentL4Snapshot(state=S.REPLY, img=img, reason='response_evidence', reply_text=chosen.text, reply_source_offset=chosen.source_offset)
    if img in ('POPUP3.IMG', 'POPUP4.IMG'):
        return EquipmentL4Snapshot(state=S.BUY_LIST, img=img, reason='list_img')
    return EquipmentL4Snapshot(state=S.NONE, img=img, reason='none')

def _compute(w, img: str) -> EquipmentL4Snapshot:
    snap = _decide(w, img)
    prev_state = getattr(w, '_equipment_l4_prev_state', None)
    if snap.state is EquipmentL4State.NONE:
        streak = int(getattr(w, '_equipment_l4_none_streak', 0) or 0) + 1
        w._equipment_l4_none_streak = streak
        prev_snap = getattr(w, '_equipment_l4_prev_snapshot', None)
        if streak < _NONE_STABLE_POLLS and prev_state is not None and (prev_state is not EquipmentL4State.NONE) and (prev_snap is not None):
            snap = prev_snap
    else:
        w._equipment_l4_none_streak = 0
    w._equipment_l4_prev_state = snap.state
    w._equipment_l4_prev_snapshot = snap
    if snap.state is EquipmentL4State.REPLY:
        w._equipment_l4_prev_reply_text = snap.reply_text
    elif snap.state is not EquipmentL4State.NONE:
        w._equipment_l4_prev_reply_text = ''
    return snap

def get_equipment_l4_state(w, *, img: str) -> EquipmentL4Snapshot:
    seq = getattr(w, '_poll_seq', None)
    if seq is not None and getattr(w, '_equipment_l4_snapshot_seq', None) == seq:
        cached = getattr(w, '_equipment_l4_snapshot', None)
        if cached is not None:
            return cached
    snap = _compute(w, (img or '').upper())
    if seq is not None:
        w._equipment_l4_snapshot = snap
        w._equipment_l4_snapshot_seq = seq
    return snap

def peek_equipment_l4_state(w):
    seq = getattr(w, '_poll_seq', None)
    if seq is None or getattr(w, '_equipment_l4_snapshot_seq', None) != seq:
        return None
    return getattr(w, '_equipment_l4_snapshot', None)

def reset_equipment_l4_state(w) -> None:
    w._equipment_l4_snapshot = None
    w._equipment_l4_snapshot_seq = None
    w._equipment_l4_flag_value = None
    w._equipment_l4_menu_flag_polls = 0
    w._equipment_l4_menu_stable = False
    w._equipment_l4_none_streak = 0
    w._equipment_l4_prev_state = None
    w._equipment_l4_prev_snapshot = None
    w._equipment_l4_prev_reply_text = ''
    w._equipment_l4_resp_prev_by_offset = {}
    w._equipment_l4_resp_baselined = False
__all__ = ['EQUIPMENT_OWNERS', 'EquipmentL4Snapshot', 'EquipmentL4State', 'REPLY_STATES', 'VIEW_FLAG_MENU', 'VIEW_FLAG_OFFSET', 'VIEW_FLAG_POPUP', 'get_equipment_l4_state', 'has_equipment_negotiation_foreground', 'peek_equipment_l4_state', 'read_view_flag', 'reset_equipment_l4_state']
