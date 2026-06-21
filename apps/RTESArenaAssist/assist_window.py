
import os
import re
import sys

from PySide6.QtCore import QEvent, QPoint, QRect, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSpinBox,
    QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

import struct
import time

import logging

import i18n_helper as i18n
import assist_log
import assist_settings as settings
import theme as theme_mod
from assist_constants import APP_NAME, WIN_W, WIN_H, WIN_MIN_W, WIN_MIN_H
from version import version_string
from layout_manager import LayoutManager, TrackMode, LayoutCorner, LayoutForm, calc_layout_zones
from layout_panel_translate import LayoutPanelTranslate

_log = logging.getLogger("assist_window")
from tabs.tab_translate import TabTranslate
from tabs.tab_status import TabStatus
from attributes_panel import AttributesPanel
from tabs.tab_dict import TabDict
from tabs.tab_save import TabSave
from tabs.tab_manual import TabManual
from tabs.tab_capture import TabCapture
try:
    from tabs.tab_map import TabMap
    _TAB_MAP_AVAILABLE = True
except Exception:  # noqa: BLE001
    TabMap = None  # type: ignore
    _TAB_MAP_AVAILABLE = False
try:
    from tabs.tab_journal import TabJournal
    _TAB_JOURNAL_AVAILABLE = True
except Exception:  # noqa: BLE001
    TabJournal = None  # type: ignore
    _TAB_JOURNAL_AVAILABLE = False
from windows.settings_dialog import _SettingsDialog
from controllers.img_screen_controller import ImgScreenController
from controllers.poll_controller import PollController
from controllers.window_chrome import WindowChrome
from controllers.layout_controller import LayoutController
from controllers.chargen_controller import ChargenController

if settings.get("screen_judge_enabled", True):
    try:
        from controllers.screen_judge_controller import ScreenJudgeController
        from tabs.tab_screen_judge import TabScreenJudge
        _SCREEN_JUDGE_AVAILABLE = True
    except ImportError as _sj_exc:
        _log.warning("screen_judge unavailable: %s", _sj_exc)
        ScreenJudgeController = None
        TabScreenJudge = None
        _SCREEN_JUDGE_AVAILABLE = False
else:
    ScreenJudgeController = None
    TabScreenJudge = None
    _SCREEN_JUDGE_AVAILABLE = False

_POLL_MS       = 100
_RESIZE_BORDER = 6
_APP_DIR       = os.path.dirname(os.path.abspath(__file__))
_USER_DIR      = (os.path.dirname(os.path.abspath(sys.executable))
                  if getattr(sys, "frozen", False) else _APP_DIR)

from controllers.chargen_helpers import (
    _CHARGEN_OPENING_HINT_ADDR, _CHARGEN_OPENING_MAXLEN,
    _CHARGEN_OPENING_FULLREAD,
    _CHARGEN_OPENING_SCAN_START, _CHARGEN_OPENING_SCAN_END,
    _CHARGEN_OPENING_PREFIXES,
    _CHARGEN_GOYENOW_HINT_ADDR, _CHARGEN_GOYENOW_HINT_CHECKLEN,
    _CHARGEN_GOYENOW_PREFIX,
    _CHARGEN_GOYENOW_SCAN_START, _CHARGEN_GOYENOW_SCAN_END,
    _GARBAGE_NPC_PATTERNS, _is_garbage_npc_buffer, _looks_like_cinematic,
    _CHARGEN_NAME_RE,
    _CHARGEN_CLASS_JA, _CHARGEN_PEOPLE_JA,
    _CHARGEN_RACE_INF_TO_JA,
    _CHARGEN_DYNAMIC_PATTERNS,
)

class _ConnectWorker(QThread):
    done   = Signal(int, int)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analyzer = None

    def run(self):
        try:
            from arena_bridge import ArenaMemoryAnalyzer, find_anchor
            self.analyzer = ArenaMemoryAnalyzer()
            self.analyzer.attach()
            anchor = find_anchor(self.analyzer)
            if anchor is None:
                self.analyzer.detach()
                self.analyzer = None
                self.failed.emit("Anchor not found — is Arena running in DOSBox?")
                return
            self.done.emit(self.analyzer.pid, anchor)
        except Exception as exc:
            if self.analyzer:
                try:
                    self.analyzer.detach()
                except Exception:
                    pass
                self.analyzer = None
            self.failed.emit(str(exc))


class AssistWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._analyzer = None
        self._anchor: int = 0
        self._worker: _ConnectWorker | None = None


        self._poll_timer = QTimer(self)
        self._poll_ms = settings.get("poll_interval_ms", _POLL_MS)
        self._poll_timer.setInterval(self._poll_ms)
        self._poll_timer.timeout.connect(self._poll)

        self._img_screen = ImgScreenController(self)

        self._poll_ctrl = PollController(self)

        self._chrome = WindowChrome(self)

        self._layout = LayoutController(self)

        self._chargen = ChargenController(self)

        from tts_service import TTSService
        from controllers.translation_feed import TranslationFeed
        from services.log_store import LogStore
        self._tts = TTSService()
        try:
            from tts_read_aloud import set_speaker as _set_speaker
            _set_speaker(self._tts.speak_now)
        except Exception:  # noqa: BLE001
            pass
        self._log_store = LogStore(
            max_entries=int(settings.get("log_max_entries", 2000)))
        self._translation_feed = TranslationFeed(
            self._tts, self, log_store=self._log_store)
        try:
            from controllers.map_ext_lifecycle import get_lifecycle
            get_lifecycle().add_store(self._log_store)
            get_lifecycle().add_on_load(self._translation_feed.reset_spoken)
        except Exception:  # noqa: BLE001
            pass
        self._apply_tts_settings()

        if _SCREEN_JUDGE_AVAILABLE and ScreenJudgeController is not None:
            self._screen_judge = ScreenJudgeController(self)
            _log.info("screen_judge: enabled")
        else:
            self._screen_judge = None
            _log.info("screen_judge: disabled (setting or import failed)")

        self._layout_mgr = LayoutManager(self)
        self._layout_corner = LayoutCorner(
            settings.get("layout_corner", LayoutCorner.TOP_LEFT.value)
        )
        try:
            self._layout_form = LayoutForm(settings.get("layout_form", LayoutForm.FORM_2.value))
        except ValueError:
            self._layout_form = LayoutForm.FORM_2
        self._is_layout_active:   bool             = False
        self._layout_old_central                   = None
        self._layout_saved_geo                     = None
        self._layout_dos_offset: tuple[int, int]   = (0, 0)
        self._layout_dos_size:   tuple[int, int]   = (0, 0)
        self._layout_dosbox_saved_rect             = None
        self._layout_dpr:        float             = 1.0
        self._layout_zone_widgets:  list           = []
        self._layout_translate_panel               = None

        self._is_embed_active:    bool             = False
        self._embed_old_central                    = None
        self._embed_saved_geo                      = None

        self._cursor_unlock_timer = QTimer(self)
        self._cursor_unlock_timer.setInterval(100)
        self._cursor_unlock_timer.timeout.connect(self._layout.unlock_cursor)

        self._img_name_prev:         str  = ""
        self._newgame_layout_pushed: bool = False
        self._startup_layout_pushed: bool = False

        self._trigger_flag_prev: int       = 0
        self._trigger_indices:   list      = []
        self._cached_trig_idx:   int       = 0
        self._cached_rt_x:       int | None = None
        self._cached_rt_z:       int | None = None
        self._mif_matcher                  = None

        self._npc_dialog_prev: str         = ""
        self._npc_dialog_text_prev: str    = ""
        self._ask_about_menu_active_prev: bool = False
        self._popup11_ask_recovery: bool   = False
        self._popup11_item_dyn_prev: tuple = (-1, -1)

        self._npc_phase: int | None        = None
        self._npc_conversation_active: bool = False
        self._npc_phase_unknown_prev: int | None = None
        from session import (
            SessionManager, NpcChatSession, TavernSession, TempleSession,
            EquipmentSession, MagesGuildSession,
        )
        self._session_manager: SessionManager = SessionManager()
        self._npc_chat_session: NpcChatSession = NpcChatSession()
        self._tavern_session: TavernSession = TavernSession()
        self._temple_session: TempleSession = TempleSession()
        self._equipment_session: EquipmentSession = EquipmentSession()
        self._mages_guild_session: MagesGuildSession = MagesGuildSession()
        self._session_manager.register(self._temple_session)
        self._session_manager.register(self._equipment_session)
        self._session_manager.register(self._mages_guild_session)
        self._session_manager.register(self._tavern_session)
        self._session_manager.register(self._npc_chat_session)
        self._tavern_active_prev: bool = False
        self._temple_active_prev: bool = False
        self._equipment_active_prev: bool = False
        self._mages_guild_active_prev: bool = False
        self._temple_menu_key_prev: tuple | None = None
        self._temple_active_template_key_prev: tuple | None = None
        self._temple_negot_key_prev: tuple | None = None
        self._temple_last_img_prev: str = ""
        self._loading_data_select_active: bool   = False
        self._loading_state_active: bool         = False
        self._loading_loadsave_seen_prev: bool   = False
        self._loading_state_post_remaining: int  = 0

        self._chargen_state_prev: int      = 0
        self._chargen_q_seq_prev: int      = 0
        self._in_chargen_name: bool        = False
        self._chargen_state_streak: int        = 0
        self._chargen_in_advice: bool          = False
        self._chargen_advice_state: int | None = None
        self._chargen_goyenow_displayed: bool  = False
        self._chargen_goyenow_state: int | None = None
        self._chargen_10q_displayed: bool      = False
        self._chargen_method_state: int | None = None
        self._chargen_distribute_displayed: bool = False
        self._chargen_choose_attrs_displayed: bool = False
        self._chargen_choose_attrs_state_val: int | None = None
        self._chargen_appearance_displayed: bool = False
        self._chargen_done_prev: int = 0
        self._chargen_opening_displayed: bool = False
        self._chargen_opening_retry: int = 0
        self._chargen_opening_text_prev: str = ""
        self._dungeon_entry_cleared: bool = False
        self._goyenow_scan_budget: int = 0
        self._advice_capture_age: int = -1
        self._chargen_method_window: bool      = False
        self._chargen_race_select_displayed: bool = False
        self._chargen_class_accept_displayed: bool = False
        self._chargen_race_desc_displayed: bool    = False
        self._chargen_sex_select_displayed: bool   = False
        self._chargen_complete_displayed: bool     = False
        self._last_chargen_subscreen: str | None   = None
        self._chargen_class_list_active: bool  = False
        self._is_in_chargen: bool              = False
        self._chargen_race_ja: str | None      = None
        self._chargen_class_ja: str | None     = None
        self._chargen_class_en: str | None     = None

        self._chargen_status_display_armed: bool = False

        self._chargen_attrs_state_anchor: int | None = None
        self._chargen_attrs_phase_seen: bool         = False

        self._chargen_attrs_modal_active: bool = False
        self._chargen_attrs_modal_kind: str | None = None
        self._chargen_attrs_phase_log_prev: tuple | None = None
        self._chargen_explanation_active: str | None = None
        self._chargen_explanation_distribute_npc_snapshot: bytes | None = None
        self._chargen_explanation_distribute_dlg_seen_open: bool = False
        self._chargen_goyenow_npc_snapshot: bytes | None = None
        self._chargen_goyenow_b7c4_prev: int | None = None

        self._theme_mode = settings.get("theme", "dark")

        self._top_level_state: str = "pregame"
        self._chargen_subscreen_last: str | None = None
        self._last_chargen_entry_key: tuple | None = None
        self._last_class_list_activation: str | None = None
        self._pregame_loadsave_seen: bool = False

        self._player_level_prev:    int | None = None
        self._player_bonus_prev:    int | None = None
        self._level_up_active:      bool       = False
        self._level_up_from:        int | None = None
        self._level_up_to:          int | None = None
        self._level_up_saw_bonus:   bool       = False
        self._bonus_screen_hold:    bool       = False
        self._char_screen_flag_prev: int        = 0
        self._char_screen_settling:  bool       = False
        self._char_screen_budget:    int        = 0
        self._spell_screen_active:   bool       = False
        self._spell_view_base:       int | None = None

        self._build_ui()
        self._restore_geometry()
        self._apply_theme()

        self._shutter_se_wav = None
        self._shutter_se_kind = None
        self._reload_shutter_se()

        if settings.get("always_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        QApplication.instance().installEventFilter(self)


    def _build_ui(self):
        from assist_window_ui import build_ui
        build_ui(self)


    def _open_settings(self):
        dlg = _SettingsDialog(self, self._theme_mode, self._layout_translate_panel)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        settings.set_val("save_dir",               dlg.game_dir)
        settings.set_val("backup_dir",             dlg.backup_dir)
        settings.set_val("capture_dir",            dlg.capture_dir)
        settings.set_val("capture_delete_confirm", dlg.delete_confirm)
        settings.set_val("capture_se_enabled",     dlg.capture_se_enabled)
        settings.set_val("capture_se_volume",      dlg.capture_se_volume)
        settings.set_val("capture_se_kind",        dlg.capture_se_kind)
        self._reload_shutter_se()

        settings.set_val("equipment_mark_equipped",     dlg.equipment_mark_equipped)
        settings.set_val("equipment_mark_equippable",   dlg.equipment_mark_equippable)
        settings.set_val("equipment_mark_unequippable", dlg.equipment_mark_unequippable)

        old_aot = settings.get("always_on_top", False)
        new_aot = dlg.always_on_top
        settings.set_val("always_on_top", new_aot)
        if new_aot != old_aot:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, new_aot)
            self.show()

        if dlg.theme != self._theme_mode:
            self._set_theme(dlg.theme)

        if dlg.ui_language != settings.get("ui_language", ""):
            settings.set_val("ui_language", dlg.ui_language)
            QMessageBox.information(
                self,
                i18n.tr("settings.language_restart_title"),
                i18n.tr("settings.language_restart_msg"))

        settings.set_val("keep_trigger_on_panel", dlg.keep_trigger_on_panel)

        settings.set_val("panel_translate_font_family_ja", dlg.font_family_ja)
        settings.set_val("panel_translate_font_size_ja",   dlg.font_size_ja)
        settings.set_val("panel_translate_font_family_en", dlg.font_family_en)
        settings.set_val("panel_translate_font_size_en",   dlg.font_size_en)
        settings.set_val("panel_translate_font_sync",      dlg.font_sync)
        if self._layout_translate_panel is not None:
            self._layout_translate_panel.apply_font_settings()

        if dlg.layout_dirty:
            try:
                self._layout.set_track_mode(TrackMode(dlg.layout_track_mode))
            except ValueError:
                pass
            try:
                self._layout.set_layout_corner(LayoutCorner(dlg.layout_corner))
            except ValueError:
                pass
            try:
                self._layout.set_layout_form(LayoutForm(dlg.layout_form))
            except ValueError:
                pass
            settings.set_val("layout_size_w", dlg.layout_size_w)
            settings.set_val("layout_size_h", dlg.layout_size_h)
            old_dos_top = settings.get("dosbox_always_on_top", False)
            if dlg.dosbox_always_on_top != old_dos_top:
                self._layout.toggle_dosbox_topmost(dlg.dosbox_always_on_top)

        new_poll_ms = max(100, min(5000, dlg.poll_interval_ms))
        settings.set_val("poll_interval_ms", new_poll_ms)
        if new_poll_ms != self._poll_ms:
            self._poll_ms = new_poll_ms
            self._poll_timer.setInterval(self._poll_ms)

        settings.set_val("cheat_enabled", dlg.cheat_enabled)
        settings.set_val("cheat_status_change", dlg.cheat_status_change)
        settings.set_val("cheat_reveal_map", dlg.cheat_reveal_map)
        settings.set_val("cheat_health_max", dlg.cheat_health_max)
        settings.set_val("cheat_fatigue_max", dlg.cheat_fatigue_max)
        settings.set_val("cheat_spell_max", dlg.cheat_spell_max)
        try:
            self._tab_status.apply_cheat_settings()
        except AttributeError:
            pass

        settings.set_val("map_wall_line_of_sight", dlg.map_wall_line_of_sight)
        settings.set_val("map_show_unexplored_floor",
                         dlg.map_show_unexplored_floor)
        settings.set_val("map_center_on_player", dlg.map_center_on_player)
        settings.set_val("map_show_grid", dlg.map_show_grid)
        settings.set_val("map_show_chunk_grid", dlg.map_show_chunk_grid)
        settings.set_val("map_show_chunk_coords", dlg.map_show_chunk_coords)
        settings.set_val("map_show_recenter_lines",
                         dlg.map_show_recenter_lines)
        settings.set_val("map_chunk_coord_font_size",
                         dlg.map_chunk_coord_font_size)
        settings.set_val("map_extended_display", dlg.map_extended_display)
        settings.set_val("wild_distinguish_road", dlg.wild_distinguish_road)
        settings.set_val("wild_show_edge", dlg.wild_show_edge)
        settings.set_val("wild_distinguish_edge", dlg.wild_distinguish_edge)
        settings.set_val("wild_show_crops", dlg.wild_show_crops)
        settings.set_val("wild_show_all_entrances",
                         dlg.wild_show_all_entrances)
        settings.set_val("wild_show_static_flats",
                         dlg.wild_show_static_flats)
        settings.set_val("translate_fallback_screen",
                         dlg.translate_fallback_screen)
        try:
            self._tab_map.apply_settings()
        except AttributeError:
            pass
        try:
            self._tab_translate.apply_map_settings()
        except AttributeError:
            pass

        settings.set_val("show_recognition_screen", dlg.show_recognition_screen)
        settings.set_val("show_img_info", dlg.show_img_info)
        settings.set_val("show_version", dlg.show_version)
        self._apply_view_settings()

        settings.set_val("tts_enabled", dlg.tts_enabled)
        settings.set_val("tts_engine", dlg.tts_engine)
        settings.set_val("tts_voice", dlg.tts_voice)
        settings.set_val("tts_vv_speaker", dlg.tts_vv_speaker)
        settings.set_val("tts_rate", dlg.tts_rate)
        settings.set_val("tts_volume", dlg.tts_volume)
        settings.set_val("tts_interrupt", dlg.tts_interrupt)
        settings.set_val("tts_target_situation", dlg.tts_target_situation)
        settings.set_val("tts_target_conversation",
                         dlg.tts_target_conversation)
        settings.set_val("tts_speaker_icon", dlg.tts_speaker_icon)
        settings.set_val("log_show_original", dlg.log_show_original)
        settings.set_val("log_show_datetime", dlg.log_show_datetime)
        _fmt = dlg.log_datetime_format
        if _fmt:
            settings.set_val("log_datetime_format", _fmt)
        settings.set_val("tts_name_reading", dlg.tts_name_reading)
        settings.set_val("log_max_entries", dlg.log_max_entries)
        try:
            self._log_store.set_max_entries(dlg.log_max_entries)
        except Exception:  # noqa: BLE001
            pass
        try:
            if getattr(self, "_tab_log", None) is not None:
                self._tab_log.refresh()
        except Exception:  # noqa: BLE001
            pass
        self._apply_tts_settings()

        settings.set_val("translate_tab_emulate_panel_hidden",
                         dlg.translate_tab_emulate_panel_hidden)

        self._tab_save.on_settings_changed()
        self._tab_capture.set_cap_dir(self._get_cap_dir())
        settings.set_val("dosbox_conf_path", dlg.dosbox_conf_path)

    def _toggle_always_on_top(self, checked: bool):
        settings.set_val("always_on_top", checked)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()


    def _on_connect_clicked(self):
        if self._analyzer is not None:
            self._disconnect()
        else:
            self._start_connect()

    def _start_connect(self):
        self._conn_btn.setEnabled(False)
        self._status_lbl.setText(i18n.tr("status.loading"))
        self._sb.showMessage(i18n.tr("status.loading"))
        self._worker = _ConnectWorker(self)
        self._worker.done.connect(self._on_connect_done)
        self._worker.failed.connect(self._on_connect_failed)
        self._worker.start()

    def _on_connect_done(self, pid: int, anchor: int):
        from controllers.connect_flow_controller import on_connect_done
        on_connect_done(self, pid, anchor)

    def _on_connect_failed(self, msg: str):
        self._conn_btn.setEnabled(True)
        self._conn_btn.setText(i18n.tr("connection.connect"))
        self._status_lbl.setText(i18n.tr("connection.status_disconnected"))
        self._sb.showMessage(f"{i18n.tr('common.error')}: {msg}")

    def _disconnect(self):
        self._poll_timer.stop()
        if self._analyzer:
            try:
                self._analyzer.detach()
            except Exception:
                pass
            self._analyzer = None
        self._anchor = 0
        self._conn_btn.setText(i18n.tr("connection.connect"))
        self._status_lbl.setText(i18n.tr("connection.status_disconnected"))
        self._anchor_lbl.setText("")
        self._img_name_lbl.setText("")
        self._img_name_prev = ""
        self._screen_id_prev = None
        self._screen_id_pending = None
        self._screen_id_stable_count = 0
        self._spell_detail_marker = None
        self._menu_active_prev = 0xFFFF
        self._flag_detail_skip_n = 0
        self._spell_detail_text_ready = True
        self._spell_detail_text_marker = None
        self._equipment_marker = None
        try:
            from template_parser import reset_cache
            reset_cache()
        except (ImportError, Exception):
            pass
        self._newgame_layout_pushed = False
        self._startup_layout_pushed = False
        self._tab_translate.set_connected(False)
        self._tab_status.clear_memory_target()
        try:
            self._tab_translate.appearance_faces_panel().clear_memory_target()
        except AttributeError:
            pass
        if self._layout_translate_panel is not None:
            self._layout_translate_panel.set_connected(False)
        self._is_in_chargen = False
        self._set_class_list_panel_mode(False)
        self._set_chargen_ui_state(False)
        self._mif_matcher = None
        self._top_level_state = "pregame"
        self._chargen_subscreen_last = None
        self._pregame_loadsave_seen = False
        self._layout_mgr.set_dosbox_pid(0)
        self._sb.showMessage(i18n.tr("status.ready"))


    def _transition_top_level(self, new_state: str, reason: str) -> None:
        if self._top_level_state == new_state:
            return
        _log.info("top_level: %s → %s (reason: %s)",
                  self._top_level_state, new_state, reason)
        self._top_level_state = new_state
        if new_state == "normal-play":
            try:
                self._ui_router.set_panel_mode("translate", reason="enter_normal_play")
            except (AttributeError, RuntimeError):
                pass
            try:
                self._ui_router.release_if_owner("load_screen")
            except (AttributeError, RuntimeError):
                pass
        if new_state == "normal-play":
            self._chargen_subscreen_last = None
            try:
                self._save_play_class_id_mapping(
                    getattr(self, "_chargen_class_en", None))
            except AttributeError:
                pass
            try:
                self._reset_map_marker_for_normal_play_entry()
            except AttributeError:
                pass
        if new_state != "chargen":
            self._chargen_status_display_armed = False
            self._chargen_attrs_state_anchor = None
            self._chargen_attrs_phase_seen = False
            self._chargen_attrs_modal_active = False
            self._chargen_attrs_modal_kind = None
            self._chargen_attrs_phase_log_prev = None
            self._chargen_explanation_active = None
            self._chargen_explanation_distribute_npc_snapshot = None
            self._chargen_explanation_distribute_dlg_seen_open = False
            self._chargen_goyenow_npc_snapshot = None
            self._chargen_goyenow_b7c4_prev = None
            try:
                if self._tab_status is not None:
                    self._tab_status.set_freeze_updates(False)
            except (AttributeError, RuntimeError):
                pass
        self._sync_attributes_chargen_mode()
        self._apply_display_active_for_state()

    def _update_attr_panel_placement(self) -> None:
        try:
            want_translate = (
                self._tabs.currentWidget() is self._tab_translate
                and self._tab_translate.panel_mode()
                in ("choose_attributes", "fallback_status")
            )
            if want_translate:
                self._tab_translate.mount_attributes_panel()
            else:
                self._tab_status.mount_attributes_panel()
        except (AttributeError, RuntimeError):
            pass

    def _apply_display_active_for_state(self) -> None:
        state = self._top_level_state
        if state == "normal-play":
            status_active = True
            map_active = True
            journal_active = True
        elif state == "chargen":
            status_active = self._chargen_status_display_armed
            map_active = False
            journal_active = False
        else:
            status_active = False
            map_active = False
            journal_active = False
        try:
            self._tab_status.set_display_active(status_active)
        except AttributeError:
            pass
        try:
            self._tab_map.set_display_active(map_active)
        except AttributeError:
            pass
        try:
            self._tab_journal.set_display_active(journal_active)
        except AttributeError:
            pass

    def _reset_map_marker_for_normal_play_entry(self) -> None:
        self._map_rt_x_last = None
        self._map_rt_z_last = None
        self._map_angle_last = None

    def _sync_attributes_chargen_mode(self) -> None:
        mode = (self._top_level_state == "chargen")
        try:
            self._tab_status.set_chargen_mode(mode)
        except AttributeError:
            pass

    def _detect_top_level_at_connect(self) -> None:
        from controllers.connect_flow_controller import (
            detect_top_level_at_connect)
        detect_top_level_at_connect(self)


    _POLL_SLOW_MS = 50.0

    def _poll(self):
        _t0 = time.perf_counter()
        self._poll_ctrl.poll()
        _elapsed_ms = (time.perf_counter() - _t0) * 1000.0
        phases = getattr(self, "_poll_phase_times", None) or {}
        checkpoints = getattr(self, "_poll_checkpoints", None) or []
        if _log.isEnabledFor(logging.DEBUG):
            breakdown = " ".join(
                f"{name}={ms:.1f}ms" for name, ms in phases.items())
            ckline = " ".join(
                f"{name}@{cum:.1f}" for name, cum in checkpoints)
            _log.debug(
                "poll timing: total=%.1fms%s%s",
                _elapsed_ms,
                f" [{breakdown}]" if breakdown else "",
                f" ck[{ckline}]" if ckline else "")

    def _update_translate_tab(self, entry: dict) -> None:
        from controllers.translation_update_controller import (
            update_translate_tab)
        update_translate_tab(self, entry)

    def _set_class_list_panel_mode(self, active: bool) -> None:
        mode = "class_list" if active else "translate"
        try:
            self._ui_router.set_panel_mode(mode)
        except AttributeError:
            pass
        self._chargen_class_list_active = active
        if active:
            try:
                import inf_text_lookup as itl_local
                entry = itl_local.lookup("_CHARGEN_CHOOSE_CLASS_", 0)
                if entry is not None:
                    p_orig = itl_local.get_text_panel(entry)
                    p_basic = itl_local.get_translation(entry) or ""
                    self._ui_router.update_panel_translation(
                        p_orig, p_basic)
            except (ImportError, AttributeError) as exc:
                _log.debug("class_list panel translate push skipped: %s", exc)

    def _activate_choose_attributes_panel(self, *, priority: int = 0) -> None:
        if self._chargen_class_list_active:
            self._set_class_list_panel_mode(False)
        try:
            self._ui_router.set_panel_mode(
                "choose_attributes", priority=priority)
        except AttributeError:
            pass
        self._set_chargen_ui_state(True)
        self._sync_attributes_race_class()

    def _sync_attributes_race_class(self) -> None:
        try:
            self._tab_status.set_race_class(self._chargen_race_ja, self._chargen_class_ja)
        except AttributeError:
            pass

    def _track_chargen_race_class(self, inf_key: str) -> None:
        if inf_key.startswith("_CHARGEN_RACE_"):
            race_key = inf_key[len("_CHARGEN_RACE_"):].rstrip("_")
            ja = _CHARGEN_RACE_INF_TO_JA.get(race_key)
            if ja:
                self._chargen_race_ja = ja
                self._sync_attributes_race_class()
        elif inf_key.startswith("_CHARGEN_CLASS_ADVICE_") or inf_key.startswith("_CHARGEN_RESULT_"):
            prefix = "_CHARGEN_CLASS_ADVICE_" if inf_key.startswith("_CHARGEN_CLASS_ADVICE_") else "_CHARGEN_RESULT_"
            cls_key = inf_key[len(prefix):].rstrip("_")
            cls_en = cls_key.replace("_", " ").title().replace(" ", "")
            self._chargen_class_en = cls_en
            ja = _CHARGEN_CLASS_JA.get(cls_en, cls_en)
            if ja:
                self._chargen_class_ja = ja
                self._sync_attributes_race_class()
            self._save_class_id_mapping(cls_en)

    def _save_class_id_mapping(self, cls_en: str) -> None:
        if self._analyzer is None or not cls_en:
            return
        try:
            cls_id = self._analyzer.read_bytes(self._anchor + 0x217, 1)[0]
        except OSError:
            return
        mapping = dict(settings.get("arena_class_id_map", {}) or {})
        if mapping.get(str(cls_id)) != cls_en:
            mapping[str(cls_id)] = cls_en
            settings.set_val("arena_class_id_map", mapping)
            _log.info("chargen: arena_class_id_map updated: %d → %s",
                      cls_id, cls_en)

    def _save_play_class_id_mapping(self, cls_en: str | None) -> None:
        if not cls_en and getattr(self, "_chargen_class_ja", None):
            for en_name, ja_name in _CHARGEN_CLASS_JA.items():
                if ja_name == self._chargen_class_ja:
                    cls_en = en_name
                    break
        if self._analyzer is None or not cls_en:
            return
        try:
            cls_id = self._analyzer.read_bytes(self._anchor + 0x1A9, 1)[0]
        except OSError:
            return
        mapping = dict(settings.get("arena_play_class_id_map", {}) or {})
        if mapping.get(str(cls_id)) != cls_en:
            mapping[str(cls_id)] = cls_en
            settings.set_val("arena_play_class_id_map", mapping)
            _log.info("normal-play: arena_play_class_id_map updated: %d → %s",
                      cls_id, cls_en)

    def _set_chargen_ui_state(self, in_chargen: bool) -> None:
        if self._is_in_chargen == in_chargen:
            return
        self._is_in_chargen = in_chargen
        try:
            self._tab_translate.set_chargen_active(in_chargen)
        except AttributeError:
            pass


    def _push_translation(self, original: str, translated: str,
                          panel_original: str | None = None,
                          panel_translated: str | None = None,
                          speech_role: str | None = None) -> None:
        from controllers.translation_update_controller import (
            push_translation)
        push_translation(self, original, translated,
                         panel_original=panel_original,
                         panel_translated=panel_translated,
                         speech_role=speech_role)







    def _get_cap_dir(self) -> str:
        return (settings.get("capture_dir", "")
                or settings.get("backup_dir", "")
                or os.path.join(_USER_DIR, "captures"))

    def _get_dosbox_window_resolution(self) -> tuple[int, int]:
        import dosbox_conf as dc
        path = settings.get("dosbox_conf_path", "") or dc.DEFAULT_CONF_PATH
        size = dc.get_window_size(path)
        if size:
            return size
        return 1024, 768

    def _apply_tts_settings(self) -> None:
        tts = getattr(self, "_tts", None)
        if tts is None:
            return
        tts.set_enabled(bool(settings.get("tts_enabled", False)))
        tts.set_interrupt(bool(settings.get("tts_interrupt", True)))
        tts.set_rate(int(settings.get("tts_rate", 0)))
        tts.set_volume(int(settings.get("tts_volume", 100)))
        tts.set_voice(settings.get("tts_voice", "") or "")
        tts.set_engine(settings.get("tts_engine", "sapi5") or "sapi5")
        tts.set_vv_speaker(int(settings.get("tts_vv_speaker", 0) or 0))

    def _apply_view_settings(self) -> None:
        show_img = bool(settings.get("show_img_info", True))
        show_ver = bool(settings.get("show_version", True))
        if hasattr(self, "_anchor_lbl"):
            self._anchor_lbl.setVisible(show_img)
        if hasattr(self, "_conn_ver_lbl"):
            self._conn_ver_lbl.setVisible(show_ver)
        if hasattr(self, "_sb_ver_lbl"):
            self._sb_ver_lbl.setVisible(show_ver)

    def _reload_shutter_se(self) -> None:
        kind = settings.get("capture_se_kind", "phone_camera")
        if self._shutter_se_kind == kind and self._shutter_se_wav is not None:
            return
        self._shutter_se_wav = None
        self._shutter_se_kind = kind
        try:
            import app_resources
            wav = app_resources.read_bytes(f"assets/se_{kind}.wav")
            if wav is None:
                wav = app_resources.read_bytes("assets/se_phone_camera.wav")
            self._shutter_se_wav = wav
        except Exception:
            self._shutter_se_wav = None

    def _capture(self):
        if settings.get("capture_se_enabled", True):
            self._reload_shutter_se()
            if self._shutter_se_wav is not None:
                try:
                    from services.sound_effect import play_wav_async
                    vol = float(settings.get("capture_se_volume", 0.3))
                    play_wav_async(self._shutter_se_wav, vol)
                except Exception:
                    pass
        try:
            import screen_capture as sc
            if not sc.is_available():
                self._sb.showMessage(i18n.tr("capture.no_pillow"), 5000)
                return

            out_dir = self._get_cap_dir()
            os.makedirs(out_dir, exist_ok=True)
            cap_no = sc.next_cap_no(out_dir)

            if self._is_layout_active:
                import ctypes
                import ctypes.wintypes
                r = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(int(self.winId()), ctypes.byref(r))
                img = sc.capture_screen_region(
                    r.left, r.top, r.right - r.left, r.bottom - r.top)
                if img:
                    path = os.path.join(out_dir, f"cap_{cap_no:03d}_layout.png")
                    img.save(path)
                    self._sb.showMessage(
                        i18n.tr("capture.saved", no=cap_no, count=1), 4000)
                    self._tab_capture.set_cap_dir(out_dir)
                else:
                    self._sb.showMessage(i18n.tr("capture.nothing"), 4000)
                return

            game_pid = self._analyzer.pid if self._analyzer else 0
            game_path, viewer_path = sc.save_screenshots(
                out_dir     = out_dir,
                cap_no      = cap_no,
                widget      = self,
                game_pid    = game_pid,
                game_prefix = "DOSBox",
            )
            saved = [p for p in (game_path, viewer_path) if p]
            if saved:
                self._sb.showMessage(
                    i18n.tr("capture.saved", no=cap_no, count=len(saved)), 4000)
                self._tab_capture.set_cap_dir(out_dir)
            else:
                self._sb.showMessage(i18n.tr("capture.nothing"), 4000)
        except Exception as exc:
            self._sb.showMessage(f"{i18n.tr('capture.error')}: {exc}", 5000)


    def _apply_theme(self):
        self.setStyleSheet(theme_mod.get_stylesheet(self._theme_mode))

    def _set_theme(self, mode: str):
        self._theme_mode = mode
        settings.set_val("theme", mode)
        self._apply_theme()


    def _restore_geometry(self):
        geo = settings.get("window_geometry", "")
        if geo:
            from PySide6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))


    def eventFilter(self, obj, event):
        return self._chrome.handle_event(obj, event)



    def moveEvent(self, event):
        super().moveEvent(event)
        self._layout.handle_move_event()


    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        try:
            self._tts.shutdown()
        except (AttributeError, RuntimeError):
            pass
        self._chrome.clear_edge_cursor()
        if self._is_layout_active:
            self._layout.exit_layout_mode()
        if self._is_embed_active:
            self._layout.exit_embed_layout_mode()
        self._layout_mgr.stop()
        geo_b64 = self.saveGeometry().toBase64().data().decode()
        settings.set_val("window_geometry", geo_b64)
        self._disconnect()
        if self._worker and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)


