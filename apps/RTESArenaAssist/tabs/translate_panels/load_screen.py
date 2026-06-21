"""tabs/translate_panels/load_screen.py — LOADSAVE.IMG セーブスロット一覧レンダリング"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem


def render_load_screen_slots(table: QTableWidget, slots: list) -> None:
    """ロード画面テーブルをセーブスロット情報で更新する。

    slots: list of dict with keys: slot, save_name, note_label, modified
    """
    table.setRowCount(0)
    for info in slots:
        row = table.rowCount()
        table.insertRow(row)
        slot_item = QTableWidgetItem(str(info.get("slot", "")))
        slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 0, slot_item)
        table.setItem(row, 1, QTableWidgetItem(info.get("save_name") or ""))
        table.setItem(row, 2, QTableWidgetItem(info.get("note_label") or ""))
        table.setItem(row, 3, QTableWidgetItem(info.get("modified") or ""))
