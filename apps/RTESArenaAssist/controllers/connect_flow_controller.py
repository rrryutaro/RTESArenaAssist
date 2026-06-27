from __future__ import annotations
import logging
import os
import i18n_helper as i18n
import assist_settings as settings
import inf_text_lookup as itl
from controllers.chargen_helpers import _CHARGEN_CLASS_JA
from ui_router import UiRouter
_log = logging.getLogger('assist_window')

def _app_dir() -> str:
    from assist_window import _APP_DIR
    return _APP_DIR

def on_connect_done(win, pid: int, anchor: int):
    win._analyzer = win._worker.analyzer
    win._anchor = anchor
    win._npc_dialog_prev = ''
    win._npc_dialog_text_prev = ''
    win._ask_about_menu_active_prev = False
    win._ask_about_current_ptr_prev = -1
    win._popup11_list_state_prev = ''
    win._popup11_exit_pending_ask_about = False
    win._popup11_ask_recovery = False
    win._popup11_item_dyn_prev = (-1, -1)
    win._popup11_place_response_lock = None
    win._cap159_diag_prev = None
    win._city_npc_active_was_nonzero_prev = False
    win._interior_facility_kind = ''
    itl.load()
    win._conn_btn.setEnabled(True)
    win._conn_btn.setText(i18n.tr('connection.disconnect'))
    if settings.get('show_recognition_screen', True):
        win._status_lbl.setText(i18n.tr('connection.status_connected', screen='—'))
    else:
        win._status_lbl.setText(i18n.tr('connection.status_connected_no_screen'))
    win._anchor_lbl.setText(i18n.tr('connection.img_info', img='—'))
    win._img_name_lbl.setVisible(False)
    win._tab_translate.set_connected(True)
    win._tab_status.set_memory_target(win._analyzer, win._anchor)
    try:
        win._tab_translate.appearance_faces_panel().set_memory_target(win._analyzer, win._anchor)
        win._tab_translate.appearance_faces_panel().set_window(win)
    except AttributeError:
        pass
    if win._layout_translate_panel is not None:
        win._layout_translate_panel.set_connected(True)
    try:
        from arena_bridge import MifTriggerMatcher
        from runtime_paths import resolve_arena_data_dir
        import json as _json

        def _usable_mif_dir(path: str) -> str:
            if not path or not os.path.isdir(path):
                return ''
            try:
                for name in os.listdir(path):
                    if name.upper().endswith('.MIF'):
                        return path
            except OSError:
                return ''
            return ''
        save_dir = settings.get('save_dir', '')
        explicit_mif_dir = settings.get('mif_dir', '')
        mif_dir = _usable_mif_dir(explicit_mif_dir)
        if not mif_dir and save_dir:
            maps_path = os.path.join(save_dir, 'MAPS')
            mif_dir = _usable_mif_dir(maps_path)
            if not mif_dir:
                mif_dir = _usable_mif_dir(save_dir)
        if not mif_dir:
            mif_dir = _usable_mif_dir(os.fspath(resolve_arena_data_dir() / 'MIF'))
        win._mif_matcher = MifTriggerMatcher(mif_dir=mif_dir)
        _log.info('MifTriggerMatcher initialized: mif_dir=%s', mif_dir or '(none)')
    except Exception:
        win._mif_matcher = None
    win._trigger_flag_prev = 0
    win._trigger_indices = []
    win._cached_trig_idx = 0
    win._cached_rt_x = win._cached_rt_z = None
    win._panel_owner: str = ''
    win._ui_router = UiRouter(win)
    _feed = getattr(win, '_translation_feed', None)
    if _feed is not None:
        win._ui_router.set_translation_observer(_feed.on_translation)
        win._ui_router.set_clear_observer(_feed.on_display_cleared)
    win._b32_was_corpse: bool = False
    win._img_name_prev = ''
    win._screen_id_prev: str | None = None
    win._screen_id_pending: str | None = None
    win._screen_id_stable_count: int = 0
    win._menu_active_prev: int = 65535
    win._flag_detail_skip_n: int = 0
    win._spell_detail_text_ready: bool = True
    win._spell_detail_text_marker = None
    win._equipment_marker: bytes | None = None
    win._newgame_layout_pushed = False
    win._startup_layout_pushed = False
    win._chargen_state_prev = 0
    win._chargen_q_seq_prev = 0
    win._in_chargen_name = False
    win._chargen_state_streak = 0
    win._chargen_in_advice = False
    win._chargen_advice_state = None
    win._chargen_goyenow_displayed = False
    win._chargen_goyenow_state = None
    win._chargen_goyenow_b7c4_prev = None
    win._chargen_10q_displayed = False
    win._chargen_method_state = None
    win._chargen_distribute_displayed = False
    win._chargen_choose_attrs_displayed = False
    win._chargen_choose_attrs_state_val = None
    win._chargen_appearance_displayed = False
    win._chargen_done_prev = 0
    win._chargen_opening_displayed = False
    win._chargen_method_window = False
    win._chargen_race_select_displayed = False
    win._chargen_class_accept_displayed = False
    win._chargen_race_desc_displayed = False
    win._chargen_sex_select_displayed = False
    win._chargen_complete_displayed = False
    win._chargen_class_list_active = False
    win._is_in_chargen = False
    win._goyenow_scan_budget = 0
    win._advice_capture_age = -1
    win._chargen_race_ja = None
    win._chargen_class_ja = None
    win._chargen_class_en = None
    win._top_level_state = 'pregame'
    win._chargen_subscreen_last = None
    win._pregame_loadsave_seen = False
    win._set_class_list_panel_mode(False)
    win._set_chargen_ui_state(False)
    try:
        from arena_bridge import CHARGEN_STATE_OFFSET, CHARGEN_Q_SEQ_OFFSET, CHARGEN_DONE_OFFSET, NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN, read_live_buffer
        win._chargen_state_prev = win._analyzer.read_bytes(win._anchor + CHARGEN_STATE_OFFSET, 1)[0]
        win._chargen_q_seq_prev = win._analyzer.read_bytes(win._anchor + CHARGEN_Q_SEQ_OFFSET, 1)[0]
        win._chargen_done_prev = win._analyzer.read_bytes(win._anchor + CHARGEN_DONE_OFFSET, 1)[0]
        npc_init = read_live_buffer(win._analyzer, win._anchor + NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN)
        win._chargen._handle_chargen_npc_dialog(npc_init)
        win._npc_dialog_prev = npc_init
    except (OSError, ImportError):
        pass
    win._sb.showMessage(i18n.tr('status.ready'))
    win._layout_mgr.set_dosbox_pid(pid)
    win._detect_top_level_at_connect()
    if win._top_level_state == 'normal-play':
        try:
            from session.hierarchy_attach import resolve_attach_path
            from normal_play.base_location.base_location_view import area_name
            from arena_bridge import read_game_state, read_interior_flag
            from play_area_classifier import resolve_in_interior, _WILDERNESS_FLAG_OFFSET
            _gs_attach = read_game_state(win._analyzer, win._anchor)
            _mif_attach = _gs_attach.get('LiveMifName') or _gs_attach.get('MifName') or ''
            try:
                _place_attach = win._analyzer.read_bytes(win._anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
            except (OSError, IndexError, AttributeError):
                _place_attach = None
            _in_interior_attach = resolve_in_interior(read_interior_flag(win._analyzer, win._anchor), _place_attach, _mif_attach)
            _attach = resolve_attach_path(win, mif_name=_mif_attach, in_interior=_in_interior_attach)
            _seed_area = area_name(_attach.get('l2', ''))
            if _seed_area:
                win._last_non_interior_area = _seed_area
            _log.info('hierarchy attach: l1=%s l2=%s l3=%s (mif=%r in_interior=%s seed_area=%r)', _attach.get('l1'), _attach.get('l2'), _attach.get('l3'), _mif_attach, _in_interior_attach, _seed_area)
        except Exception:
            _log.exception('hierarchy attach failed')
    if win._top_level_state == 'chargen':
        try:
            attrs = win._analyzer.read_bytes(win._anchor + 461, 8)
            name_raw = win._analyzer.read_bytes(win._anchor + 429, 26)
            name_str = name_raw.split(b'\x00', 1)[0].decode('ascii', errors='ignore').strip()
            is_named = bool(name_str) and all((32 <= b <= 126 for b in name_raw[:len(name_str)]))
            attrs_ok = sum(attrs) > 0 and all((b < 200 for b in attrs))
            if is_named and attrs_ok:
                try:
                    race_idx = win._analyzer.read_bytes(win._anchor + 532, 1)[0]
                    if 0 <= race_idx < 8:
                        race_jas = ['ブレトン', 'レッドガード', 'ノルド', 'ダークエルフ', 'ハイエルフ', 'ウッドエルフ', 'カジート', 'アルゴニアン']
                        win._chargen_race_ja = race_jas[race_idx]
                except OSError:
                    pass
                try:
                    cls_id = win._analyzer.read_bytes(win._anchor + 535, 1)[0]
                    cls_map = settings.get('arena_class_id_map', {}) or {}
                    cls_en = cls_map.get(str(cls_id))
                    if cls_en:
                        win._chargen_class_en = cls_en
                        win._chargen_class_ja = _CHARGEN_CLASS_JA.get(cls_en, cls_en)
                except OSError:
                    pass
                win._sync_attributes_race_class()
                win._activate_choose_attributes_panel()
                _log.info('connect: ChooseAttributes panel auto-activated (name=%r race=%s class=%s)', name_str, win._chargen_race_ja, win._chargen_class_ja)
        except OSError:
            pass
    win._sync_attributes_chargen_mode()
    win._apply_display_active_for_state()
    win._poll_timer.start()

def detect_top_level_at_connect(win) -> None:
    try:
        from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN, CHARGEN_DONE_OFFSET
        raw = win._analyzer.read_bytes(win._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
        img = raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
    except (OSError, ImportError, AttributeError):
        img = ''
    img_upper = img.upper()
    try:
        from screen_detector import get_chargen_subscreen
        if get_chargen_subscreen(win) is not None:
            win._top_level_state = 'chargen'
            _log.info('top_level: connect-time detect → chargen (chargen flags, img=%r)', img)
            return
    except ImportError:
        pass
    if img_upper in ('QUOTE.IMG', 'SCROLL01.IMG', 'SCROLL02.IMG', 'MENU.IMG', 'LOADSAVE.IMG', 'PERCNTRO.XMI'):
        state = 'pregame'
        if img_upper == 'LOADSAVE.IMG':
            win._pregame_loadsave_seen = True
    elif img_upper == 'VISION.XMI':
        try:
            hp_raw = win._analyzer.read_bytes(win._anchor + 509, 2)
            hp = hp_raw[0] | hp_raw[1] << 8
        except (OSError, AttributeError, IndexError):
            hp = None
        if hp == 0:
            state = 'normal-play'
        else:
            try:
                exp_raw = win._analyzer.read_bytes(win._anchor + 1453, 4)
                exp = exp_raw[0] | exp_raw[1] << 8 | exp_raw[2] << 16 | exp_raw[3] << 24
                state = 'chargen' if exp == 0 else 'normal-play'
            except (OSError, AttributeError, IndexError):
                state = 'normal-play'
    elif img_upper.startswith('INTRO') and img_upper.endswith('.IMG') or img_upper in ('EVLINTRO.XMI', 'NOEXIT.IMG', 'BONUS.IMG', 'PARCH.CIF'):
        state = 'chargen'
    elif img_upper in ('PAGE2.IMG', 'OP.IMG', 'LOGBOOK.IMG', 'AUTOMAP.IMG', 'POINTER.IMG', 'NEWPOP.IMG'):
        state = 'normal-play'
    else:
        try:
            exp_raw = win._analyzer.read_bytes(win._anchor + 1453, 4)
            exp = exp_raw[0] | exp_raw[1] << 8 | exp_raw[2] << 16 | exp_raw[3] << 24
            state = 'chargen' if exp == 0 else 'normal-play'
        except (OSError, AttributeError):
            state = 'normal-play'
    win._top_level_state = state
    _log.info('top_level: connect-time detect → %s (img=%r)', state, img)
    if state == 'normal-play':
        try:
            win._ui_router.set_panel_mode('translate', reason='connect_normal_play')
        except (AttributeError, RuntimeError):
            pass
__all__ = ['on_connect_done', 'detect_top_level_at_connect']
