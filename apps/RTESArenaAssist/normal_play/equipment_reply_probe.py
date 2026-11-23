from __future__ import annotations
import logging
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')
_FG_PTR_OFFSET = 43076
_A846_OFFSET = 43078
_FRAME_OFFSET = 36724
_FRAME_TYPE_OFFSET = 36730
_TEXT_HEAD = 48

def _read_int(w, offset: int, size: int) -> int | None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + offset, size)
    except (OSError, AttributeError, TypeError):
        return None
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < size:
        return None
    return int.from_bytes(bytes(raw[:size]), 'little')

def _hex(value: int | None, width: int) -> str:
    return 'n/a' if value is None else f'0x{int(value):0{width}X}'

def note_reply_place_change(w, *, img: str, state: str) -> None:
    try:
        from popup11_response_reader import RESPONSE_OFFSETS, _read_one
        texts = tuple((_read_one(w._analyzer, w._anchor, off) for off in RESPONSE_OFFSETS))
    except Exception:
        return
    prev = getattr(w, '_equipment_reply_probe_texts', None)
    w._equipment_reply_probe_texts = texts
    if prev is None or prev == texts:
        return
    parts = []
    for off, text, old in zip(RESPONSE_OFFSETS, texts, prev):
        if text == old or not text:
            continue
        try:
            import npc_dialog_lookup as ndl
            hit = ndl.lookup(text) is not None
        except Exception:
            hit = None
        parts.append(f'0x{off:04X}:hit={hit}:{text[:_TEXT_HEAD]!r}')
    if not parts:
        return
    _recog(_log, 'equipment reply place changed: state=%s img=%r ptr=%s a846=%s frame=%s frame_type=%s %s', state, img, _hex(_read_int(w, _FG_PTR_OFFSET, 2), 4), _hex(_read_int(w, _A846_OFFSET, 2), 4), _hex(_read_int(w, _FRAME_OFFSET, 1), 2), _hex(_read_int(w, _FRAME_TYPE_OFFSET, 1), 2), ' '.join(parts))
__all__ = ['note_reply_place_change']
