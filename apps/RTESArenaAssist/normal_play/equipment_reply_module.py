from __future__ import annotations
import logging
from normal_play.equipment_l4_state import EquipmentL4State, REPLY_STATES, get_equipment_l4_state
_log = logging.getLogger('RTESArenaAssist')
REPLY_OWNER = 'equipment_reply'
_RENDER_KEY = '_equipment_reply_render_key'
_REPAIR_BUTTONS_EN = ('ADD JOB', 'STATUS', 'CANCEL')
_REPAIR_BUTTONS_JA = ('ジョブ追加', '状態', 'キャンセル')
_BUTTON_ROW_SEP = '  '
_ACTIVE_REPLY_CHOICE_PREFIXES = ("Can't you afford it?", "Can't you wait that long?", "Maybe you're not interested?")
_ESTIMATE_RENDERED_PREFIXES = ('Sure I could fix that ', 'Fixing that ')

def _reset_state(w) -> None:
    setattr(w, _RENDER_KEY, None)

def reset_equipment_reply_state(w) -> None:
    _reset_state(w)

def cleanup_equipment_reply_if_owner(w) -> None:
    if getattr(w, _RENDER_KEY, None) is None:
        return
    setattr(w, _RENDER_KEY, None)
    if getattr(w, '_panel_owner', '') == REPLY_OWNER:
        try:
            if w._tab_translate.panel_mode() == 'facility_list':
                w._ui_router.set_panel_mode('translate')
        except AttributeError:
            pass
        w._ui_router.clear_if_owner(REPLY_OWNER, mode='translate')

def _lookup_ja(text: str) -> str | None:
    try:
        import npc_dialog_lookup as ndl
        result = ndl.lookup(text)
        if result is None:
            return None
        ja_tmpl, placeholders = result
        return ndl.format_japanese(ja_tmpl, placeholders)
    except Exception:
        return None

def _yesno_button_row() -> tuple[str, str]:
    try:
        from negotiation_reader import get_negotiation_profile
        profile = get_negotiation_profile('YESNO.IMG')
    except ImportError:
        profile = None
    if not profile:
        return ('', '')
    return (_BUTTON_ROW_SEP.join(profile['buttons_en']), _BUTTON_ROW_SEP.join(profile['buttons_ja']))

def _with_buttons_above(en: str, ja: str, buttons_en: str, buttons_ja: str) -> tuple[str, str]:
    if not buttons_en:
        return (en, ja)
    return (f'{buttons_en}\n{en}', f'{buttons_ja}\n{ja}')

def _read_c_string(analyzer, anchor: int, offset: int, maxlen: int=96) -> str:
    try:
        raw = analyzer.read_bytes(anchor + offset, maxlen)
    except (OSError, AttributeError):
        return ''
    end = raw.find(b'\x00')
    if end == -1:
        end = len(raw)
    return raw[:end].decode('ascii', errors='replace').strip()

def _read_active_reply_choice_group(analyzer, anchor: int, start_offset: int) -> list[str]:
    first = _read_c_string(analyzer, anchor, start_offset)
    if first != _ACTIVE_REPLY_CHOICE_PREFIXES[0]:
        return []
    out: list[str] = []
    cur = start_offset
    for expected in _ACTIVE_REPLY_CHOICE_PREFIXES:
        text = _read_c_string(analyzer, anchor, cur)
        if text != expected:
            break
        out.append(text)
        cur += len(text.encode('ascii', errors='ignore')) + 1
    return out if len(out) > 1 else []

def _format_reply_choice_rows(lines: list[str]) -> list[dict]:
    rows: list[dict] = []
    for line in lines:
        ja = _lookup_ja(line) or line
        rows.append({'en': line, 'ja': ja})
    return rows

def _update(w, *, key, en_display: str, ja_display: str, speech_ja: str='', log_text: str='') -> bool:
    owner_taken = getattr(w, '_panel_owner', '') != REPLY_OWNER
    if key == getattr(w, _RENDER_KEY, None) and (not owner_taken):
        return True
    setattr(w, _RENDER_KEY, key)
    if speech_ja:
        w._ui_router.update_translation(REPLY_OWNER, en_display, ja_display, speech_role='conversation', speech_text=speech_ja)
    else:
        w._ui_router.update_translation(REPLY_OWNER, en_display, ja_display)
    if log_text:
        _log.info('equipment_reply: %s', log_text)
    return True

def _render_repair_entry(w, snapshot) -> bool:
    en = snapshot.reply_text
    ja = _lookup_ja(en) or en
    en_display, ja_display = _with_buttons_above(en, ja, _BUTTON_ROW_SEP.join(_REPAIR_BUTTONS_EN), _BUTTON_ROW_SEP.join(_REPAIR_BUTTONS_JA))
    return _update(w, key=('repair_entry', en, ja), en_display=en_display, ja_display=ja_display, speech_ja=ja, log_text=f'repair-entry {en[:60]!r}')

def _render_repair_status(w, snapshot) -> bool:
    if not snapshot.status_reply:
        return False
    kind, en, ja = snapshot.status_reply
    return _update(w, key=('repair_status', kind, en, ja), en_display=en, ja_display=ja, speech_ja=ja, log_text=f'repair-status kind={kind} text={en[:60]!r}')

def _find_rendered_estimate(w) -> str:
    try:
        from popup11_response_reader import read_response_candidates_all
        candidates = read_response_candidates_all(w._analyzer, w._anchor)
    except Exception:
        return ''
    for c in candidates:
        text = (c.text or '').strip()
        if not text or not c.lookup_hit:
            continue
        if '%' in text:
            continue
        if text.startswith(_ESTIMATE_RENDERED_PREFIXES):
            return text
    return ''

def _render_repair_estimate(w, snapshot) -> bool:
    en = _find_rendered_estimate(w)
    if not en:
        return True
    ja = _lookup_ja(en) or en
    btn_en, btn_ja = _yesno_button_row()
    en_display, ja_display = _with_buttons_above(en, ja, btn_en, btn_ja)
    return _update(w, key=('repair_estimate', en, ja), en_display=en_display, ja_display=ja_display, speech_ja=ja, log_text=f'repair-estimate text={en[:60]!r}')

def _lookup_composite(en: str):
    try:
        import npc_dialog_lookup as ndl
        return ndl.lookup_composite(en)
    except Exception:
        return None

def _render_generic_reply(w, snapshot) -> bool:
    en = snapshot.reply_text
    if not en:
        return False
    composite = _lookup_composite(en)
    if composite is not None:
        en_display, ja_display = composite
        return _update(w, key=('reply_composite', en_display, ja_display), en_display=en_display, ja_display=ja_display, speech_ja=ja_display, log_text=f'reply-composite {en_display[:60]!r}')
    choice_lines = _read_active_reply_choice_group(w._analyzer, w._anchor, snapshot.reply_source_offset)
    if choice_lines:
        rows = _format_reply_choice_rows(choice_lines)
        owner_taken = getattr(w, '_panel_owner', '') != REPLY_OWNER
        key = ('reply_choices', tuple(((r['en'], r['ja']) for r in rows)))
        if key == getattr(w, _RENDER_KEY, None) and (not owner_taken):
            return True
        setattr(w, _RENDER_KEY, key)
        w._ui_router.update_facility_list(REPLY_OWNER, rows, 'Repair Options', '修理の選択肢')
        _log.info('equipment_reply choices: %d rows', len(rows))
        return True
    ja = _lookup_ja(en)
    if ja is None:
        return False
    en_display, ja_display = (en, ja)
    if snapshot.img == 'YESNO.IMG':
        btn_en, btn_ja = _yesno_button_row()
        en_display, ja_display = _with_buttons_above(en, ja, btn_en, btn_ja)
    return _update(w, key=('reply', en, ja), en_display=en_display, ja_display=ja_display, speech_ja=ja, log_text=f'reply text={en[:60]!r}')

def render_equipment_reply_state(w, snapshot) -> bool:
    state = getattr(snapshot, 'state', None)
    if state is EquipmentL4State.REPAIR_ENTRY:
        return _render_repair_entry(w, snapshot)
    if state in (EquipmentL4State.REPAIR_STATUS_REPLY, EquipmentL4State.REPAIR_DONE_REPLY):
        return _render_repair_status(w, snapshot)
    if state is EquipmentL4State.REPAIR_ESTIMATE:
        return _render_repair_estimate(w, snapshot)
    if state is EquipmentL4State.REPLY:
        return _render_generic_reply(w, snapshot)
    return False

def poll_equipment_reply(w, *, equipment_active: bool, equipment_just_started: bool, img_name: str, shop_menu_visible: bool) -> bool:
    if not equipment_active:
        return False
    if equipment_just_started:
        _reset_state(w)
    snapshot = get_equipment_l4_state(w, img=(img_name or '').upper())
    if snapshot.state not in REPLY_STATES:
        return False
    return render_equipment_reply_state(w, snapshot)
__all__ = ['poll_equipment_reply', 'render_equipment_reply_state', 'reset_equipment_reply_state', 'cleanup_equipment_reply_if_owner', 'REPLY_OWNER']
