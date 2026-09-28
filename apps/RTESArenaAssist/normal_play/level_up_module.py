from __future__ import annotations
import logging
from assist_log import recog
from controllers.screen_finalize import _HOLD_OVERRIDE_PAGES as _CHARACTER_PAGES
_log = logging.getLogger('RTESArenaAssist')
LEVEL_UP_MESSAGE_EN = 'You have gained a level of experience!'
_BONUS_ARTIFACT_TEMPLATE_KEYS = frozenset({506})

def is_bonus_artifact_text(text: str | None) -> bool:
    if not text:
        return False
    try:
        import npc_dialog_lookup as _ndl
        return _ndl.template_key_of_exact(text) in _BONUS_ARTIFACT_TEMPLATE_KEYS
    except Exception:
        return False

def _clear_bonus_artifact_state(w) -> None:
    w._bonus_window_expected = False
    w._bonus_window_saw = False
    w._bonus_window_opened = False
    w._bonus_window_start_coord = None

def _player_coord(w) -> tuple | None:
    coord = getattr(w, '_coord_gate_coord_prev', None)
    if not coord or len(coord) < 2 or coord[0] is None or (coord[1] is None):
        return None
    return (coord[0], coord[1])

def _player_moved_while_waiting(w) -> bool:
    now = _player_coord(w)
    if now is None:
        return False
    start = getattr(w, '_bonus_window_start_coord', None)
    if start is None:
        w._bonus_window_start_coord = now
        return False
    return now != start

def _note_bonus_artifact(w) -> None:
    from normal_play.c1_runtime_dialog_module import accepted_dialog_body, runtime_dialog_accept_seq
    seq = runtime_dialog_accept_seq(w)
    if seq == getattr(w, '_bonus_artifact_seq_seen', 0):
        return
    w._bonus_artifact_seq_seen = seq
    if is_bonus_artifact_text(accepted_dialog_body(w)):
        _clear_bonus_artifact_state(w)
        w._bonus_window_expected = True
        w._bonus_window_start_coord = _player_coord(w)
        recog(_log, 'artifact bonus window: expected (dialog accepted)')
    elif getattr(w, '_bonus_window_expected', False) and (not getattr(w, '_bonus_window_saw', False)):
        _clear_bonus_artifact_state(w)
        recog(_log, 'artifact bonus window: cancelled (another dialog)')

def is_level_up_message(text: str | None) -> bool:
    if not text:
        return False
    return ' '.join(text.split()) == LEVEL_UP_MESSAGE_EN

def _level_up_message_translation() -> str:
    try:
        import npc_dialog_lookup as _ndl
        _found = _ndl.lookup_exact(LEVEL_UP_MESSAGE_EN)
        if _found is not None:
            return _ndl.format_japanese(_found[0], _found[1])
    except Exception as exc:
        _log.debug('level-up message lookup failed: %s', exc)
    return LEVEL_UP_MESSAGE_EN

def reset_level_up_on_load(w) -> None:
    try:
        import player_reader as _pr
        _cur_level = _pr.read_all(w._analyzer, w._anchor)['level']
    except Exception:
        _cur_level = None
    if w._level_up_active or getattr(w, '_panel_owner', '') == 'level_up':
        _log.info('LEVEL UP: load detected → state cleared (prev_level=%s, cur_level=%s)', getattr(w, '_player_level_prev', None), _cur_level)
    del _cur_level
    w._level_up_active = False
    w._level_up_from = None
    w._level_up_to = None
    w._player_bonus_prev = None
    w._level_up_saw_bonus = False
    w._level_up_waiting_for_bonus = False
    w._level_up_pushed_key = None
    _clear_bonus_artifact_state(w)
    try:
        if getattr(w, '_ui_router', None) is not None and w._ui_router.is_owner('level_up'):
            w._ui_router.clear_if_owner('level_up')
    except (AttributeError, RuntimeError):
        pass
    w._player_level_prev = None
    w._player_level_read_prev = None

def suspend_level_up_state(w) -> None:
    w._player_level_prev = None
    w._player_level_read_prev = None
    _clear_bonus_artifact_state(w)
    if getattr(w, '_level_up_active', False):
        w._level_up_active = False
        w._level_up_saw_bonus = False
        w._level_up_waiting_for_bonus = False
        w._level_up_pushed_key = None
        try:
            if getattr(w, '_ui_router', None) is not None and w._ui_router.is_owner('level_up'):
                w._ui_router.clear_if_owner('level_up')
        except (AttributeError, RuntimeError):
            pass

def produce_level_up_state(w, *, loading_active: bool=False, loading_post_settle: bool=False) -> bool:
    try:
        import player_reader as _pr
        _player = _pr.read_all(w._analyzer, w._anchor)
        _raw_level = _player['level']
        _cur_exp = _player['experience']
        _read_prev = getattr(w, '_player_level_read_prev', None)
        w._player_level_read_prev = _raw_level
        _confirmed_level = _raw_level if _raw_level is not None and _raw_level == _read_prev else None
        if loading_active or loading_post_settle:
            if _confirmed_level is not None:
                w._player_level_prev = _confirmed_level
            return False
        _note_bonus_artifact(w)
        if w._player_level_prev is None and _confirmed_level is not None:
            w._player_level_prev = _confirmed_level
        if _confirmed_level is not None and w._player_level_prev is not None and (_confirmed_level > w._player_level_prev):
            _log.info('LEVEL UP detected: %d → %d (Exp=%s)', w._player_level_prev, _confirmed_level, _cur_exp)
            w._level_up_from = w._player_level_prev
            w._level_up_to = _confirmed_level
            w._level_up_active = True
            w._level_up_waiting_for_bonus = True
        if _confirmed_level is not None:
            w._player_level_prev = _confirmed_level
        return True
    except (ImportError, AttributeError, OSError):
        return False

def consume_level_up_display(w, *, screen_id_stable: str | None, b30_dialog_active: bool, b30_dialog_active_prev: bool) -> None:
    try:
        _is_bonus_screen = screen_id_stable == 'bonus_screen'
        _is_dialog_only = b30_dialog_active and (not _is_bonus_screen)
        if getattr(w, '_bonus_window_expected', False):
            if _is_bonus_screen:
                if not getattr(w, '_bonus_window_saw', False):
                    recog(_log, 'artifact bonus window: held')
                w._bonus_window_saw = True
            elif getattr(w, '_bonus_window_saw', False):
                recog(_log, 'artifact bonus window: complete')
                _clear_bonus_artifact_state(w)
            elif screen_id_stable in _CHARACTER_PAGES:
                w._bonus_window_opened = True
            elif getattr(w, '_bonus_window_opened', False):
                recog(_log, 'artifact bonus window: cancelled (closed without the bonus window)')
                _clear_bonus_artifact_state(w)
            elif _player_moved_while_waiting(w):
                recog(_log, 'artifact bonus window: cancelled (the player moved without the bonus window)')
                _clear_bonus_artifact_state(w)
        if w._level_up_active:
            if _is_dialog_only:
                _push_key = (w._level_up_from, w._level_up_to)
                if getattr(w, '_level_up_pushed_key', None) != _push_key:
                    w._level_up_pushed_key = _push_key
                    import i18n_helper as _i18n
                    _translated = _level_up_message_translation()
                    _levels = '%s %s → %s' % (_i18n.tr('status.stat.level'), w._level_up_from, w._level_up_to)
                    w._ui_router.update_translation('level_up', LEVEL_UP_MESSAGE_EN, f'{_translated}\n({_levels})', panel_en=LEVEL_UP_MESSAGE_EN, panel_ja=_translated, speech_role='situation', speech_text=_translated)
            if _is_bonus_screen:
                import player_reader as _pr
                _cur_bonus = _pr.read_all(w._analyzer, w._anchor)['bonus_pts']
                if _cur_bonus is not None and 0 <= _cur_bonus <= 30:
                    w._player_bonus_prev = _cur_bonus
                    w._level_up_saw_bonus = True
                    w._level_up_waiting_for_bonus = False
            _saw_bonus = getattr(w, '_level_up_saw_bonus', False)
            _waiting_bonus = getattr(w, '_level_up_waiting_for_bonus', False)
            _bonus_closed = _saw_bonus and (not _is_bonus_screen)
            _dialog_closed = b30_dialog_active_prev and (not b30_dialog_active)
            if _dialog_closed and (not _is_bonus_screen):
                w._ui_router.clear_if_owner('level_up')
            if _bonus_closed or (not _saw_bonus and (not _waiting_bonus) and _dialog_closed):
                _log.info('LEVEL UP: complete (saw_bonus=%s)', _saw_bonus)
                w._level_up_active = False
                w._player_bonus_prev = None
                w._level_up_saw_bonus = False
                w._level_up_waiting_for_bonus = False
                w._level_up_pushed_key = None
                w._ui_router.clear_if_owner('level_up')
    except (ImportError, AttributeError, OSError):
        pass

def poll_level_up(w, *, b30_dialog_active: bool, b30_dialog_active_prev: bool, loading_active: bool=False, loading_post_settle: bool=False) -> None:
    _continue = produce_level_up_state(w, loading_active=loading_active, loading_post_settle=loading_post_settle)
    if not _continue:
        return
    consume_level_up_display(w, screen_id_stable=getattr(w, '_screen_id_prev', None), b30_dialog_active=b30_dialog_active, b30_dialog_active_prev=b30_dialog_active_prev)

def level_up_active(w) -> bool:
    return bool(getattr(w, '_level_up_active', False))

def bonus_window_pending(w) -> bool:
    return level_up_active(w) or bool(getattr(w, '_bonus_window_expected', False))

def bonus_window_points_max(w) -> int:
    from controllers.screen_finalize import ARTIFACT_BONUS_PTS_MAX, BONUS_PTS_MAX
    if getattr(w, '_bonus_window_expected', False):
        return max(ARTIFACT_BONUS_PTS_MAX, BONUS_PTS_MAX)
    return BONUS_PTS_MAX
__all__ = ['poll_level_up', 'produce_level_up_state', 'suspend_level_up_state', 'consume_level_up_display', 'level_up_active', 'bonus_window_pending', 'bonus_window_points_max', 'is_level_up_message', 'is_bonus_artifact_text', 'LEVEL_UP_MESSAGE_EN']
