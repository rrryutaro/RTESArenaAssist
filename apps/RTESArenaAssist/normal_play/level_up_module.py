from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")


def produce_level_up_state(w, *, loading_active: bool = False,
                           load_edge_start: bool = False,
                           loading_post_settle: bool = False) -> bool:
    try:
        import player_reader as _pr
        _player = _pr.read_all(w._analyzer, w._anchor)
        _cur_level = _player["level"]
        _cur_exp   = _player["experience"]

        if load_edge_start:
            if w._level_up_active or getattr(w, "_panel_owner", "") == "level_up":
                _log.info(
                    "LEVEL UP: load edge detected → state cleared "
                    "(prev_level=%s, cur_level=%s)",
                    w._player_level_prev, _cur_level)
            w._level_up_active = False
            w._level_up_from = None
            w._level_up_to = None
            w._player_bonus_prev = None
            w._level_up_saw_bonus = False
            w._level_up_waiting_for_bonus = False
            try:
                if (getattr(w, "_ui_router", None) is not None
                        and w._ui_router.is_owner("level_up")):
                    w._ui_router.clear_if_owner("level_up")
            except (AttributeError, RuntimeError):
                pass
            w._player_level_prev = _cur_level
            return False

        if loading_active or loading_post_settle:
            if _cur_level is not None:
                w._player_level_prev = _cur_level
            return False

        if w._player_level_prev is None and _cur_level is not None:
            w._player_level_prev = _cur_level

        if (_cur_level is not None
                and w._player_level_prev is not None
                and _cur_level > w._player_level_prev):
            _log.info("LEVEL UP detected: %d → %d (Exp=%s)",
                      w._player_level_prev, _cur_level, _cur_exp)
            w._level_up_from   = w._player_level_prev
            w._level_up_to     = _cur_level
            w._level_up_active = True
            w._level_up_waiting_for_bonus = True
        w._player_level_prev = _cur_level
        return True
    except (ImportError, AttributeError, OSError):
        return False


def consume_level_up_display(w, *, screen_id_stable: str | None,
                             b30_dialog_active: bool,
                             b30_dialog_active_prev: bool,
                             b30_red_changed: bool,
                             npc_dialog_changed: bool) -> None:
    try:
        _is_bonus_screen = (screen_id_stable == "bonus_screen")
        _is_dialog_only  = b30_dialog_active and not _is_bonus_screen

        if w._level_up_active:
            if _is_dialog_only:
                _en_panel = "You have gained a level of experience!"
                _ja_panel = "経験値レベルが上がった！"
                _en_tab = "You have gained a level of experience!"
                _ja_tab = (f"レベルアップ! Level {w._level_up_from} → "
                           f"{w._level_up_to} に上がった。")
                w._ui_router.update_translation(
                    "level_up", _en_tab, _ja_tab,
                    panel_en=_en_panel, panel_ja=_ja_panel,
                    speech_role="situation")

            if _is_bonus_screen:
                import player_reader as _pr
                _cur_bonus = _pr.read_all(w._analyzer, w._anchor)["bonus_pts"]
                if _cur_bonus is not None and 0 <= _cur_bonus <= 30:
                    w._player_bonus_prev = _cur_bonus
                    w._level_up_saw_bonus = True
                    w._level_up_waiting_for_bonus = False

            _saw_bonus     = getattr(w, "_level_up_saw_bonus", False)
            _waiting_bonus = getattr(w, "_level_up_waiting_for_bonus", False)
            _bonus_closed  = _saw_bonus and not _is_bonus_screen
            _dialog_closed = (b30_dialog_active_prev and not b30_dialog_active)
            if _bonus_closed or (
                    not _saw_bonus and not _waiting_bonus and _dialog_closed):
                _log.info("LEVEL UP: complete (saw_bonus=%s)", _saw_bonus)
                w._level_up_active   = False
                w._player_bonus_prev = None
                w._level_up_saw_bonus = False
                w._level_up_waiting_for_bonus = False
                _c1_fg = getattr(w, "_c1_dialog_foreground", "")
                if _c1_fg == "" and w._ui_router.is_owner("level_up"):
                    w._ui_router.clear_if_owner("level_up")
    except (ImportError, AttributeError, OSError):
        pass


def poll_level_up(w, *, b30_dialog_active: bool,
                  b30_dialog_active_prev: bool,
                  b30_red_changed: bool,
                  npc_dialog_changed: bool,
                  loading_active: bool = False,
                  load_edge_start: bool = False,
                  loading_post_settle: bool = False) -> None:
    _continue = produce_level_up_state(
        w,
        loading_active=loading_active,
        load_edge_start=load_edge_start,
        loading_post_settle=loading_post_settle,
    )
    if not _continue:
        return
    consume_level_up_display(
        w,
        screen_id_stable=getattr(w, "_screen_id_prev", None),
        b30_dialog_active=b30_dialog_active,
        b30_dialog_active_prev=b30_dialog_active_prev,
        b30_red_changed=b30_red_changed,
        npc_dialog_changed=npc_dialog_changed,
    )


__all__ = [
    "poll_level_up",
    "produce_level_up_state",
    "consume_level_up_display",
]
