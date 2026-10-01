from __future__ import annotations
import logging
from arena_aexe import AKEY_ACD_OFFSETS, detect_image_base
from assist_log import recog as _recog
import i18n_helper as i18n
_log = logging.getLogger('RTESArenaAssist')
OWNER = 'static_action_text'
_AKEYS = ('A425.0', 'A426.0', 'A427.0')
_IDS = tuple((f'npc_dialog.{key}' for key in _AKEYS))

def _panel_owner(w) -> str:
    try:
        return w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        return getattr(w, '_panel_owner', '') or ''

def _read_records(w) -> tuple[str, str, str]:
    anchor = getattr(w, '_anchor', None)
    if getattr(w, '_static_action_records_anchor', None) == anchor:
        return getattr(w, '_static_action_records', ('', '', ''))
    w._static_action_records_anchor = anchor
    out: list[str] = []
    try:
        detected = detect_image_base(w._analyzer, anchor)
        if not detected or detected[0] != 'ACD.EXE':
            raise ValueError('unsupported Arena executable')
        image_base = detected[1]
        for key in _AKEYS:
            raw = w._analyzer.read_bytes(image_base + AKEY_ACD_OFFSETS[key], 96)
            value = raw.split(b'\x00', 1)[0].decode('latin-1').strip()
            if not value or any((ord(ch) < 32 for ch in value)):
                raise ValueError(key)
            out.append(value)
    except (AttributeError, OSError, TypeError, UnicodeDecodeError, ValueError):
        out = ['', '', '']
    records = tuple(out)
    w._static_action_records = records
    return records

def _drawn_kind(w, band) -> int | None:
    if band.seen is not True:
        return getattr(w, '_static_action_shown_kind', None)
    records = _read_records(w)
    if not all(records):
        w._static_action_shown_kind = None
        return None
    hits = tuple((band.drawn_line([text]) == 0 for text in records))
    day = hits[0] or hits[1]
    night = hits[2]
    kind = None if day == night else 0 if day else 1
    w._static_action_shown_kind = kind
    return kind

def _payload(w, kind: int) -> tuple[str, str]:
    records = _read_records(w)
    indices = (0, 1) if kind == 0 else (2,)
    original = '\n'.join((records[index] for index in indices))
    translated = '\n'.join((i18n.text_opt(_IDS[index]) or records[index] for index in indices))
    return (original, translated)

def poll_static_action_text(w, *, band, in_play: bool) -> None:
    if not in_play:
        release_static_action_text(w)
        return
    kind = _drawn_kind(w, band)
    event = (band.episode, kind) if kind is not None else None
    if event is not None and event != getattr(w, '_static_action_event', None):
        owner = _panel_owner(w)
        if owner in ('', OWNER):
            original, translated = _payload(w, kind)
            w._static_action_event = event
            w._static_action_spoken_seen = False
            w._ui_router.update_translation(OWNER, original, translated, speech_role='situation', speech_action='reannounce')
            _recog(_log, '静的赤文字: 出す kind=%d episode=%d', kind, band.episode)
    _poll_lifetime(w, band)

def _poll_lifetime(w, band) -> None:
    if _panel_owner(w) != OWNER:
        w._static_action_spoken_seen = False
        return
    try:
        speaking_owner = w._translation_feed.speaking_owner()
    except AttributeError:
        speaking_owner = None
    try:
        speaking = bool(w._tts.is_speaking())
    except AttributeError:
        speaking = False
    if speaking_owner == OWNER and speaking:
        w._static_action_spoken_seen = True
        return
    if getattr(w, '_static_action_spoken_seen', False):
        w._static_action_spoken_seen = False
        w._ui_router.clear_if_owner(OWNER)
        return
    if band.seen is True and getattr(w, '_static_action_shown_kind', None) is None:
        w._ui_router.clear_if_owner(OWNER)

def release_static_action_text(w) -> None:
    w._static_action_shown_kind = None
    w._static_action_event = None
    w._static_action_spoken_seen = False
    if _panel_owner(w) == OWNER:
        w._ui_router.clear_if_owner(OWNER)
__all__ = ['OWNER', 'poll_static_action_text', 'release_static_action_text']
