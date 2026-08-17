from __future__ import annotations
import re
from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget
import i18n_helper as i18n
import assist_settings as settings
OFF_NAME = 429
OFF_PRIMARY_1 = 461
OFF_PRIMARY_2 = 469
PRIMARY_LEN = 8
OFF_DAMAGE_I16 = 477
OFF_BONUS_PTS_U8 = 4764
OFF_HEALTH_CURR_U16 = 509
OFF_HEALTH_MAX_U16 = 511
OFF_SPELL_PTS_CURR = 522
OFF_SPELL_PTS_MAX = 524
OFF_RACE_INDEX = 424
OFF_CLASS_INDEX = 425
OFF_LEVEL_U16 = 541
OFF_LEVEL_U8 = 426
OFF_GOLD_U32 = 1474
OFF_EXP_U32 = 1453
OFF_FATIGUE_U16 = 513
OFF_FATIGUE_MAX = None
OFF_BONUS_PTS = None
ATTR_KEYS = ('STR', 'INT', 'WIL', 'AGI', 'SPD', 'END', 'PER', 'LUC')

def attr_label(attr_key: str) -> str:
    return i18n.text(f'status.attr.{attr_key}')
DERIVED_COL2_BY_ATTR: dict[int, str] = {0: 'damage', 1: 'spell_pts', 2: 'magic_def', 3: 'to_hit', 5: 'health', 6: 'charisma'}
DERIVED_COL3_BY_ATTR: dict[int, str] = {0: 'max_kilos', 3: 'to_defend', 5: 'heal_mod'}
DERIVED_LABEL_KEYS: dict[str, str] = {'damage': 'status.derived.damage', 'spell_pts': 'status.derived.spell_pts', 'magic_def': 'status.derived.magic_def', 'to_hit': 'status.derived.to_hit', 'to_defend': 'status.derived.to_defend', 'health': 'status.derived.health', 'charisma': 'status.derived.charisma', 'heal_mod': 'status.derived.heal_mod', 'max_kilos': 'status.derived.max_kilos', 'bonus_pts': 'status.derived.bonus_pts'}
STAT_LABEL_KEYS: dict[str, str] = {'hp': 'status.stat.health', 'fatigue': 'status.stat.fatigue', 'gold': 'status.stat.gold', 'experience': 'status.stat.experience', 'level': 'status.stat.level'}

def resolve_class_en_from_label(label: Optional[str]) -> Optional[str]:
    text = (label or '').strip()
    if not text:
        return None

    def _canonical_from_en(value: str) -> Optional[str]:
        value_norm = value.strip().lower()
        try:
            from class_list_panel import CLASS_LIST_ORDER
            for canonical in CLASS_LIST_ORDER:
                if value_norm == canonical.lower():
                    return canonical
        except ImportError:
            pass
        return None
    direct = _canonical_from_en(text)
    if direct:
        return direct
    m = re.search('[（(]\\s*([A-Za-z ]+)\\s*[)）]', text)
    if m:
        from_paren = _canonical_from_en(m.group(1))
        if from_paren:
            return from_paren
    try:
        from class_list_panel import resolve_class_from_display_name
        resolved = resolve_class_from_display_name(text)
        if resolved:
            return resolved
    except ImportError:
        pass
    return None
from attribute_formulas import _scale_100_to_256, _scale_256_to_100
import attribute_formulas as _attribute_formulas
calc_damage_bonus = _attribute_formulas.calc_damage_bonus
calc_max_kilos = _attribute_formulas.calc_max_kilos
calc_magic_defense = _attribute_formulas.calc_magic_defense
calc_bonus_to_hit = _attribute_formulas.calc_bonus_to_hit
calc_bonus_to_health = _attribute_formulas.calc_bonus_to_health
calc_max_stamina = _attribute_formulas.calc_max_stamina

def _signed(value: int) -> str:
    return f'+{value}' if value >= 0 else str(value)
POLL_INTERVAL_MS = 100
UNKNOWN = '—'
COL_PRIMARY_LABEL = 0
COL_PRIMARY_VALUE = 1
COL_DERIVED_LABEL = 2
COL_DERIVED_VALUE = 3
COL_KILOS_LABEL = 4
COL_KILOS_VALUE = 5
ROW_NAME = 0
ROW_RACE = 1
ROW_CLASS = 2
ROW_HEADER_GAP = 3
ROW_PRIMARY_FIRST = 4
ROW_PRIMARY_LAST = 11
ROW_PRE_BONUS_GAP = 12
ROW_BONUS_PTS = 13
ROW_POST_BONUS_GAP = 14
ROW_HP = 15
ROW_FATIGUE = 16
ROW_GOLD = 17
ROW_GOLD_EXP_GAP = 18
ROW_EXP = 19
ROW_LEVEL = 20

def _bilingual(label_id: str) -> str:
    en = i18n.lang_value_in(label_id, 'en') or ''
    translated = i18n.text(label_id)
    if not en or en == translated:
        return translated or en
    return f'{en} ({translated})'

class AttributesPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._analyzer = None
        self._anchor: int = 0
        self._cheat_enabled: bool = bool(settings.get('cheat_enabled', False)) and bool(settings.get('cheat_status_change', False))
        self._cheat_parent: bool = bool(settings.get('cheat_enabled', False))
        self._health_max_enabled: bool = self._compute_always_max('cheat_health_max')
        self._fatigue_max_enabled: bool = self._compute_always_max('cheat_fatigue_max')
        self._spell_max_enabled: bool = self._compute_always_max('cheat_spell_max')
        self._chargen_mode: bool = False
        self._is_bonus_screen: bool = False
        self._freeze_updates: bool = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._race_label: Optional[str] = None
        self._class_label: Optional[str] = None
        self._spinboxes: list[QSpinBox] = []
        self._derived: dict[str, QLabel] = {}
        self._stats: dict[str, QLabel] = {}
        self._name_lbl = QLabel(UNKNOWN)
        self._race_lbl = QLabel(UNKNOWN)
        self._class_lbl = QLabel(UNKNOWN)
        self._build_ui()
        self._apply_cheat_state(self._cheat_enabled)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        self._cheat_note_lbl = QLabel('')
        self._cheat_note_lbl.setObjectName('dimLabel')
        self._cheat_note_lbl.setVisible(False)
        root.addWidget(self._cheat_note_lbl)
        root.addWidget(self._build_main_grid())
        self._cheat_values_group = self._build_cheat_values_group()
        self._cheat_values_group.setVisible(self._cheat_parent)
        root.addWidget(self._cheat_values_group)
        root.addSpacing(12)
        root.addSpacing(12)
        note = QLabel(i18n.tr('status.note_redraw'))
        note.setObjectName('dimLabel')
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch(1)

    def _build_main_grid(self) -> QWidget:
        from attributes_panel_ui import build_main_grid
        return build_main_grid(self)

    def set_memory_target(self, analyzer, anchor: int) -> None:
        self._analyzer = analyzer
        self._anchor = anchor
        self._poll()
        self._poll_timer.start()
        self._apply_write_permission_state()

    def clear_memory_target(self) -> None:
        self._analyzer = None
        self._anchor = 0
        self._poll_timer.stop()

    def set_chargen_mode(self, mode: bool) -> None:
        self._chargen_mode = mode
        self._bp_widget.setVisible(mode or self._is_bonus_screen)

    def set_is_bonus_screen(self, mode: bool) -> None:
        if self._is_bonus_screen == mode:
            return
        self._is_bonus_screen = mode
        self._bp_widget.setVisible(self._chargen_mode or mode)

    def set_race_class(self, race: Optional[str], cls: Optional[str]) -> None:
        self._race_label = race
        self._class_label = cls
    _CHEAT_VALUE_SPECS = (('health', 'status.cheat_field_hp', 65535), ('fatigue', 'status.cheat_field_fatigue', 200), ('spell', 'status.cheat_field_spell', 65535), ('gold', 'status.cheat_field_gold', 65535), ('exp', 'status.cheat_field_exp', 9999999))

    def _build_cheat_values_group(self) -> QGroupBox:
        from attributes_panel_ui import build_cheat_values_group
        return build_cheat_values_group(self)

    def _write_cheat_value(self, key: str) -> None:
        if not self._cheat_parent:
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, 'can_write', False):
            self._cheat_note_lbl.setText(i18n.tr('status.no_write_permission'))
            self._cheat_note_lbl.setVisible(True)
            return
        sb = getattr(self, '_cheat_value_spins', {}).get(key)
        if sb is None:
            return
        value = int(sb.value())

        def _u16(off: int, v: int) -> None:
            v &= 65535
            self._analyzer.write_bytes(self._anchor + off, bytes([v & 255, v >> 8 & 255]))
        try:
            if key == 'health':
                _u16(OFF_HEALTH_CURR_U16, value)
            elif key == 'spell':
                _u16(OFF_SPELL_PTS_CURR, value)
            elif key == 'gold':
                v = value & 4294967295
                self._analyzer.write_bytes(self._anchor + OFF_GOLD_U32, bytes([v & 255, v >> 8 & 255, v >> 16 & 255, v >> 24 & 255]))
            elif key == 'exp':
                v = value & 4294967295
                self._analyzer.write_bytes(self._anchor + OFF_EXP_U32, bytes([v & 255, v >> 8 & 255, v >> 16 & 255, v >> 24 & 255]))
            elif key == 'fatigue':
                raw256 = max(0, min(1023, round(value * 256 / 100)))
                _u16(OFF_FATIGUE_U16, raw256 << 6)
        except (OSError, AttributeError):
            pass

    def _on_cheat_toggled(self, on: bool) -> None:
        self._cheat_enabled = on
        settings.set_val('cheat_enabled', on)
        self._apply_cheat_state(on)
        self._apply_write_permission_state()

    def _compute_always_max(self, key: str) -> bool:
        if not bool(settings.get('cheat_enabled', False)):
            return False
        return bool(settings.get(key, False))

    def apply_cheat_settings(self) -> None:
        new_cheat = bool(settings.get('cheat_enabled', False)) and bool(settings.get('cheat_status_change', False))
        if new_cheat != self._cheat_enabled:
            self._cheat_enabled = new_cheat
            self._apply_cheat_state(new_cheat)
            self._apply_write_permission_state()
        self._health_max_enabled = self._compute_always_max('cheat_health_max')
        self._fatigue_max_enabled = self._compute_always_max('cheat_fatigue_max')
        self._spell_max_enabled = self._compute_always_max('cheat_spell_max')
        self._cheat_parent = bool(settings.get('cheat_enabled', False))
        if hasattr(self, '_cheat_values_group'):
            self._cheat_values_group.setVisible(self._cheat_parent)

    def _apply_cheat_state(self, on: bool) -> None:
        all_spins = list(self._spinboxes)
        if hasattr(self, '_bp_spin'):
            all_spins.append(self._bp_spin)
        for sb in all_spins:
            sb.setReadOnly(not on)
            sb.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows if on else QSpinBox.ButtonSymbols.NoButtons)
            sb.setStyleSheet('')
            if on:
                sb.setMinimumWidth(72)
                sb.setMaximumWidth(96)
            else:
                sb.setMinimumWidth(0)
                sb.setMaximumWidth(72)
            sb.updateGeometry()
        if hasattr(self, '_main_grid') and self._main_grid is not None:
            self._main_grid.invalidate()
        if on:
            self._cheat_note_lbl.setText(i18n.tr('status.cheat_enabled'))
        else:
            self._cheat_note_lbl.setText(i18n.tr('status.cheat_disabled_note'))

    def _on_bonus_changed(self, value: int) -> None:
        if not self._cheat_enabled:
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, 'can_write', False):
            return
        try:
            payload = bytes([max(0, min(255, int(value)))])
            self._analyzer.write_bytes(self._anchor + OFF_BONUS_PTS_U8, payload)
        except OSError:
            pass

    def _apply_write_permission_state(self) -> None:
        if self._cheat_enabled and self._analyzer is not None and (not getattr(self._analyzer, 'can_write', True)):
            self._cheat_note_lbl.setText(i18n.tr('status.no_write_permission'))

    def set_freeze_updates(self, freeze: bool) -> None:
        self._freeze_updates = freeze

    def set_display_active(self, active: bool) -> None:
        if active:
            self._freeze_updates = False
        else:
            self._freeze_updates = True
            self._clear_display()

    def _clear_display(self) -> None:
        self._name_lbl.setText(UNKNOWN)
        self._race_lbl.setText(UNKNOWN)
        self._class_lbl.setText(UNKNOWN)
        for sb in self._spinboxes:
            sb.blockSignals(True)
            sb.setValue(0)
            sb.blockSignals(False)
        for w in self._derived.values():
            w.setText(UNKNOWN)
        for w in self._stats.values():
            w.setText(UNKNOWN)
        self._bp_spin.blockSignals(True)
        self._bp_spin.setValue(0)
        self._bp_spin.blockSignals(False)

    def _poll(self) -> None:
        from attributes_panel_poll import poll_attributes
        poll_attributes(self)

    def _read_u16(self, addr: int) -> int:
        b = self._analyzer.read_bytes(addr, 2)
        return b[0] | b[1] << 8

    def _read_u32(self, addr: int) -> int:
        b = self._analyzer.read_bytes(addr, 4)
        return b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24

    def _next_exp_threshold(self, current_level: Optional[int]) -> Optional[int]:
        if current_level is None or self._chargen_mode:
            return None
        try:
            cls_byte = self._analyzer.read_bytes(self._anchor + OFF_CLASS_INDEX, 1)[0]
            mapping = settings.get('arena_play_class_id_map', {}) or {}
            class_en = mapping.get(str(cls_byte))
            if not class_en:
                class_en = resolve_class_en_from_label(self._class_label)
            if not class_en:
                class_en = resolve_class_en_from_label(self._class_lbl.text())
            if not class_en:
                return None
            from experience_calc import exp_threshold_for_next_level_by_name
            return exp_threshold_for_next_level_by_name(class_en, current_level)
        except (OSError, AttributeError, ImportError):
            return None

    def _lookup_class_display(self, cls_idx: int) -> Optional[str]:
        mapping = settings.get('arena_play_class_id_map', {}) or {}
        en = mapping.get(str(cls_idx))
        if not en:
            return None
        name = i18n.value('classes', en)
        if name and name != en:
            return f'{name} ({en})'
        return en

    def _on_attr_changed(self, value: int) -> None:
        if not self._cheat_enabled:
            return
        sb = self.sender()
        if not isinstance(sb, QSpinBox):
            return
        idx = sb.property('attr_idx')
        if not isinstance(idx, int):
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, 'can_write', False):
            return
        if self._chargen_mode or self._is_bonus_screen:
            raw_val = max(0, min(255, int(value)))
        else:
            raw_val = max(0, min(255, round(value * 256 / 100)))
        try:
            payload = bytes([raw_val])
            self._analyzer.write_bytes(self._anchor + OFF_PRIMARY_1 + idx, payload)
            self._analyzer.write_bytes(self._anchor + OFF_PRIMARY_2 + idx, payload)
        except OSError:
            pass
