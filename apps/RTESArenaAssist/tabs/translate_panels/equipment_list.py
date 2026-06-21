from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

import assist_settings as settings


_COL_YELLOW      = QColor("#EBC734")
_COL_TAN         = QColor("#D38E00")
_COL_RED         = QColor("#C72000")
_COL_CYAN        = QColor("#45BABE")
_COL_BRIGHT_CYAN = QColor("#8AFFFF")
_COL_DIM         = QColor("#6a8a9a")


def render_equipment_list(table: QTableWidget, items: list) -> None:
    table.setRowCount(0)

    mark_equipped     = settings.get("equipment_mark_equipped",     "Ｅ")
    mark_equippable   = settings.get("equipment_mark_equippable",   "")
    mark_unequippable = settings.get("equipment_mark_unequippable", "✕")

    for item_data in items:
        equipped        = item_data.get("equipped", False)
        is_unidentified = item_data.get("is_unidentified", False)
        can_equip       = item_data.get("can_equip", None)
        en         = item_data.get("en", "")
        ja         = item_data.get("ja", "") or "—"
        slot_label = item_data.get("slot_label", "") or "—"
        weight     = item_data.get("weight", "") or "—"
        condition  = item_data.get("condition", "") or "—"
        effect     = item_data.get("effect", "") or "—"
        if weight == "n/a":
            weight = "—"

        if is_unidentified and equipped:
            name_color = _COL_BRIGHT_CYAN
        elif is_unidentified:
            name_color = _COL_CYAN
        elif can_equip is False:
            name_color = _COL_RED
        elif equipped:
            name_color = _COL_YELLOW
        else:
            name_color = _COL_TAN

        if equipped:
            mark = mark_equipped
        elif can_equip is False:
            mark = mark_unequippable
        else:
            mark = mark_equippable

        row = table.rowCount()
        table.insertRow(row)

        cells = [
            (mark,      name_color, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter),
            ("?" if is_unidentified else "",
             _COL_CYAN if is_unidentified else _COL_DIM,
             Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter),
            (slot_label, _COL_DIM,  Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter),
            (en,        name_color, Qt.AlignmentFlag.AlignLeft   | Qt.AlignmentFlag.AlignVCenter),
            (ja,        name_color, Qt.AlignmentFlag.AlignLeft   | Qt.AlignmentFlag.AlignVCenter),
            (weight,    _COL_DIM,   Qt.AlignmentFlag.AlignRight  | Qt.AlignmentFlag.AlignVCenter),
            (condition, _COL_DIM,   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter),
            (effect,    _COL_DIM,   Qt.AlignmentFlag.AlignLeft   | Qt.AlignmentFlag.AlignVCenter),
        ]
        for col, (text, color, align) in enumerate(cells):
            cell = QTableWidgetItem(text)
            cell.setTextAlignment(align)
            cell.setForeground(color)
            table.setItem(row, col, cell)

    for col_idx in (2, 5, 6, 7):
        table.resizeColumnToContents(col_idx)
