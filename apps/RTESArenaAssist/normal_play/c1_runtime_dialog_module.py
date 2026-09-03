from __future__ import annotations
import logging
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')
C1_RUNTIME_DIALOG_OWNER = 'c1_runtime_dialog'
_C1_RUNTIME_DIALOG_REPLACEABLE_OWNERS = frozenset({'', C1_RUNTIME_DIALOG_OWNER, 'gold_drop', 'trigger', 'red_text', 'red_text_dialog'})

def _read_foreground_ptr(w) -> int | None:
    try:
        _fg_raw = w._analyzer.read_bytes(w._anchor + 43076, 2)
    except (OSError, AttributeError):
        return None
    if len(_fg_raw) < 2:
        return None
    return _fg_raw[0] | _fg_raw[1] << 8
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
    if _ptr_targets_other_c1_surface(fg_ptr):
        return ''
    if _ptr_targets_msg_buf(fg_ptr):
        return msg_buf or ''
    if dlgflg_active and fg_ptr is not None and (fg_ptr >= 256) and (not _ptr_targets_runtime_dialog(fg_ptr)) and (not bool(getattr(w, '_level_up_active', False))) and (not bool(getattr(w, '_b32_newpop_open', False))):
        return _read_static_dialog_text(w, fg_ptr)
    if _ptr_in(fg_ptr, _NPC_DIALOG_RANGE):
        return npc_dialog or ''
    return ''

def poll_c1_runtime_dialog(w, *, npc_dialog: str, facility_active_now: bool, msg_buf: str='') -> bool:
    _c1_axis = None
    try:
        from normal_play.c1_dialog_axis import read_c1_dialog_axis
        _c1_axis = read_c1_dialog_axis(w, c_area='dungeon', in_gameplay=True, update_prev=False)
    except Exception:
        pass
    if _c1_axis is not None:
        _fg_ptr = getattr(_c1_axis, 'current_ptr', None)
        _dlgflg_active = getattr(_c1_axis, 'a84d', 0) == _DLGFLG_A84D_VALUE
    else:
        _fg_ptr = _read_foreground_ptr(w)
        _dlgflg_active = False
    _body = _resolve_runtime_dialog_body(w, npc_dialog=npc_dialog, msg_buf=msg_buf, fg_ptr=_fg_ptr, dlgflg_active=_dlgflg_active)
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
    if bool(getattr(w, '_npc_conversation_active', False)):
        _block_reasons.append('npc-conversation-active')
    if facility_active_now:
        _block_reasons.append('facility-active')
    if _owner_now not in _C1_RUNTIME_DIALOG_REPLACEABLE_OWNERS:
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
    _open_c1_runtime_dialog_display(w)
    _recog(_log, 'c1 runtime dialog accepted: %r → %r', _body[:64], _npc_ja[:64])
    return True

def _open_c1_runtime_dialog_display(w) -> None:
    w._c1_runtime_dialog_open = True
    w._c1_runtime_dialog_frame_seen = False
    w._c1_runtime_dialog_frame_absent = 0
    w._c1_runtime_dialog_frame_unseen_polls = 0

def _close_c1_runtime_dialog_display(w) -> None:
    w._c1_runtime_dialog_open = False
    w._c1_runtime_dialog_frame_seen = False
    w._c1_runtime_dialog_frame_absent = 0
    w._c1_runtime_dialog_frame_unseen_polls = 0

def release_c1_runtime_dialog(w) -> None:
    _close_c1_runtime_dialog_display(w)
    w._c1_runtime_dialog_body_prev = None

def poll_c1_runtime_dialog_lifetime(w) -> None:
    if not getattr(w, '_c1_runtime_dialog_open', False):
        return
    from screen_detector import is_popup_frame_drawn, POPUP_FRAME_ABSENT_POLLS_TO_END
    from normal_play.trigger_module import restore_last_trigger_display
    try:
        owner = w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        return
    try:
        drawn = is_popup_frame_drawn(w._analyzer, w._anchor)
    except (OSError, AttributeError, RuntimeError):
        drawn = None
    if drawn:
        w._c1_runtime_dialog_frame_seen = True
        w._c1_runtime_dialog_frame_absent = 0
    elif drawn is False and getattr(w, '_c1_runtime_dialog_frame_seen', False):
        w._c1_runtime_dialog_frame_absent = int(getattr(w, '_c1_runtime_dialog_frame_absent', 0)) + 1
    elif drawn is False:
        unseen = int(getattr(w, '_c1_runtime_dialog_frame_unseen_polls', 0)) + 1
        w._c1_runtime_dialog_frame_unseen_polls = unseen
        if unseen == POPUP_FRAME_ABSENT_POLLS_TO_END:
            _recog(_log, 'c1 runtime dialog: popup frame not observed since open (display end deferred to replacement)')
    game_end = bool(getattr(w, '_c1_runtime_dialog_frame_seen', False)) and int(getattr(w, '_c1_runtime_dialog_frame_absent', 0)) >= POPUP_FRAME_ABSENT_POLLS_TO_END
    if owner not in ('', C1_RUNTIME_DIALOG_OWNER):
        return
    if not game_end:
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
__all__ = ['C1_RUNTIME_DIALOG_OWNER', 'poll_c1_runtime_dialog', 'poll_c1_runtime_dialog_lifetime', 'release_c1_runtime_dialog']
