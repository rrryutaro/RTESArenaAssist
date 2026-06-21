
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

import i18n_helper as i18n
import assist_settings as settings



OFF_NAME            = 0x1AD
OFF_PRIMARY_1       = 0x1CD
OFF_PRIMARY_2       = 0x1D5
PRIMARY_LEN         = 8

OFF_DAMAGE_I16      = 0x1DD
OFF_BONUS_PTS_U8    = 0x129C
OFF_HEALTH_CURR_U16 = 0x1FD
OFF_HEALTH_MAX_U16  = 0x1FF


OFF_SPELL_PTS_CURR  = 0x20A
OFF_SPELL_PTS_MAX   = 0x20C

OFF_RACE_INDEX      = 0x1A8
OFF_CLASS_INDEX     = 0x1A9

OFF_LEVEL_U16       = 0x21D
OFF_LEVEL_U8        = 0x1AA

OFF_GOLD_U16        = 0x5C2
OFF_EXP_U32         = 0x5AD
OFF_FATIGUE_U16      = 0x201
OFF_FATIGUE_MAX      = None
OFF_BONUS_PTS       = None


RACE_INDEX_TO_DISPLAY: dict[int, tuple[str, str]] = {
    0: ("Breton",   "ブレトン"),
    1: ("Redguard", "レッドガード"),
    2: ("Nord",     "ノルド"),
    3: ("Dark Elf", "ダークエルフ"),
    4: ("High Elf", "ハイエルフ"),
    5: ("Wood Elf", "ウッドエルフ"),
    6: ("Khajiit",  "カジート"),
    7: ("Argonian", "アルゴニアン"),
}


ATTR_KEYS = ("STR", "INT", "WIL", "AGI", "SPD", "END", "PER", "LUC")
ATTR_DISPLAY_EN = ("Str", "Int", "Wil", "Agi", "Spd", "End", "Per", "Luc")
ATTR_DISPLAY_JA = ("筋力", "知性", "意志力", "敏捷", "速度", "持久力", "個性", "幸運")

DERIVED_COL2_BY_ATTR: dict[int, str] = {
    0: "damage",
    1: "spell_pts",
    2: "magic_def",
    3: "to_hit",
    5: "health",
    6: "charisma",
}

DERIVED_COL3_BY_ATTR: dict[int, str] = {
    0: "max_kilos",
    3: "to_defend",
    5: "heal_mod",
}

DERIVED_LABELS: dict[str, tuple[str, str]] = {
    "damage":     ("Damage",    "ダメージ"),
    "spell_pts":  ("Spell Pts", "呪文ポイント"),
    "magic_def":  ("Magic Def", "魔法防御"),
    "to_hit":     ("to Hit",    "命中"),
    "to_defend":  ("to Defend", "防御"),
    "health":     ("Health",    "体力"),
    "charisma":   ("Charisma",  "魅力"),
    "heal_mod":   ("Heal Mod",  "回復補正"),
    "max_kilos":  ("Max Kilos", "最大重量"),
    "bonus_pts":  ("BONUS PTS", "ボーナスPTS"),
}

STAT_LABELS: dict[str, tuple[str, str]] = {
    "hp":         ("Health",     "体力"),
    "fatigue":    ("Fatigue",    "疲労"),
    "gold":       ("Gold",       "ゴールド"),
    "experience": ("Experience", "経験値"),
    "level":      ("Level",      "レベル"),
}


def resolve_class_en_from_label(label: Optional[str]) -> Optional[str]:
    text = (label or "").strip()
    if not text:
        return None

    def _canonical_from_en(value: str) -> Optional[str]:
        value_norm = value.strip().lower()
        try:
            from class_list_panel import CLASS_LIST_ORDER
            for canonical, _kana, _kanji in CLASS_LIST_ORDER:
                if value_norm == canonical.lower():
                    return canonical
        except ImportError:
            pass
        return None

    direct = _canonical_from_en(text)
    if direct:
        return direct

    m = re.search(r"[（(]\s*([A-Za-z ]+)\s*[)）]", text)
    if m:
        from_paren = _canonical_from_en(m.group(1))
        if from_paren:
            return from_paren

    try:
        from class_list_panel import CLASS_LIST_ORDER
        for canonical, kana, kanji in CLASS_LIST_ORDER:
            if text == kana or (kanji and text == kanji):
                return canonical
            if kanji and text == f"{kana}（{kanji}）":
                return canonical
    except ImportError:
        pass

    try:
        from controllers.chargen_helpers import _CHARGEN_CLASS_JA
        for en_name, ja_name in _CHARGEN_CLASS_JA.items():
            if text == ja_name:
                return en_name
    except ImportError:
        pass

    return None



from attribute_formulas import (  # noqa: E402
    _scale_100_to_256,
    _scale_256_to_100,
)
import attribute_formulas as _attribute_formulas  # noqa: E402

calc_damage_bonus = _attribute_formulas.calc_damage_bonus
calc_max_kilos = _attribute_formulas.calc_max_kilos
calc_magic_defense = _attribute_formulas.calc_magic_defense
calc_bonus_to_hit = _attribute_formulas.calc_bonus_to_hit
calc_bonus_to_health = _attribute_formulas.calc_bonus_to_health
calc_max_stamina = _attribute_formulas.calc_max_stamina


def _signed(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)



POLL_INTERVAL_MS = 100
UNKNOWN          = "—"

COL_PRIMARY_LABEL  = 0
COL_PRIMARY_VALUE  = 1
COL_DERIVED_LABEL  = 2
COL_DERIVED_VALUE  = 3
COL_KILOS_LABEL    = 4
COL_KILOS_VALUE    = 5

ROW_NAME           = 0
ROW_RACE           = 1
ROW_CLASS          = 2
ROW_HEADER_GAP     = 3
ROW_PRIMARY_FIRST  = 4
ROW_PRIMARY_LAST   = 11
ROW_PRE_BONUS_GAP  = 12
ROW_BONUS_PTS      = 13
ROW_POST_BONUS_GAP = 14
ROW_HP             = 15
ROW_FATIGUE        = 16
ROW_GOLD           = 17
ROW_GOLD_EXP_GAP   = 18
ROW_EXP            = 19
ROW_LEVEL          = 20


def _bilingual(en: str, ja: str) -> str:
    return f"{en} ({ja})"


class AttributesPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._analyzer = None
        self._anchor: int = 0
        self._cheat_enabled: bool = (
            bool(settings.get("cheat_enabled", False))
            and bool(settings.get("cheat_status_change", False))
        )
        self._cheat_parent: bool = bool(settings.get("cheat_enabled", False))
        self._health_max_enabled: bool = self._compute_always_max("cheat_health_max")
        self._fatigue_max_enabled: bool = self._compute_always_max("cheat_fatigue_max")
        self._spell_max_enabled: bool = self._compute_always_max("cheat_spell_max")
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
        self._stats:   dict[str, QLabel] = {}
        self._name_lbl  = QLabel(UNKNOWN)
        self._race_lbl  = QLabel(UNKNOWN)
        self._class_lbl = QLabel(UNKNOWN)

        self._build_ui()
        self._apply_cheat_state(self._cheat_enabled)


    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        self._cheat_note_lbl = QLabel("")
        self._cheat_note_lbl.setObjectName("dimLabel")
        self._cheat_note_lbl.setVisible(False)
        root.addWidget(self._cheat_note_lbl)

        root.addWidget(self._build_main_grid())

        self._cheat_values_group = self._build_cheat_values_group()
        self._cheat_values_group.setVisible(self._cheat_parent)
        root.addWidget(self._cheat_values_group)

        root.addSpacing(12)
        root.addSpacing(12)
        note = QLabel(i18n.tr("status.note_redraw"))
        note.setObjectName("dimLabel")
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


    _CHEAT_VALUE_SPECS = (
        ("health",  "status.cheat_field_hp",      65535),
        ("fatigue", "status.cheat_field_fatigue", 200),
        ("spell",   "status.cheat_field_spell",   65535),
        ("gold",    "status.cheat_field_gold",    65535),
        ("exp",     "status.cheat_field_exp",     9999999),
    )

    def _build_cheat_values_group(self) -> QGroupBox:
        from attributes_panel_ui import build_cheat_values_group
        return build_cheat_values_group(self)

    def _write_cheat_value(self, key: str) -> None:
        if not self._cheat_parent:
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, "can_write", False):
            self._cheat_note_lbl.setText(i18n.tr("status.no_write_permission"))
            self._cheat_note_lbl.setVisible(True)
            return
        sb = getattr(self, "_cheat_value_spins", {}).get(key)
        if sb is None:
            return
        value = int(sb.value())

        def _u16(off: int, v: int) -> None:
            v &= 0xFFFF
            self._analyzer.write_bytes(
                self._anchor + off, bytes([v & 0xFF, (v >> 8) & 0xFF]))

        try:
            if key == "health":
                _u16(OFF_HEALTH_CURR_U16, value)
            elif key == "spell":
                _u16(OFF_SPELL_PTS_CURR, value)
            elif key == "gold":
                _u16(OFF_GOLD_U16, value)
            elif key == "exp":
                v = value & 0xFFFFFFFF
                self._analyzer.write_bytes(
                    self._anchor + OFF_EXP_U32,
                    bytes([v & 0xFF, (v >> 8) & 0xFF,
                           (v >> 16) & 0xFF, (v >> 24) & 0xFF]))
            elif key == "fatigue":
                raw256 = max(0, min(1023, round(value * 256 / 100)))
                _u16(OFF_FATIGUE_U16, raw256 << 6)
        except (OSError, AttributeError):
            pass


    def _on_cheat_toggled(self, on: bool) -> None:
        self._cheat_enabled = on
        settings.set_val("cheat_enabled", on)
        self._apply_cheat_state(on)
        self._apply_write_permission_state()

    def _compute_always_max(self, key: str) -> bool:
        if not bool(settings.get("cheat_enabled", False)):
            return False
        return bool(settings.get(key, False))

    def apply_cheat_settings(self) -> None:
        new_cheat = (
            bool(settings.get("cheat_enabled", False))
            and bool(settings.get("cheat_status_change", False))
        )
        if new_cheat != self._cheat_enabled:
            self._cheat_enabled = new_cheat
            self._apply_cheat_state(new_cheat)
            self._apply_write_permission_state()
        self._health_max_enabled = self._compute_always_max("cheat_health_max")
        self._fatigue_max_enabled = self._compute_always_max("cheat_fatigue_max")
        self._spell_max_enabled = self._compute_always_max("cheat_spell_max")
        self._cheat_parent = bool(settings.get("cheat_enabled", False))
        if hasattr(self, "_cheat_values_group"):
            self._cheat_values_group.setVisible(self._cheat_parent)

    def _apply_cheat_state(self, on: bool) -> None:
        all_spins = list(self._spinboxes)
        if hasattr(self, "_bp_spin"):
            all_spins.append(self._bp_spin)
        for sb in all_spins:
            sb.setReadOnly(not on)
            sb.setButtonSymbols(
                QSpinBox.ButtonSymbols.UpDownArrows if on
                else QSpinBox.ButtonSymbols.NoButtons
            )
            sb.setStyleSheet("")
            if on:
                sb.setMinimumWidth(72)
                sb.setMaximumWidth(96)
            else:
                sb.setMinimumWidth(0)
                sb.setMaximumWidth(72)
            sb.updateGeometry()
        if hasattr(self, "_main_grid") and self._main_grid is not None:
            self._main_grid.invalidate()
        if on:
            self._cheat_note_lbl.setText(i18n.tr("status.cheat_enabled"))
        else:
            self._cheat_note_lbl.setText(i18n.tr("status.cheat_disabled_note"))

    def _on_bonus_changed(self, value: int) -> None:
        if not self._cheat_enabled:
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, "can_write", False):
            return
        try:
            payload = bytes([max(0, min(255, int(value)))])
            self._analyzer.write_bytes(self._anchor + OFF_BONUS_PTS_U8, payload)
        except OSError:
            pass

    def _apply_write_permission_state(self) -> None:
        if (self._cheat_enabled and self._analyzer is not None
                and not getattr(self._analyzer, "can_write", True)):
            self._cheat_note_lbl.setText(i18n.tr("status.no_write_permission"))


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
        return b[0] | (b[1] << 8)

    def _next_exp_threshold(self, current_level: Optional[int]) -> Optional[int]:
        if current_level is None or self._chargen_mode:
            return None
        try:
            cls_byte = self._analyzer.read_bytes(self._anchor + OFF_CLASS_INDEX, 1)[0]
            mapping = settings.get("arena_play_class_id_map", {}) or {}
            class_en = mapping.get(str(cls_byte))
            if not class_en:
                class_en = resolve_class_en_from_label(self._class_label)
            if not class_en:
                class_en = resolve_class_en_from_label(self._class_lbl.text())
            if not class_en:
                return None
            import arena_data
            cls_data = arena_data.get_class_by_name(class_en)
            if not cls_data:
                return None
            from experience_calc import exp_threshold_for_next_level
            return exp_threshold_for_next_level(cls_data["id"], current_level)
        except (OSError, AttributeError, ImportError):
            return None

    def _lookup_class_display(self, cls_idx: int) -> Optional[str]:
        mapping = settings.get("arena_play_class_id_map", {}) or {}
        en = mapping.get(str(cls_idx))
        if not en:
            return None
        try:
            from class_list_panel import CLASS_LIST_ORDER
            for canonical, kana, kanji in CLASS_LIST_ORDER:
                if canonical == en:
                    return f"{kana} ({en})"
        except ImportError:
            pass
        return en

    def _on_attr_changed(self, value: int) -> None:
        if not self._cheat_enabled:
            return
        sb = self.sender()
        if not isinstance(sb, QSpinBox):
            return
        idx = sb.property("attr_idx")
        if not isinstance(idx, int):
            return
        if self._analyzer is None or self._anchor == 0:
            return
        if not getattr(self._analyzer, "can_write", False):
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
