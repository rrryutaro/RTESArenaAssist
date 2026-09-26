from __future__ import annotations
import logging
from assist_log import recog as _recog
from normal_play.c1_dialog_axis import close_confirmed as _close_confirmed
_log = logging.getLogger('RTESArenaAssist')
C1_RUNTIME_DIALOG_OWNER = 'c1_runtime_dialog'
_C1_RUNTIME_DIALOG_REPLACEABLE_OWNERS = frozenset({'', C1_RUNTIME_DIALOG_OWNER, 'gold_drop', 'trigger', 'red_text', 'red_text_dialog'})
_SCENE_TEXT_REPLACEABLE_OWNERS = frozenset({'vision_cinematic'})

def _replaceable_owners(w) -> frozenset:
    from normal_play.cinematic_module import scene_text_is_replaceable
    if scene_text_is_replaceable(w):
        return _C1_RUNTIME_DIALOG_REPLACEABLE_OWNERS | _SCENE_TEXT_REPLACEABLE_OWNERS
    return _C1_RUNTIME_DIALOG_REPLACEABLE_OWNERS
_NPC_DIALOG_RANGE = (4164, 512)
_MSG_BUF_RANGE = (39582, 512)

def _ptr_in(ptr: int | None, span: tuple[int, int]) -> bool:
    if ptr is None:
        return False
    start, length = span
    return start <= ptr < start + length

def _ptr_targets_runtime_dialog(ptr: int | None) -> bool:
    return _ptr_in(ptr, _NPC_DIALOG_RANGE) or _ptr_in(ptr, _MSG_BUF_RANGE)

def _ptr_targets_msg_buf(ptr: int | None) -> bool:
    return _ptr_in(ptr, _MSG_BUF_RANGE)
_OTHER_C1_SURFACE_RANGES = ((31097, 68), (37534, 512))
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
    if _ptr_targets_other_c1_surface(fg_ptr):
        return ''
    if _ptr_targets_msg_buf(fg_ptr):
        return msg_buf or ''
    if dlgflg_active and fg_ptr is not None and (fg_ptr >= 256) and (not _ptr_targets_runtime_dialog(fg_ptr)):
        from normal_play.level_up_module import level_up_active
        from normal_play.item_pickup_module import pickup_list_open
        if not level_up_active(w) and (not pickup_list_open(w)):
            return _read_static_dialog_text(w, fg_ptr)
        return ''
    if _ptr_in(fg_ptr, _NPC_DIALOG_RANGE):
        return npc_dialog or ''
    return ''

def poll_c1_runtime_dialog(w, *, npc_dialog: str, facility_active_now: bool, msg_buf: str='', axis=None) -> bool:
    if axis is None:
        return False
    _body = _resolve_runtime_dialog_body(w, npc_dialog=npc_dialog, msg_buf=msg_buf, fg_ptr=axis.current_ptr, dlgflg_active=axis.dlgflg)
    from normal_play.level_up_module import is_level_up_message
    if is_level_up_message(_body):
        _body = ''
    _prev = getattr(w, '_c1_runtime_dialog_body_prev', None)
    w._c1_runtime_dialog_body_prev = _body
    _changed = _prev is not None and _body != _prev
    if not (_changed and _body):
        return False
    try:
        _owner_now = w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        _owner_now = getattr(w, '_panel_owner', '') or ''
    _block_reasons = []
    if facility_active_now:
        _block_reasons.append('facility-active')
    if _owner_now not in _replaceable_owners(w):
        _block_reasons.append('panel-owner=%s' % (_owner_now or '-'))
    if _block_reasons:
        _recog(_log, 'c1 runtime dialog skipped (%s): %r', ','.join(_block_reasons), _body[:64])
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
    w._ui_router.update_translation(C1_RUNTIME_DIALOG_OWNER, _body, _npc_ja, speech_role='situation')
    _open_c1_runtime_dialog_display(w, area=axis.area)
    _recog(_log, 'c1 runtime dialog accepted (ptr=%s area=%s): %r → %r', '0x%04X' % axis.current_ptr if axis.current_ptr is not None else 'n/a', axis.area or '-', _body[:64], _npc_ja[:64])
    return True

def _open_c1_runtime_dialog_display(w, *, area: str='') -> None:
    w._c1_runtime_dialog_open = True
    w._c1_runtime_dialog_accept_seq = int(getattr(w, '_c1_runtime_dialog_accept_seq', 0)) + 1
    w._c1_runtime_dialog_area = area
    w._c1_runtime_dialog_closed = False
    w._c1_runtime_dialog_left_noted = False

def _close_c1_runtime_dialog_display(w) -> None:
    w._c1_runtime_dialog_open = False
    w._c1_runtime_dialog_area = ''
    w._c1_runtime_dialog_closed = False
    w._c1_runtime_dialog_left_noted = False

def runtime_dialog_accept_seq(w) -> int:
    return int(getattr(w, '_c1_runtime_dialog_accept_seq', 0))

def release_c1_runtime_dialog(w) -> None:
    _close_c1_runtime_dialog_display(w)
    w._c1_runtime_dialog_body_prev = None

def pause_c1_runtime_dialog(w) -> None:
    w._c1_runtime_dialog_body_prev = None

def poll_c1_runtime_dialog_lifetime(w, *, axis=None) -> None:
    if not getattr(w, '_c1_runtime_dialog_open', False):
        return
    from normal_play.trigger_module import restore_last_trigger_display
    try:
        owner = w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        return
    area_open = getattr(w, '_c1_runtime_dialog_area', '') or ''
    if axis is not None and axis.area != area_open:
        ptr_text = '0x%04X' % axis.current_ptr if axis.current_ptr is not None else 'n/a'
        if _close_confirmed(area_open):
            if not getattr(w, '_c1_runtime_dialog_closed', False):
                w._c1_runtime_dialog_closed = True
                _recog(_log, 'c1 runtime dialog: closed (pointer left %s, ptr=%s area=%s)', area_open, ptr_text, axis.area or '-')
        elif not getattr(w, '_c1_runtime_dialog_left_noted', False):
            w._c1_runtime_dialog_left_noted = True
            _recog(_log, 'c1 runtime dialog: pointer left %s (ptr=%s area=%s) but the close signal for this kind is not confirmed; display end deferred to replacement', area_open or '-', ptr_text, axis.area or '-')
    if owner not in ('', C1_RUNTIME_DIALOG_OWNER):
        return
    if not getattr(w, '_c1_runtime_dialog_closed', False):
        return
    feed = getattr(w, '_translation_feed', None)
    try:
        speaking_owner = feed.speaking_owner() if feed is not None else None
    except AttributeError:
        speaking_owner = None
    if speaking_owner == C1_RUNTIME_DIALOG_OWNER:
        try:
            if w._tts.is_speaking():
                return
        except AttributeError:
            pass
    _recog(_log, 'c1 runtime dialog display end (表示終了・読み上げ終了)')
    _close_c1_runtime_dialog_display(w)
    if owner == C1_RUNTIME_DIALOG_OWNER:
        w._ui_router.notify_display_unit_closed(C1_RUNTIME_DIALOG_OWNER)
        w._ui_router.clear_if_owner(C1_RUNTIME_DIALOG_OWNER, notify_close=False)
        restore_last_trigger_display(w)
    else:
        w._ui_router.clear_display('', allowed_current_owners=('',))
__all__ = ['C1_RUNTIME_DIALOG_OWNER', 'poll_c1_runtime_dialog', 'poll_c1_runtime_dialog_lifetime', 'runtime_dialog_accept_seq', 'release_c1_runtime_dialog', 'pause_c1_runtime_dialog']
