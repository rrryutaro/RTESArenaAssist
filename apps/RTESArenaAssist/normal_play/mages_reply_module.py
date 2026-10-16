from __future__ import annotations
import logging
from mages_signals import CONFIRM_IMG as _CONFIRM_IMG
from normal_play.mages_owner_names import REPLY_OWNER
_log = logging.getLogger('RTESArenaAssist')
_RESPONSE_TEXT_OFFSET = 4164
_NEGOTIATION_TEXT_OFFSET = 37534
_MAGES_MENU_TEXT_OFFSET = 28508
_DETECT_MAGIC_QUOTE_PREFIX = 'I can tell you if that is magical'
_DETECT_MAGIC_ALREADY_KNOWN = 'You already know what that is!'
_DETECT_MAGIC_IDENTIFIED = 'The item is now identified in your inventory.'

def _normalize_reply_text(text: str) -> str:
    s = (text or '').replace('\r', ' ').replace('\n', ' ').replace('\x00', ' ')
    return ' '.join(s.split())

def _reset_state(w) -> None:
    w._mages_reply_current_key = None
    w._mages_reply_current_text = None
    w._mages_reply_baselined = False

def _clear_reply_owner(w) -> None:
    _reset_state(w)
    try:
        if getattr(w, '_panel_owner', '') == REPLY_OWNER:
            w._ui_router.clear_if_owner(REPLY_OWNER)
    except AttributeError:
        pass

def reset_mages_reply_state(w) -> None:
    _reset_state(w)

def _ensure_state(w) -> None:
    if not hasattr(w, '_mages_reply_current_key'):
        w._mages_reply_current_key = None
    if not hasattr(w, '_mages_reply_current_text'):
        w._mages_reply_current_text = None
    if not hasattr(w, '_mages_reply_baselined'):
        w._mages_reply_baselined = False

def _with_yesno_buttons(img_name: str, en: str, ja: str) -> tuple[str, str]:
    if (img_name or '').upper() != _CONFIRM_IMG:
        return (en, ja)
    try:
        from negotiation_reader import get_negotiation_profile
        profile = get_negotiation_profile(_CONFIRM_IMG)
    except ImportError:
        profile = None
    if not profile:
        return (en, ja)
    en_buttons = '  '.join(profile['buttons_en'])
    ja_buttons = '  '.join(profile['buttons_ja'])
    return (f'{en_buttons}\n{en}', f'{ja_buttons}\n{ja}')

def _read_cstr(w, off: int, length: int) -> str:
    try:
        raw = w._analyzer.read_bytes(w._anchor + off, length)
    except (OSError, AttributeError):
        return ''
    if not isinstance(raw, (bytes, bytearray)):
        return ''
    return bytes(raw).split(b'\x00', 1)[0].decode('ascii', errors='replace')

def _reply_text(w, reply_kind: str) -> str:
    if reply_kind == 'detect_result':
        return _DETECT_MAGIC_IDENTIFIED
    if reply_kind == 'detect_cost':
        text = _normalize_reply_text(_read_cstr(w, _RESPONSE_TEXT_OFFSET, 160))
        return text if _DETECT_MAGIC_QUOTE_PREFIX in text else ''
    if reply_kind == 'detect_known':
        text = _normalize_reply_text(_read_cstr(w, _MAGES_MENU_TEXT_OFFSET, 96))
        return text if text == _DETECT_MAGIC_ALREADY_KNOWN else ''
    return ''

def poll_mages_reply(w, *, mages_active: bool, mages_just_started: bool, img_name: str, view=None) -> bool:
    _ensure_state(w)
    if not mages_active:
        return False
    kind = getattr(view, 'l4_kind', '') or ''
    if kind != 'reply':
        if kind not in ('', 'none'):
            _clear_reply_owner(w)
        return False
    if mages_just_started:
        _reset_state(w)
    reply_kind = getattr(view, 'reply_kind', '') or ''
    chosen_text = _reply_text(w, reply_kind)
    if not chosen_text:
        return False
    w._mages_reply_baselined = True
    try:
        import npc_dialog_lookup as _ndl
        _r = _ndl.lookup(chosen_text)
    except Exception:
        _r = None
    if not _r:
        return False
    _ja_tmpl, _ph = _r
    ja = _ndl.format_japanese(_ja_tmpl, _ph)
    img = (img_name or '').upper()
    if reply_kind == 'detect_result':
        en_text, ja_text = (chosen_text, ja)
    else:
        en_text, ja_text = _with_yesno_buttons(img, chosen_text, ja)
    key = (reply_kind, chosen_text, ja_text)
    if key != w._mages_reply_current_key:
        w._mages_reply_current_key = key
        w._mages_reply_current_text = chosen_text
        w._ui_router.update_translation(REPLY_OWNER, en_text, ja_text, speech_role='conversation', speech_text=ja)
        _log.info('mages_reply translated: kind=%s img=%r text=%r', reply_kind, img, chosen_text[:80])
    return True
__all__ = ['poll_mages_reply', 'reset_mages_reply_state', 'REPLY_OWNER']
