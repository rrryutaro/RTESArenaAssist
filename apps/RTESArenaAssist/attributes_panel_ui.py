
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from attributes_panel import AttributesPanel

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget,
)

import i18n_helper as i18n

from attributes_panel import (
    UNKNOWN,
    COL_PRIMARY_LABEL,
    COL_PRIMARY_VALUE,
    COL_DERIVED_LABEL,
    COL_DERIVED_VALUE,
    COL_KILOS_LABEL,
    COL_KILOS_VALUE,
    ROW_NAME,
    ROW_RACE,
    ROW_CLASS,
    ROW_HEADER_GAP,
    ROW_PRIMARY_FIRST,
    ROW_PRE_BONUS_GAP,
    ROW_BONUS_PTS,
    ROW_POST_BONUS_GAP,
    ROW_HP,
    ROW_FATIGUE,
    ROW_GOLD,
    ROW_GOLD_EXP_GAP,
    ROW_EXP,
    ROW_LEVEL,
    ATTR_DISPLAY_EN,
    ATTR_DISPLAY_JA,
    DERIVED_COL2_BY_ATTR,
    DERIVED_COL3_BY_ATTR,
    DERIVED_LABELS,
    STAT_LABELS,
    _bilingual,
)


def build_main_grid(panel: "AttributesPanel") -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    panel._main_grid = g
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(8)
    g.setVerticalSpacing(2)

    for row, lbl in ((ROW_NAME, panel._name_lbl),
                     (ROW_RACE, panel._race_lbl),
                     (ROW_CLASS, panel._class_lbl)):
        lbl.setObjectName("valueLabel")
        g.addWidget(lbl, row, 0, 1, 4,
                    alignment=Qt.AlignmentFlag.AlignLeft)

    g.setRowMinimumHeight(ROW_HEADER_GAP, 8)

    for idx in range(8):
        row = ROW_PRIMARY_FIRST + idx

        primary_lbl = QLabel(_bilingual(ATTR_DISPLAY_EN[idx],
                                        ATTR_DISPLAY_JA[idx]) + ":")
        primary_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        g.addWidget(primary_lbl, row, COL_PRIMARY_LABEL,
                    alignment=Qt.AlignmentFlag.AlignLeft)

        sb = QSpinBox()
        sb.setRange(0, 255)
        sb.setMinimumWidth(72)
        sb.setMaximumWidth(96)
        sb.setAlignment(Qt.AlignmentFlag.AlignRight)
        sb.setProperty("attr_idx", idx)
        sb.valueChanged.connect(panel._on_attr_changed)
        panel._spinboxes.append(sb)
        g.addWidget(sb, row, COL_PRIMARY_VALUE,
                    alignment=Qt.AlignmentFlag.AlignLeft)

        d_key = DERIVED_COL2_BY_ATTR.get(idx)
        if d_key:
            en, ja = DERIVED_LABELS[d_key]
            d_label = QLabel(_bilingual(en, ja) + ":")
            d_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            g.addWidget(d_label, row, COL_DERIVED_LABEL,
                        alignment=Qt.AlignmentFlag.AlignLeft)
            d_value = QLabel(UNKNOWN)
            d_value.setObjectName("valueLabel")
            d_value.setMinimumWidth(56)
            d_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
            g.addWidget(d_value, row, COL_DERIVED_VALUE,
                        alignment=Qt.AlignmentFlag.AlignLeft)
            panel._derived[d_key] = d_value

        k_key = DERIVED_COL3_BY_ATTR.get(idx)
        if k_key:
            en, ja = DERIVED_LABELS[k_key]
            k_label = QLabel(_bilingual(en, ja) + ":")
            k_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            g.addWidget(k_label, row, COL_KILOS_LABEL,
                        alignment=Qt.AlignmentFlag.AlignLeft)
            k_value = QLabel(UNKNOWN)
            k_value.setObjectName("valueLabel")
            k_value.setMinimumWidth(56)
            k_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
            g.addWidget(k_value, row, COL_KILOS_VALUE,
                        alignment=Qt.AlignmentFlag.AlignLeft)
            panel._derived[k_key] = k_value

    g.setRowMinimumHeight(ROW_PRE_BONUS_GAP, 16)

    en, ja = DERIVED_LABELS["bonus_pts"]
    bp_label = QLabel(_bilingual(en, ja) + ":")
    panel._bp_spin = QSpinBox()
    panel._bp_spin.setRange(0, 255)
    panel._bp_spin.setMinimumWidth(80)
    panel._bp_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
    panel._bp_spin.valueChanged.connect(panel._on_bonus_changed)
    bp_widget = QWidget()
    bp_h = QHBoxLayout(bp_widget)
    bp_h.setContentsMargins(0, 0, 0, 0)
    bp_h.setSpacing(6)
    bp_h.addStretch(1)
    bp_h.addWidget(bp_label)
    bp_h.addWidget(panel._bp_spin)
    bp_h.addStretch(1)
    panel._bp_widget = bp_widget
    bp_widget.setVisible(False)
    g.addWidget(bp_widget, ROW_BONUS_PTS, 0, 1, 6,
                alignment=Qt.AlignmentFlag.AlignHCenter)

    g.setRowMinimumHeight(ROW_POST_BONUS_GAP, 16)

    stat_rows = [
        (ROW_HP,       "hp"),
        (ROW_FATIGUE,  "fatigue"),
        (ROW_GOLD,     "gold"),
        (ROW_EXP,      "experience"),
        (ROW_LEVEL,    "level"),
    ]
    for row, key in stat_rows:
        en, ja = STAT_LABELS[key]
        label = QLabel(_bilingual(en, ja) + ":")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        g.addWidget(label, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        v_lbl = QLabel(UNKNOWN)
        v_lbl.setObjectName("valueLabel")
        v_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        g.addWidget(v_lbl, row, 1, 1, 3,
                    alignment=Qt.AlignmentFlag.AlignLeft)
        panel._stats[key] = v_lbl

    g.setRowMinimumHeight(ROW_GOLD_EXP_GAP, 8)

    g.setColumnStretch(COL_KILOS_VALUE + 1, 1)

    return w


def build_cheat_values_group(panel: "AttributesPanel") -> QGroupBox:
    grp = QGroupBox(i18n.tr("status.cheat_values_title"), panel)
    g = QGridLayout(grp)
    g.setContentsMargins(8, 8, 8, 8)
    g.setHorizontalSpacing(8)
    g.setVerticalSpacing(4)
    panel._cheat_value_spins: dict[str, QSpinBox] = {}
    for row, (key, label_key, vmax) in enumerate(panel._CHEAT_VALUE_SPECS):
        lbl = QLabel(i18n.tr(label_key) + ":")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight
                         | Qt.AlignmentFlag.AlignVCenter)
        sb = QSpinBox()
        sb.setRange(0, vmax)
        sb.setAlignment(Qt.AlignmentFlag.AlignRight)
        sb.setMaximumWidth(120)
        btn = QPushButton(i18n.tr("status.cheat_apply"))
        btn.clicked.connect(
            lambda _checked=False, k=key: panel._write_cheat_value(k))
        panel._cheat_value_spins[key] = sb
        g.addWidget(lbl, row, 0)
        g.addWidget(sb, row, 1)
        g.addWidget(btn, row, 2)
    return grp
