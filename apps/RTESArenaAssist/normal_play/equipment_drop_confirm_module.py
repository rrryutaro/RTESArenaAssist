from __future__ import annotations
import logging
import i18n_helper as i18n
from assist_log import recog as _recog
from panel_mode_resolver import SCREEN_PANEL_PRIORITY
_log = logging.getLogger('equipment_drop_confirm_module')
OWNER = 'equipment_drop_confirm'
_FRAME_OFFSET = 36724
_TEXT_OFFSET = 4164
_TEXT_READ_LEN = 96
_CONFIRM_AKEYS = ('A201.0',)

def _normalize(text: str) -> str:
    return ' '.join((text or '').split())

def _original(akey: str) -> str:
    return i18n.original_by_source_id(f'aexe:akey:{akey}', category='npc_dialog') or i18n.original(f'npc_dialog.{akey}') or ''

def read_visible_confirm(w) -> str | None:
    try:
        frame = w._analyzer.read_bytes(w._anchor + _FRAME_OFFSET, 1)
        raw = w._analyzer.read_bytes(w._anchor + _TEXT_OFFSET, _TEXT_READ_LEN)
    except (OSError, AttributeError):
        return None
    if not isinstance(frame, (bytes, bytearray)) or not frame or frame[0] == 0:
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    text = _normalize(bytes(raw).split(b'\x00', 1)[0].decode('latin-1'))
    if not text:
        return None
    for akey in _CONFIRM_AKEYS:
        if text == _normalize(_original(akey)):
            return akey
    return None

def poll_equipment_drop_confirm(w) -> bool:
    akey = read_visible_confirm(w)
    if akey is None:
        reset_equipment_drop_confirm(w)
        return False
    if getattr(w, '_equipment_drop_confirm_key', None) == akey:
        return True
    key = f'npc_dialog.{akey}'
    en = _original(akey)
    ja = i18n.text_opt(key)
    if not ja:
        return True
    w._equipment_drop_confirm_key = akey
    _recog(_log, 'equipment confirm open: key=%s', key)
    w._ui_router.propose_translation(OWNER, en, ja, mode='translate', floor_mode='equipment', priority=SCREEN_PANEL_PRIORITY + 1, reason='equipment:drop_confirm', speech_role='situation', speech_text=ja)
    return True

def reset_equipment_drop_confirm(w) -> None:
    previous = getattr(w, '_equipment_drop_confirm_key', None)
    if previous is not None:
        _recog(_log, 'equipment confirm closed: key=npc_dialog.%s', previous)
        router = getattr(w, '_ui_router', None)
        if router is not None:
            router.notify_display_unit_closed(OWNER)
            router.clear_if_owner(OWNER)
    w._equipment_drop_confirm_key = None
__all__ = ['OWNER', 'poll_equipment_drop_confirm', 'read_visible_confirm', 'reset_equipment_drop_confirm']
