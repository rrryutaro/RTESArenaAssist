from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
_FG_PTR_OFFSET = 43076
_DIALOG_BUF_OFFSET = 38434
_DIALOG_BUF_READ = 4096
_CHOICE_OVERLAY_PTR = 33384
_OWNER = 'palace_dialog'
_KEY_ATTR = '_palace_dialog_prev_key'
_UNIT_ATTR = '_palace_dialog_accepted_unit'
_RESOLVE_CACHE_ATTR = '_palace_dialog_resolve_cache'
_POINTER_UNSET = object()
_TEXT_BYTES = frozenset(bytes(range(32, 127)) + b'\n\r\t')

def is_palace_interior_mif(interior_mif_name: str | None) -> bool:
    u = (interior_mif_name or '').upper()
    return u.startswith(('PALACE', 'TOWNPAL', 'VILPAL'))

def _is_text_bytes(seg: bytes) -> bool:
    return bool(seg) and all((b in _TEXT_BYTES for b in seg))

def _dialog_body_source(ptr: int | None) -> tuple[int, int, bool] | None:
    if ptr is None:
        return None
    try:
        from active_template_reader import message_buffer_remaining
    except ImportError:
        return None
    remaining = message_buffer_remaining(ptr)
    if remaining is not None:
        return (ptr, remaining, False)
    if ptr == _DIALOG_BUF_OFFSET:
        return (_DIALOG_BUF_OFFSET, _DIALOG_BUF_READ, False)
    if ptr == _CHOICE_OVERLAY_PTR:
        return (_DIALOG_BUF_OFFSET, _DIALOG_BUF_READ, True)
    return None

def _dialog_hold_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    if _dialog_body_source(ptr) is not None:
        return False
    return _DIALOG_BUF_OFFSET <= ptr < _DIALOG_BUF_OFFSET + _DIALOG_BUF_READ

def _read_dialog_pointer(w) -> int | None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + _FG_PTR_OFFSET, 2)
        return raw[0] | raw[1] << 8
    except (OSError, AttributeError, IndexError):
        return None

def _dialog_chunks(raw: bytes) -> list[str]:
    chunks: list[str] = []
    segments = raw.split(b'\x00')
    final_is_terminated = raw.endswith(b'\x00')
    for index, seg in enumerate(segments):
        if index == len(segments) - 1 and (not final_is_terminated):
            if chunks:
                break
            return []
        if not seg or not _is_text_bytes(seg):
            if chunks:
                break
            return []
        text = ' '.join(seg.decode('ascii').split())
        if not text:
            if chunks:
                break
            return []
        chunks.append(text)
    return chunks

def assemble_dialog_text(raw: bytes) -> str:
    return ' '.join(_dialog_chunks(raw))

def _read_dialog_chunks(w, off: int, size: int) -> list[str]:
    try:
        raw = w._analyzer.read_bytes(w._anchor + off, size)
        if len(raw) != size:
            return []
    except (OSError, AttributeError, TypeError):
        return []
    return _dialog_chunks(raw)

def _is_building_entry_chunks(chunks: list[str]) -> bool:
    try:
        import template_dat_building_lookup as _tbl
        return any((_tbl.is_building_entry_message(' '.join(chunks[:end])) for end in range(1, len(chunks) + 1)))
    except (ImportError, AttributeError):
        return False

def _resolve_dialog(w, source: tuple[int, int, bool]) -> tuple[str, str] | None:
    chunks = _read_dialog_chunks(w, source[0], source[1])
    if not chunks:
        return None
    cache_key = (source, tuple(chunks))
    cached = getattr(w, _RESOLVE_CACHE_ATTR, None)
    if cached is not None and cached[0] == cache_key:
        return cached[1]
    if _is_building_entry_chunks(chunks):
        setattr(w, _RESOLVE_CACHE_ATTR, (cache_key, None))
        return None
    en, ja = (chunks[0], '')
    try:
        import npc_dialog_lookup as _ndl
        found = _ndl.lookup_span_at_chunk_boundaries(chunks)
        boundaries = {' '.join(chunks[:i]) for i in range(1, len(chunks) + 1)}
        if found is not None and found[2] in boundaries:
            ja_text = _ndl.format_japanese(found[0], found[1])
            if ja_text and '%' not in ja_text:
                en, ja = (found[2], ja_text)
    except (ImportError, AttributeError):
        pass
    resolved = (en, ja) if en else None
    setattr(w, _RESOLVE_CACHE_ATTR, (cache_key, resolved))
    return resolved

def _close_palace_unit(w) -> None:
    shown = getattr(w, _KEY_ATTR, None) is not None
    if shown:
        try:
            w._ui_router.notify_display_unit_closed(_OWNER)
        except AttributeError:
            pass
    if w._ui_router.is_owner(_OWNER):
        w._ui_router.clear_if_owner(_OWNER, notify_close=False)
    setattr(w, _KEY_ATTR, None)
    setattr(w, _UNIT_ATTR, None)
    w._palace_dialog_last_off = None

def _read_dialog_occurrence(w) -> int | None:
    try:
        from active_template_reader import read_display_occurrence
        return read_display_occurrence(w._analyzer, w._anchor)
    except Exception:
        return None

def _dialog_display_unit(w, occurrence: int, source: tuple[int, int, bool], resolved: tuple[str, str]) -> str:
    unit = getattr(w, _UNIT_ATTR, None)
    if unit is None:
        return 'new'
    body_changed = unit[3] != resolved[0]
    if unit[0] != occurrence:
        if body_changed:
            return 'new'
        return 'page' if (unit[1], unit[2]) != (source[0], source[2]) else 'same'
    if body_changed:
        return 'hold'
    if (unit[1], unit[2]) != (source[0], source[2]):
        return 'page'
    return 'same'

def poll_palace_dialog(w, *, palace_active: bool, foreground_ptr=_POINTER_UNSET) -> bool:
    if not palace_active:
        _close_palace_unit(w)
        return False
    ptr = _read_dialog_pointer(w) if foreground_ptr is _POINTER_UNSET else foreground_ptr
    source = _dialog_body_source(ptr)
    if source is None:
        if _dialog_hold_pointer(ptr) and getattr(w, _UNIT_ATTR, None) is not None:
            return True
        _close_palace_unit(w)
        return False
    resolved = _resolve_dialog(w, source)
    occurrence = _read_dialog_occurrence(w)
    if resolved is None or occurrence is None:
        return True
    kind = _dialog_display_unit(w, occurrence, source, resolved)
    if kind == 'hold':
        return True
    if kind == 'same' and w._ui_router.is_owner(_OWNER):
        return True
    en, base_ja = resolved
    if kind == 'new' and getattr(w, _KEY_ATTR, None) is not None:
        try:
            w._ui_router.notify_display_unit_replaced(_OWNER)
        except AttributeError:
            pass
    yesno = source[2]
    display_ja = base_ja
    if yesno and base_ja:
        display_ja = f'{base_ja}\n\n  はい\n  いいえ'
    key = (en, display_ja, yesno)
    key_changed = getattr(w, _KEY_ATTR, None) != key
    if key_changed or not w._ui_router.is_owner(_OWNER):
        setattr(w, _KEY_ATTR, key)
        w._palace_dialog_last_off = source[0]
        w._ui_router.update_translation(_OWNER, en, display_ja, speech_role='conversation' if base_ja else None, speech_text=base_ja if base_ja else None)
        if key_changed:
            _log.info('palace dialog displayed (len=%d translated=%s yesno=%s)', len(en), bool(base_ja), yesno)
    unit = getattr(w, _UNIT_ATTR, None)
    accepted = occurrence if kind == 'new' or unit is None else unit[0]
    setattr(w, _UNIT_ATTR, (accepted, source[0], source[2], en))
    return True
__all__ = ['poll_palace_dialog', 'is_palace_interior_mif', 'assemble_dialog_text']
