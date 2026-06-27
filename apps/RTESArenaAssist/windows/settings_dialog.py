from __future__ import annotations
import os
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QMessageBox, QScrollArea, QTabWidget, QVBoxLayout, QWidget
import i18n_helper as i18n
import assist_settings as settings
import dosbox_conf as dc
from layout_manager import TrackMode, LayoutCorner, LayoutForm
from windows.settings_dialog_tabs import build_general_tab, build_display_tab, build_map_tab, build_translate_tab, build_tts_tab, build_cheat_tab, build_dosbox_tab
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_HERE)
_POLL_MS = 100
_WIN_RES_PRESETS = [('640×480  (2x)', 640, 480), ('800×600', 800, 600), ('960×720  (3x)', 960, 720), ('1024×768', 1024, 768), ('1280×720  (HD)', 1280, 720), ('1280×960  (4x)', 1280, 960), ('1600×900', 1600, 900), ('1600×1200', 1600, 1200), ('1920×1080 (FHD)', 1920, 1080), ('1920×1440 (6x)', 1920, 1440), ('2560×1440 (QHD)', 2560, 1440), ('カスタム', 0, 0)]
_FULL_RESOLUTIONS = ['desktop', 'original', '1280x720', '1920x1080', '2560x1440']
_OUTPUT_MODES = ['ddraw', 'surface', 'overlay', 'opengl', 'openglnb']
_SCALERS = ['none', 'normal2x', 'normal3x', 'advmame2x', 'advmame3x', 'advinterp2x', 'advinterp3x', 'hq2x', 'hq3x', '2xsai', 'super2xsai', 'supereagle', 'tv2x', 'tv3x', 'rgb2x', 'rgb3x', 'scan2x', 'scan3x']
_AUDIO_RATES = ['22050', '44100', '48000', '32000']
_MIDI_DEVICES = ['default', 'win32', 'none']

def _wrap_scroll(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll

class _SettingsDialog(QDialog):

    def __init__(self, parent=None, current_theme: str='system', translate_panel=None):
        super().__init__(parent)
        self.setWindowTitle(i18n.tr('settings.title'))
        self.setMinimumWidth(560)
        self.setMinimumHeight(540)
        self._theme_items = ['dark', 'light', 'system']
        self._current_theme = current_theme
        self._translate_panel = translate_panel
        self._dosbox_conf_path: str = settings.get('dosbox_conf_path', '') or dc.DEFAULT_CONF_PATH
        self._dosbox_lines: list = []
        self._dosbox_index: dict = {}
        self._dosbox_values: dict = {}
        self._dosbox_load_error: str = ''
        root = QVBoxLayout(self)
        root.setSpacing(8)
        self._tabs = QTabWidget()
        self._tabs.addTab(_wrap_scroll(self._build_general_tab()), i18n.tr('settings.tab_general'))
        self._tabs.addTab(_wrap_scroll(self._build_display_tab()), i18n.tr('settings.tab_display'))
        self._tabs.addTab(_wrap_scroll(self._build_map_tab()), i18n.tr('settings.tab_map'))
        self._tabs.addTab(_wrap_scroll(self._build_translate_tab()), i18n.tr('settings.tab_translate'))
        self._tabs.addTab(_wrap_scroll(self._build_tts_tab()), i18n.tr('settings.tab_tts', default='読み上げ'))
        self._tabs.addTab(_wrap_scroll(self._build_cheat_tab()), i18n.tr('settings.tab_cheat'))
        self._tabs.addTab(_wrap_scroll(self._build_dosbox_tab()), i18n.tr('settings.tab_dosbox'))
        root.addWidget(self._tabs, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        btns.rejected.connect(self._restore_fonts)
        root.addWidget(btns)
        self._dosbox_load()
        self._dosbox_populate()
        self._initial_dosbox_path: str = self._dosbox_conf_path
        try:
            self._initial_dosbox_values: dict = self._dosbox_collect()
        except (ValueError, AttributeError):
            self._initial_dosbox_values = {}
        self._initial_layout_track: str = settings.get('layout_track_mode', TrackMode.NONE.value)
        self._initial_layout_corner: str = settings.get('layout_corner', LayoutCorner.TOP_LEFT.value)
        self._initial_layout_form: str = settings.get('layout_form', LayoutForm.FORM_2.value)
        self._initial_layout_w: int = int(settings.get('layout_size_w', 1920) or 0)
        self._initial_layout_h: int = int(settings.get('layout_size_h', 1080) or 0)
        self._initial_dosbox_top: bool = bool(settings.get('dosbox_always_on_top', False))
        self._restore_geometry()

    def _restore_geometry(self) -> None:
        geom_b64 = settings.get('settings_dialog_geometry', '')
        if not geom_b64:
            return
        try:
            ba = QByteArray.fromBase64(geom_b64.encode('ascii'))
            self.restoreGeometry(ba)
        except (ValueError, UnicodeError):
            pass

    def _save_geometry(self) -> None:
        try:
            ba = self.saveGeometry()
            b64 = bytes(ba.toBase64()).decode('ascii')
            settings.set_val('settings_dialog_geometry', b64)
        except (RuntimeError, UnicodeError):
            pass

    def accept(self) -> None:
        self._save_geometry()
        super().accept()

    def reject(self) -> None:
        self._save_geometry()
        super().reject()

    def closeEvent(self, event) -> None:
        self._save_geometry()
        super().closeEvent(event)

    def _build_general_tab(self) -> QWidget:
        return build_general_tab(self, poll_ms_default=_POLL_MS)

    def _build_display_tab(self) -> QWidget:
        return build_display_tab(self)

    def _build_map_tab(self) -> QWidget:
        return build_map_tab(self)

    def _build_translate_tab(self) -> QWidget:
        return build_translate_tab(self)

    def _build_tts_tab(self) -> QWidget:
        return build_tts_tab(self)

    def _build_cheat_tab(self) -> QWidget:
        return build_cheat_tab(self)

    def _build_dosbox_tab(self) -> QWidget:
        return build_dosbox_tab(self, _WIN_RES_PRESETS, _FULL_RESOLUTIONS, _OUTPUT_MODES, _SCALERS, _AUDIO_RATES, _MIDI_DEVICES)

    def _make_form_group(self, title: str) -> tuple[QGroupBox, QFormLayout]:
        grp = QGroupBox(title)
        form = QFormLayout(grp)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(4)
        form.setContentsMargins(8, 6, 8, 6)
        return (grp, form)

    def _browse_game(self):
        start = self._game_edit.text() or os.path.expanduser('~')
        path = QFileDialog.getExistingDirectory(self, i18n.tr('settings.game_dir'), start)
        if path:
            self._game_edit.setText(path)

    def _browse_backup(self):
        start = self._bk_edit.text() or os.path.expanduser('~')
        path = QFileDialog.getExistingDirectory(self, i18n.tr('settings.backup_dir'), start)
        if path:
            self._bk_edit.setText(path)

    def _browse_capture(self):
        start = self._cap_edit.text() or self._bk_edit.text() or os.path.expanduser('~')
        path = QFileDialog.getExistingDirectory(self, i18n.tr('settings.capture_dir'), start)
        if path:
            self._cap_edit.setText(path)

    def _preview_shutter_se(self) -> None:
        kind = self.capture_se_kind
        vol = self.capture_se_volume
        import app_resources
        path = app_resources.resource_fs_path(f'assets/se_{kind}.wav')
        if not os.path.exists(path):
            return
        try:
            from services.sound_effect import play_wav_file
            play_wav_file(path, max(0.0, min(1.0, vol)))
        except Exception:
            pass

    def _on_font_sync_toggled(self, checked: bool) -> None:
        self._font_family_en.setEnabled(not checked)
        self._font_size_en.setEnabled(not checked)

    def _preview_fonts(self, *_) -> None:
        if self._translate_panel is None:
            return
        sync = self._font_sync_cb.isChecked()
        fam_ja = self._font_family_ja.currentFont().family()
        size_ja = self._font_size_ja.value()
        fam_en = fam_ja if sync else self._font_family_en.currentFont().family()
        size_en = size_ja if sync else self._font_size_en.value()
        self._translate_panel.apply_font_direct(fam_ja, size_ja, fam_en, size_en)

    def _restore_fonts(self) -> None:
        if self._translate_panel is not None:
            self._translate_panel.apply_font_settings()

    def _browse_dosbox_conf(self):
        start_dir = os.path.dirname(self._dosbox_conf_path or dc.DEFAULT_CONF_PATH)
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr('dosbox.conf_path'), start_dir, 'Conf Files (*.conf)')
        if path:
            self._dosbox_conf_path = path
            self._dosbox_path_edit.setText(path)
            self._dosbox_load()
            self._dosbox_populate()

    def _dosbox_load(self):
        path = self._dosbox_conf_path or dc.DEFAULT_CONF_PATH
        try:
            self._dosbox_lines, self._dosbox_index, self._dosbox_values = dc.read_conf(path)
            self._dosbox_load_error = ''
        except FileNotFoundError:
            self._dosbox_lines, self._dosbox_index, self._dosbox_values = ([], {}, {})
            self._dosbox_load_error = i18n.tr('dosbox.not_found', path=path)
        except OSError as exc:
            self._dosbox_lines, self._dosbox_index, self._dosbox_values = ([], {}, {})
            self._dosbox_load_error = str(exc)
        if self._dosbox_load_error:
            self._dosbox_error_lbl.setText(self._dosbox_load_error)
            self._dosbox_error_lbl.setVisible(True)
        else:
            self._dosbox_error_lbl.setVisible(False)

    def _dosbox_get(self, section: str, key: str, default: str='') -> str:
        return self._dosbox_values.get((section, key), default)

    def _dosbox_populate(self):
        winres = self._dosbox_get('sdl', 'windowresolution', '1024x768')
        try:
            ww, wh = (int(v.strip()) for v in winres.split('x', 1))
        except (ValueError, AttributeError):
            ww, wh = (1024, 768)
        preset_idx = len(_WIN_RES_PRESETS) - 1
        for i, (_, pw, ph) in enumerate(_WIN_RES_PRESETS[:-1]):
            if pw == ww and ph == wh:
                preset_idx = i
                break
        self._cb_winres_preset.setCurrentIndex(preset_idx)
        self._sp_winres_w.setValue(ww)
        self._sp_winres_h.setValue(wh)
        self._winres_custom_widget.setVisible(preset_idx == len(_WIN_RES_PRESETS) - 1)
        fullres = self._dosbox_get('sdl', 'fullresolution', 'desktop')
        idx = self._cb_fullres.findText(fullres)
        if idx >= 0:
            self._cb_fullres.setCurrentIndex(idx)
        else:
            self._cb_fullres.setCurrentText(fullres)
        self._chk_fullscreen.setChecked(self._dosbox_get('sdl', 'fullscreen', 'false').lower() == 'true')
        output = self._dosbox_get('sdl', 'output', 'ddraw')
        idx = self._cb_output.findText(output)
        self._cb_output.setCurrentIndex(max(idx, 0))
        self._chk_autolock.setChecked(self._dosbox_get('sdl', 'autolock', 'true').lower() == 'true')
        try:
            self._sp_sensitivity.setValue(int(self._dosbox_get('sdl', 'sensitivity', '100')))
        except ValueError:
            self._sp_sensitivity.setValue(100)
        self._chk_aspect.setChecked(self._dosbox_get('render', 'aspect', 'true').lower() == 'true')
        scaler_raw = self._dosbox_get('render', 'scaler', 'normal2x').split()[0]
        idx = self._cb_scaler.findText(scaler_raw)
        self._cb_scaler.setCurrentIndex(max(idx, 0))
        cycles_raw = self._dosbox_get('cpu', 'cycles', 'auto').lower()
        if cycles_raw == 'auto':
            self._cb_cycles_mode.setCurrentText('auto')
            self._edit_cycles.setText('')
        elif cycles_raw == 'max':
            self._cb_cycles_mode.setCurrentText('max')
            self._edit_cycles.setText('')
        elif cycles_raw.startswith('fixed'):
            parts = cycles_raw.split()
            self._cb_cycles_mode.setCurrentText('fixed')
            self._edit_cycles.setText(parts[1] if len(parts) > 1 else '')
        else:
            self._cb_cycles_mode.setCurrentText('auto')
            self._edit_cycles.setText('')
        self._on_cycles_mode_changed(self._cb_cycles_mode.currentText())
        self._chk_nosound.setChecked(self._dosbox_get('mixer', 'nosound', 'false').lower() == 'true')
        rate = self._dosbox_get('mixer', 'rate', '44100')
        idx = self._cb_rate.findText(rate)
        self._cb_rate.setCurrentIndex(max(idx, 0))
        midi = self._dosbox_get('midi', 'mididevice', 'default')
        idx = self._cb_mididevice.findText(midi)
        self._cb_mididevice.setCurrentIndex(max(idx, 0))

    def _get_dosbox_window_resolution(self) -> tuple[int, int]:
        idx = self._cb_winres_preset.currentIndex()
        if 0 <= idx < len(_WIN_RES_PRESETS) - 1:
            return (_WIN_RES_PRESETS[idx][1], _WIN_RES_PRESETS[idx][2])
        return (self._sp_winres_w.value(), self._sp_winres_h.value())

    def _dosbox_collect(self) -> dict:
        new_values = {}
        w, h = self._get_dosbox_window_resolution()
        new_values['sdl', 'windowresolution'] = f'{w}x{h}'
        new_values['sdl', 'fullresolution'] = self._cb_fullres.currentText().strip() or 'desktop'
        new_values['sdl', 'fullscreen'] = 'true' if self._chk_fullscreen.isChecked() else 'false'
        new_values['sdl', 'output'] = self._cb_output.currentText()
        new_values['sdl', 'autolock'] = 'true' if self._chk_autolock.isChecked() else 'false'
        new_values['sdl', 'sensitivity'] = str(self._sp_sensitivity.value())
        new_values['render', 'aspect'] = 'true' if self._chk_aspect.isChecked() else 'false'
        new_values['render', 'scaler'] = self._cb_scaler.currentText()
        mode = self._cb_cycles_mode.currentText()
        if mode == 'fixed':
            val = self._edit_cycles.text().strip()
            if not val.isdigit():
                raise ValueError(i18n.tr('dosbox.cycles_invalid', val=val))
            new_values['cpu', 'cycles'] = f'fixed {val}'
        else:
            new_values['cpu', 'cycles'] = mode
        new_values['mixer', 'nosound'] = 'true' if self._chk_nosound.isChecked() else 'false'
        new_values['mixer', 'rate'] = self._cb_rate.currentText()
        new_values['midi', 'mididevice'] = self._cb_mididevice.currentText()
        return new_values

    def _on_winres_preset_changed(self, idx: int):
        is_custom = idx == len(_WIN_RES_PRESETS) - 1
        self._winres_custom_widget.setVisible(is_custom)
        if not is_custom:
            _, w, h = _WIN_RES_PRESETS[idx]
            self._sp_winres_w.setValue(w)
            self._sp_winres_h.setValue(h)

    def _on_cycles_mode_changed(self, mode: str):
        enabled = mode == 'fixed'
        self._edit_cycles.setEnabled(enabled)
        self._lbl_cycles_hint.setVisible(not enabled)

    def _on_accept(self) -> None:
        if self._dosbox_load_error:
            self.accept()
            return
        try:
            new_values = self._dosbox_collect()
        except ValueError as exc:
            QMessageBox.warning(self, i18n.tr('common.error'), str(exc))
            self._tabs.setCurrentIndex(5)
            return
        path_changed = self._dosbox_conf_path != self._initial_dosbox_path
        values_changed = new_values != self._initial_dosbox_values
        if not path_changed and (not values_changed):
            self.accept()
            return
        path = self._dosbox_conf_path or dc.DEFAULT_CONF_PATH
        try:
            dc.backup_conf(path)
        except OSError as exc:
            ans = QMessageBox.question(self, i18n.tr('dosbox.save'), i18n.tr('dosbox.backup_failed_confirm', err=str(exc)))
            if ans != QMessageBox.StandardButton.Yes:
                self._tabs.setCurrentIndex(5)
                return
        try:
            dc.write_conf(path, self._dosbox_lines, self._dosbox_index, new_values)
        except OSError as exc:
            QMessageBox.warning(self, i18n.tr('common.error'), f"{i18n.tr('dosbox.save_error')}: {exc}")
            self._tabs.setCurrentIndex(5)
            return
        self._dosbox_load()
        self.accept()

    @property
    def layout_dirty(self) -> bool:
        if self.layout_track_mode != self._initial_layout_track:
            return True
        if self.layout_corner != self._initial_layout_corner:
            return True
        if self.layout_form != self._initial_layout_form:
            return True
        if self.layout_size_w != self._initial_layout_w:
            return True
        if self.layout_size_h != self._initial_layout_h:
            return True
        if self.dosbox_always_on_top != self._initial_dosbox_top:
            return True
        return False

    @property
    def game_dir(self) -> str:
        return self._game_edit.text().strip()

    @property
    def backup_dir(self) -> str:
        return self._bk_edit.text().strip()

    @property
    def capture_dir(self) -> str:
        return self._cap_edit.text().strip()

    @property
    def delete_confirm(self) -> bool:
        return self._del_confirm_cb.isChecked()

    @property
    def capture_se_enabled(self) -> bool:
        return self._cap_se_cb.isChecked()

    @property
    def capture_se_volume(self) -> float:
        return self._cap_se_volume.value() / 100.0

    @property
    def capture_se_kind(self) -> str:
        idx = self._cap_se_kind_combo.currentIndex()
        if 0 <= idx < len(self._cap_se_kind_items):
            return self._cap_se_kind_items[idx][0]
        return 'phone_camera'

    @property
    def equipment_mark_equipped(self) -> str:
        return self._mark_equipped.text()

    @property
    def equipment_mark_equippable(self) -> str:
        return self._mark_equippable.text()

    @property
    def equipment_mark_unequippable(self) -> str:
        return self._mark_unequippable.text()

    @property
    def always_on_top(self) -> bool:
        return self._aot_cb.isChecked()

    @property
    def keep_trigger_on_panel(self) -> bool:
        return self._keep_trigger_cb.isChecked()

    @property
    def theme(self) -> str:
        return self._theme_items[self._theme_combo.currentIndex()]

    @property
    def ui_language(self) -> str:
        idx = self._language_combo.currentIndex()
        if 0 <= idx < len(self._language_items):
            return self._language_items[idx]
        return ''

    @property
    def font_family_ja(self) -> str:
        return self._font_family_ja.currentFont().family()

    @property
    def font_size_ja(self) -> int:
        return self._font_size_ja.value()

    @property
    def font_family_en(self) -> str:
        return self._font_family_en.currentFont().family()

    @property
    def font_size_en(self) -> int:
        return self._font_size_en.value()

    @property
    def font_sync(self) -> bool:
        return self._font_sync_cb.isChecked()

    @property
    def layout_track_mode(self) -> str:
        return self._layout_track_combo.currentData()

    @property
    def layout_corner(self) -> str:
        return self._layout_corner_combo.currentData()

    @property
    def layout_form(self) -> str:
        return self._layout_form_combo.currentData()

    @property
    def layout_size_w(self) -> int:
        return self._layout_size_w.value()

    @property
    def layout_size_h(self) -> int:
        return self._layout_size_h.value()

    @property
    def dosbox_always_on_top(self) -> bool:
        return self._dosbox_top_cb.isChecked()

    @property
    def poll_interval_ms(self) -> int:
        return self._poll_ms_spin.value()

    @property
    def dosbox_conf_path(self) -> str:
        return self._dosbox_conf_path

    @property
    def cheat_enabled(self) -> bool:
        return self._cheat_cb.isChecked()

    @property
    def cheat_status_change(self) -> bool:
        return self._cheat_status_change_cb.isChecked()

    @property
    def cheat_reveal_map(self) -> bool:
        return self._cheat_reveal_map_cb.isChecked()

    @property
    def map_wall_line_of_sight(self) -> bool:
        return self._map_wall_los_cb.isChecked()

    @property
    def map_show_unexplored_floor(self) -> bool:
        return self._map_show_unexplored_cb.isChecked()

    @property
    def map_center_on_player(self) -> bool:
        return self._map_center_cb.isChecked()

    @property
    def map_show_grid(self) -> bool:
        return self._map_show_grid_cb.isChecked()

    @property
    def map_show_chunk_grid(self) -> bool:
        return self._map_show_chunk_grid_cb.isChecked()

    @property
    def map_show_chunk_coords(self) -> bool:
        return self._map_show_chunk_coords_cb.isChecked()

    @property
    def map_show_recenter_lines(self) -> bool:
        return self._map_show_recenter_lines_cb.isChecked()

    @property
    def map_chunk_coord_font_size(self) -> int:
        return self._map_chunk_coord_font_size.value()

    @property
    def map_extended_display(self) -> bool:
        return self._map_extended_display_cb.isChecked()

    @property
    def wild_distinguish_road(self) -> bool:
        return self._wild_distinguish_road_cb.isChecked()

    @property
    def wild_show_edge(self) -> bool:
        return self._wild_show_edge_cb.isChecked()

    @property
    def wild_distinguish_edge(self) -> bool:
        return self._wild_distinguish_edge_cb.isChecked()

    @property
    def wild_show_crops(self) -> bool:
        return self._wild_show_crops_cb.isChecked()

    @property
    def wild_show_all_entrances(self) -> bool:
        return self._wild_show_all_entrances_cb.isChecked()

    @property
    def wild_show_static_flats(self) -> bool:
        return self._wild_show_static_flats_cb.isChecked()

    @property
    def tts_enabled(self) -> bool:
        return self._tts_enabled_cb.isChecked()

    @property
    def tts_engine(self) -> str:
        cur = self._tts_engine_combo.currentData() or 'sapi5'
        if not getattr(self, '_tts_vv_available', False) and getattr(self, '_tts_engine_saved', 'sapi5') == 'voicevox':
            return 'voicevox'
        return cur

    @property
    def tts_voice(self) -> str:
        return self._tts_voice_combo.currentData() or ''

    @property
    def tts_vv_speaker(self) -> int:
        d = self._tts_vv_style_combo.currentData()
        if d is None:
            return int(getattr(self, '_tts_vv_speaker_saved', 0) or 0)
        return int(d)

    @property
    def tts_rate(self) -> int:
        return int(self._tts_rate_combo.currentData() or 0)

    @property
    def tts_volume(self) -> int:
        return int(self._tts_volume_slider.value())

    @property
    def tts_interrupt(self) -> bool:
        return self._tts_interrupt_cb.isChecked()

    @property
    def tts_cancel_on_close(self) -> bool:
        return self._tts_cancel_on_close_cb.isChecked()

    @property
    def tts_suppress_repeat(self) -> bool:
        return self._tts_suppress_repeat_cb.isChecked()

    @property
    def tts_highlight_reading(self) -> bool:
        return self._tts_highlight_reading_cb.isChecked()

    @property
    def tts_target_situation(self) -> bool:
        return self._tts_target_situation_cb.isChecked()

    @property
    def tts_target_conversation(self) -> bool:
        return self._tts_target_conversation_cb.isChecked()

    @property
    def tts_speaker_icon(self) -> bool:
        return self._tts_speaker_icon_cb.isChecked()

    @property
    def log_show_original(self) -> bool:
        return self._log_show_original_cb.isChecked()

    @property
    def log_max_entries(self) -> int:
        return int(self._log_max_entries_spin.value())

    @property
    def log_show_datetime(self) -> bool:
        return self._log_show_datetime_cb.isChecked()

    @property
    def log_datetime_format(self) -> str:
        data = self._log_datetime_format_combo.currentData()
        if data == '__custom__':
            return self._log_datetime_format_edit.text().strip()
        return data or ''

    @property
    def tts_name_reading(self) -> str:
        return self._tts_name_reading_edit.text().strip()

    @property
    def translate_fallback_screen(self) -> str:
        idx = self._fallback_combo.currentIndex()
        if 0 <= idx < len(self._fallback_items):
            return self._fallback_items[idx][0]
        return 'map'

    @property
    def cheat_health_max(self) -> bool:
        return self._cheat_health_max_cb.isChecked()

    @property
    def cheat_fatigue_max(self) -> bool:
        return self._cheat_fatigue_max_cb.isChecked()

    @property
    def cheat_spell_max(self) -> bool:
        return self._cheat_spell_max_cb.isChecked()

    @property
    def show_recognition_screen(self) -> bool:
        return self._show_recog_cb.isChecked()

    @property
    def show_img_info(self) -> bool:
        return self._show_img_cb.isChecked()

    @property
    def show_version(self) -> bool:
        return self._show_version_cb.isChecked()

    @property
    def translate_tab_emulate_panel_hidden(self) -> bool:
        return self._emulate_panel_hidden_cb.isChecked()
