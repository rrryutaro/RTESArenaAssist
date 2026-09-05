from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
STATUS_OWNER = 'status'

def poll_status_popup(w, *, entry_handled: bool) -> None:
    try:
        from template_parser import parse_filled, render_status, status_popup_foreground
        _status_fg = status_popup_foreground(w._analyzer, w._anchor)
        _status_fg_was = getattr(w, '_b21_status_fg_was', False)
        try:
            _flag_popup = w._analyzer.read_bytes(w._anchor + 31012, 1)[0]
        except (OSError, AttributeError):
            _flag_popup = 0
        _popup_active = _flag_popup == 1
        _popup_was = getattr(w, '_b21_popup_was_open', False)
        if _status_fg_was and (not _status_fg) or (_popup_was and (not _popup_active)):
            w._ui_router.clear_if_owner(STATUS_OWNER)
            w._last_status_vkey = None
        w._b21_popup_was_open = _popup_active
        w._b21_status_fg_was = _status_fg
        _parsed = parse_filled(w._analyzer, w._anchor)
        if _parsed is not None:
            _vkey = (_parsed.get('location', ''), _parsed.get('time', ''), _parsed.get('date', ''), _parsed.get('weight', ''), _parsed.get('weight_max', ''), _parsed.get('states', ()))
            _full_en, _full_ja, _ = render_status(_parsed)
            if _status_fg and (not entry_handled) and (_vkey != getattr(w, '_last_status_vkey', None)):
                w._last_status_vkey = _vkey
                w._ui_router.update_translation(STATUS_OWNER, _full_en, _full_ja)
    except (ImportError, AttributeError, OSError):
        pass
__all__ = ['STATUS_OWNER', 'poll_status_popup']
