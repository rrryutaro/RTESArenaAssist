from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
C1_RUNTIME_DIALOG_OWNER = 'c1_runtime_dialog'

def _read_dialog_just_opened(w) -> tuple[bool, bool]:
    try:
        _dialog_byte = w._analyzer.read_bytes(w._anchor + 43077, 1)[0]
    except (OSError, AttributeError):
        _dialog_byte = 0
    _dialog_active_now = _dialog_byte != 0
    _dialog_active_prev = getattr(w, '_b30_dialog_active_prev', False)
    return (_dialog_active_now and (not _dialog_active_prev), _dialog_active_now)

def _read_foreground_ptr(w) -> int | None:
    try:
        _fg_raw = w._analyzer.read_bytes(w._anchor + 43076, 2)
    except (OSError, AttributeError):
        return None
    if len(_fg_raw) < 2:
        return None
    return _fg_raw[0] | _fg_raw[1] << 8
_MSG_BUF_RANGE = (39582, 512)

def _ptr_targets_runtime_dialog(ptr: int | None) -> bool:
    if ptr is None:
        return False
    return any((start <= ptr < start + length for start, length in ((4164, 512), _MSG_BUF_RANGE)))

def _ptr_targets_msg_buf(ptr: int | None) -> bool:
    if ptr is None:
        return False
    _start, _length = _MSG_BUF_RANGE
    return _start <= ptr < _start + _length
_OTHER_C1_SURFACE_RANGES = ((31097, 68), (37534, 512))
_DLGFLG_A84D_VALUE = 64
_STATIC_TEXT_READ_LEN = 256

def _ptr_targets_other_c1_surface(ptr: int | None) -> bool:
    if ptr is None:
        return False
    return any((start <= ptr < start + length for start, length in _OTHER_C1_SURFACE_RANGES))

def _read_static_dialog_text(w, ptr: int) -> str:
    try:
        from arena_logic import read_live_buffer
        return read_live_buffer(w._analyzer, w._anchor + ptr, _STATIC_TEXT_READ_LEN)
    except Exception:
        return ''

def _resolve_runtime_dialog_body(w, *, npc_dialog: str, msg_buf: str, fg_ptr: int | None, dlgflg_active: bool) -> str:
    if _ptr_targets_msg_buf(fg_ptr) and msg_buf:
        return msg_buf
    if dlgflg_active and fg_ptr is not None and (fg_ptr >= 256) and (not _ptr_targets_runtime_dialog(fg_ptr)) and (not _ptr_targets_other_c1_surface(fg_ptr)) and (not bool(getattr(w, '_level_up_active', False))) and (not bool(getattr(w, '_b32_newpop_open', False))):
        _static = _read_static_dialog_text(w, fg_ptr)
        if _static:
            return _static
    return npc_dialog

def _axis_targets_runtime_dialog(axis) -> bool:
    if not axis or not getattr(axis, 'active', False):
        return False
    return getattr(axis, 'a845', 0) == 16 or getattr(axis, 'a84d', 0) == 64 or _ptr_targets_runtime_dialog(getattr(axis, 'current_ptr', None))

def poll_c1_runtime_dialog(w, *, npc_dialog: str, npc_dialog_changed: bool, facility_active_now: bool, msg_buf: str='') -> bool:
    if bool(getattr(w, '_npc_conversation_active', False)) or facility_active_now:
        return False
    _c1_axis = None
    _c1_runtime_axis_active = False
    _c1_runtime_axis_opened = False
    try:
        from normal_play.c1_dialog_axis import read_c1_dialog_axis
        _c1_axis = read_c1_dialog_axis(w, c_area='dungeon', in_gameplay=True, update_prev=False)
        _c1_runtime_axis_active = _axis_targets_runtime_dialog(_c1_axis)
        _c1_runtime_axis_opened = bool(_c1_runtime_axis_active and getattr(_c1_axis, 'opened', False))
    except Exception:
        pass
    if _c1_axis is not None:
        _fg_ptr = getattr(_c1_axis, 'current_ptr', None)
        _dlgflg_active = getattr(_c1_axis, 'a84d', 0) == _DLGFLG_A84D_VALUE
    else:
        _fg_ptr = _read_foreground_ptr(w)
        _dlgflg_active = False
    _body = _resolve_runtime_dialog_body(w, npc_dialog=npc_dialog, msg_buf=msg_buf, fg_ptr=_fg_ptr, dlgflg_active=_dlgflg_active)
    if not _body:
        return False
    _dialog_just_opened, _dialog_active_now = _read_dialog_just_opened(w)
    _runtime_dialog_text_on_screen = _dialog_active_now and _ptr_targets_runtime_dialog(_fg_ptr)
    _runtime_dialog_just_opened = _dialog_just_opened and _c1_runtime_axis_active
    if not (npc_dialog_changed or _runtime_dialog_just_opened or _runtime_dialog_text_on_screen or _c1_runtime_axis_active):
        return False
    try:
        import dungeon_msg_lookup as _dml
    except ImportError:
        return False
    _npc_ja = _dml.lookup(_body)
    if not _npc_ja:
        try:
            import npc_dialog_lookup as _ndl
            _ndl_result = _ndl.lookup(_body)
            if _ndl_result is not None:
                _npc_ja = _ndl.format_japanese(_ndl_result[0], _ndl_result[1])
        except Exception as exc:
            _log.debug('npc_dialog fallback failed: %s', exc)
    if not _npc_ja:
        return False
    _keep = (_body, _npc_ja)
    if npc_dialog_changed or _runtime_dialog_just_opened or _c1_runtime_axis_opened or (not (getattr(w, '_c1_runtime_dialog_keep_key', None) == _keep and w._ui_router.is_owner(C1_RUNTIME_DIALOG_OWNER))):
        w._c1_runtime_dialog_keep_key = _keep
        w._ui_router.update_translation(C1_RUNTIME_DIALOG_OWNER, _body, _npc_ja, speech_role='situation')
        _log.info('panel_owner -> %s (route=c1_dungeon_msg, text=%r c1_axis=%s)', C1_RUNTIME_DIALOG_OWNER, _body, _c1_runtime_axis_active)
    return True
__all__ = ['C1_RUNTIME_DIALOG_OWNER', 'poll_c1_runtime_dialog']
