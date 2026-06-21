from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

C1_RUNTIME_DIALOG_OWNER = "c1_runtime_dialog"


def _read_dialog_just_opened(w) -> tuple[bool, bool]:
    try:
        _dialog_byte = w._analyzer.read_bytes(w._anchor + 0xA845, 1)[0]
    except (OSError, AttributeError):
        _dialog_byte = 0x00
    _dialog_active_now = (_dialog_byte != 0x00)
    _dialog_active_prev = getattr(w, "_b30_dialog_active_prev", False)
    return _dialog_active_now and not _dialog_active_prev, _dialog_active_now


def _read_response_text_on_screen(w, *, dialog_active_now: bool) -> bool:
    try:
        _fg_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
        _fg_ptr = _fg_raw[0] | (_fg_raw[1] << 8)
    except (OSError, AttributeError):
        return False
    try:
        from active_template_reader import is_response_text_buffer_pointer
        return dialog_active_now and is_response_text_buffer_pointer(_fg_ptr)
    except Exception:  # noqa: BLE001
        return dialog_active_now and any(
            start <= _fg_ptr < start + length
            for start, length in (
                (0x1044, 512),
                (0x929E, 512),
                (0x9A9E, 512),
            ))


def poll_c1_runtime_dialog(w, *, npc_dialog: str,
                           npc_dialog_changed: bool,
                           facility_active_now: bool) -> bool:
    if (not npc_dialog
            or bool(getattr(w, "_npc_conversation_active", False))
            or facility_active_now):
        return False

    _dialog_just_opened, _dialog_active_now = _read_dialog_just_opened(w)
    _response_text_on_screen = _read_response_text_on_screen(
        w, dialog_active_now=_dialog_active_now)

    _c1_axis_active = False
    _c1_axis_opened = False
    try:
        from normal_play.c1_dialog_axis import read_c1_dialog_axis
        _c1_axis = read_c1_dialog_axis(
            w, c_area="dungeon", in_gameplay=True, update_prev=False)
        _c1_axis_active = bool(_c1_axis and _c1_axis.active)
        _c1_axis_opened = bool(_c1_axis and _c1_axis.opened)
    except Exception:  # noqa: BLE001
        pass

    if not (npc_dialog_changed or _dialog_just_opened
            or _response_text_on_screen or _c1_axis_active):
        return False

    try:
        import dungeon_msg_lookup as _dml
    except ImportError:
        return False
    _npc_ja = _dml.lookup(npc_dialog)
    if not _npc_ja:
        return False

    _keep = (npc_dialog, _npc_ja)
    if (npc_dialog_changed or _dialog_just_opened or _c1_axis_opened
            or not (getattr(w, "_c1_runtime_dialog_keep_key", None) == _keep
                    and w._ui_router.is_owner(C1_RUNTIME_DIALOG_OWNER))):
        w._c1_runtime_dialog_keep_key = _keep
        w._ui_router.update_translation(
            C1_RUNTIME_DIALOG_OWNER, npc_dialog, _npc_ja,
            speech_role="situation")
    _log.info(
        "panel_owner -> %s (route=c1_dungeon_msg, text=%r c1_axis=%s)",
        C1_RUNTIME_DIALOG_OWNER, npc_dialog, _c1_axis_active)
    return True


__all__ = ["C1_RUNTIME_DIALOG_OWNER", "poll_c1_runtime_dialog"]
