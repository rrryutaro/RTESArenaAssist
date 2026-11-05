from __future__ import annotations
import logging
from active_template_reader import is_dialog_text_pointer
from assist_log import recog as _recog
from normal_play.c1_dialog_axis import area_of
_log = logging.getLogger('RTESArenaAssist')
_A846_OFFSET = 43078
_POPUP_FLAG_OFFSET = 31012
_FRAME_OFFSET = 36724

def _read(w, offset: int, size: int) -> int | None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + offset, size)
    except (OSError, AttributeError, TypeError):
        return None
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < size:
        return None
    return int.from_bytes(bytes(raw[:size]), 'little')

def note_text_window_signals(w, *, area: str | None, in_gameplay: bool, fg_ptr: int | None, overlay_gameplay: bool) -> None:
    a846 = _read(w, _A846_OFFSET, 2)
    popup = _read(w, _POPUP_FLAG_OFFSET, 1)
    frame = _read(w, _FRAME_OFFSET, 1)
    ptr_area = area_of(fg_ptr)
    if not ptr_area:
        ptr_area = 'dialog' if is_dialog_text_pointer(fg_ptr) else '-'
    key = (area if area else '-', bool(in_gameplay), ptr_area, None if a846 is None else bool(a846 >> 8), popup, None if frame is None else bool(frame), bool(overlay_gameplay))
    if getattr(w, '_text_window_probe_key', None) == key:
        return
    w._text_window_probe_key = key
    _recog(_log, 'text window signals: area=%s gameplay=%s ptr=%s ptr_area=%s a846=%s popup=%s frame=%s overlay=%s', key[0], key[1], '0x%04X' % fg_ptr if fg_ptr is not None else 'n/a', key[2], '0x%04X' % a846 if a846 is not None else 'n/a', popup if popup is not None else 'n/a', '0x%02X' % frame if frame is not None else 'n/a', key[6])

def reset_text_window_probe(w) -> None:
    w._text_window_probe_key = None
__all__ = ['note_text_window_signals', 'reset_text_window_probe']
