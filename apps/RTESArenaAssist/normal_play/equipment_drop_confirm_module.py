from __future__ import annotations
import logging
import re
import i18n_helper as i18n
from assist_log import recog as _recog
from panel_mode_resolver import SCREEN_PANEL_PRIORITY
_log = logging.getLogger('equipment_drop_confirm_module')
OWNER = 'equipment_drop_confirm'
_FRAME_OFFSET = 36724
_TEXT_OFFSET = 4164
_TEXT_READ_LEN = 96
_CONFIRM_AKEYS = ('A201.0', 'A202.0')
_PLACEHOLDER = re.compile('%[a-z][a-z0-9]*')

def _normalize(text: str) -> str:
    return ' '.join((text or '').split())

def _original(akey: str) -> str:
    return i18n.original_by_source_id(f'aexe:akey:{akey}', category='npc_dialog') or i18n.original(f'npc_dialog.{akey}') or ''

def _match(akey: str, text: str):
    original = _normalize(_original(akey))
    if not original:
        return None
    names = _PLACEHOLDER.findall(original)
    if not names:
        return () if text == original else None
    pieces = _PLACEHOLDER.split(original)
    pattern = re.escape(pieces[0])
    for name, piece in zip(names, pieces[1:]):
        pattern += '(.+?)' + re.escape(piece)
    m = re.fullmatch(pattern, text)
    return tuple(zip(names, m.groups())) if m else None

def _read_open_text(w) -> str | None:
    try:
        frame = w._analyzer.read_bytes(w._anchor + _FRAME_OFFSET, 1)
        raw = w._analyzer.read_bytes(w._anchor + _TEXT_OFFSET, _TEXT_READ_LEN)
    except (OSError, AttributeError):
        return None
    if not isinstance(frame, (bytes, bytearray)) or not frame or frame[0] == 0:
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    return _normalize(bytes(raw).split(b'\x00', 1)[0].decode('latin-1')) or None

def _read_visible(w):
    text = _read_open_text(w)
    if not text:
        return None
    for akey in _CONFIRM_AKEYS:
        values = _match(akey, text)
        if values is not None:
            return (akey, values)
    if getattr(w, '_equipment_drop_confirm_unknown', None) != text:
        w._equipment_drop_confirm_unknown = text
        _recog(_log, 'equipment confirm unknown text: %r', text[:80])
    return None

def read_visible_confirm(w) -> str | None:
    found = _read_visible(w)
    return found[0] if found else None

def _fill(text: str, values, *, translate: bool) -> str:
    for name, value in values:
        if translate and name == '%ni':
            from item_name_lookup import translate_item_name_opt
            value = translate_item_name_opt(value) or value
        text = text.replace(name, value, 1)
    return text

def poll_equipment_drop_confirm(w) -> bool:
    found = _read_visible(w)
    if found is None:
        reset_equipment_drop_confirm(w)
        return False
    akey, values = found
    if getattr(w, '_equipment_drop_confirm_key', None) == (akey, values):
        return True
    key = f'npc_dialog.{akey}'
    en = _fill(_original(akey), values, translate=False)
    ja = i18n.text_opt(key)
    if not ja:
        return True
    ja = _fill(ja, values, translate=True)
    w._equipment_drop_confirm_key = (akey, values)
    _recog(_log, 'equipment confirm open: key=%s', key)
    w._ui_router.propose_translation(OWNER, en, ja, mode='translate', floor_mode='equipment', priority=SCREEN_PANEL_PRIORITY + 1, reason='equipment:drop_confirm', speech_role='situation', speech_text=ja)
    return True

def reset_equipment_drop_confirm(w) -> None:
    previous = getattr(w, '_equipment_drop_confirm_key', None)
    if previous is not None:
        _recog(_log, 'equipment confirm closed: key=npc_dialog.%s', previous[0])
        router = getattr(w, '_ui_router', None)
        if router is not None:
            router.notify_display_unit_closed(OWNER)
            router.clear_if_owner(OWNER)
    w._equipment_drop_confirm_key = None
__all__ = ['OWNER', 'poll_equipment_drop_confirm', 'read_visible_confirm', 'reset_equipment_drop_confirm']
