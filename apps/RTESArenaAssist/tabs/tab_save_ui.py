"""
tab_save_ui.py — TabSave UI ビルダー

tab_save.py の _setup_ui 相当をモジュールレベル関数として保持する。
ロジック・スロット・スタック・シグナルハンドラはすべて tab_save.py 本体に残す。

循環 import 禁止: このモジュールは tab_save.py を import しない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.tab_save import TabSave

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

import i18n_helper as i18n


def build_ui(tab: "TabSave") -> None:
    """
    TabSave の UI を構築し、ウィジェット参照を tab に設定する。
    tab_save.py の _setup_ui から cut-paste（self → tab リネーム・インデント調整のみ）。
    """
    root = QVBoxLayout(tab)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    # ── メイン水平スプリッタ ──────────────────────────────────
    tab._main_split = QSplitter(Qt.Orientation.Horizontal)
    tab._main_split.setHandleWidth(4)

    # === 左ペイン ===
    left_w = QWidget()
    left_lay = QVBoxLayout(left_w)
    left_lay.setContentsMargins(0, 4, 0, 0)
    left_lay.setSpacing(2)

    refresh_row = QHBoxLayout()
    refresh_row.setContentsMargins(4, 0, 4, 0)
    refresh_row.addStretch()
    tab._btn_refresh = QPushButton(i18n.tr("save.refresh"))
    tab._btn_refresh.setFixedHeight(22)
    refresh_row.addWidget(tab._btn_refresh)
    left_lay.addLayout(refresh_row)

    tab._left_list = QListWidget()
    tab._left_list.setObjectName("saveLeftList")
    left_lay.addWidget(tab._left_list)

    left_w.setMinimumWidth(150)
    left_w.setMaximumWidth(270)
    tab._main_split.addWidget(left_w)

    # === 右ペイン（垂直スプリッタ）===
    tab._right_split = QSplitter(Qt.Orientation.Vertical)
    tab._right_split.setHandleWidth(4)

    # --- 右上: アクションバー + スロットテーブル ---
    top_w = QWidget()
    top_lay = QVBoxLayout(top_w)
    top_lay.setContentsMargins(4, 4, 4, 2)
    top_lay.setSpacing(4)

    # アクションボタン行
    tab._action_row = QHBoxLayout()
    tab._action_row.setSpacing(3)

    # game モードボタン
    tab._btn_backup_all      = QPushButton(i18n.tr("save.backup_all"))
    tab._btn_backup_checked  = QPushButton(i18n.tr("save.backup_checked"))
    tab._btn_backup_selected = QPushButton(i18n.tr("save.backup_selected"))
    tab._game_btns = [
        tab._btn_backup_all,
        tab._btn_backup_checked,
        tab._btn_backup_selected,
    ]

    # backup モードボタン
    tab._btn_restore_selected = QPushButton(i18n.tr("save.restore_selected"))
    tab._btn_restore_checked  = QPushButton(i18n.tr("save.restore_checked"))
    tab._btn_restore_all      = QPushButton(i18n.tr("save.restore_all"))
    tab._btn_delete           = QPushButton(i18n.tr("save.delete"))
    tab._backup_btns = [
        tab._btn_restore_selected,
        tab._btn_restore_checked,
        tab._btn_restore_all,
        tab._btn_delete,
    ]

    for btn in tab._game_btns + tab._backup_btns:
        tab._action_row.addWidget(btn)
    tab._action_row.addStretch()
    top_lay.addLayout(tab._action_row)

    # スロットテーブル（5列: ☐ | No. | 名称 | ラベル | 日付）
    tab._table = QTableWidget(0, 5)
    tab._table.setHorizontalHeaderLabels([
        "",
        i18n.tr("save.col_slot"),
        i18n.tr("save.col_save_name"),
        i18n.tr("save.col_label"),
        i18n.tr("save.col_date"),
    ])
    hh = tab._table.horizontalHeader()
    hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    tab._table.setColumnWidth(0, 28)
    tab._table.setColumnWidth(1, 44)
    tab._table.setColumnWidth(4, 126)
    tab._table.setAlternatingRowColors(True)
    tab._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tab._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tab._table.verticalHeader().setVisible(False)
    tab._table.setShowGrid(False)
    top_lay.addWidget(tab._table)

    tab._right_split.addWidget(top_w)

    # --- 右下: 詳細パネル ---
    tab._detail_scroll = QScrollArea()
    tab._detail_scroll.setWidgetResizable(True)
    tab._detail_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    tab._right_split.addWidget(tab._detail_scroll)

    tab._right_split.setSizes([340, 230])
    tab._main_split.addWidget(tab._right_split)
    tab._main_split.setSizes([185, 445])
    tab._main_split.setCollapsible(0, False)
    tab._main_split.setCollapsible(1, False)

    root.addWidget(tab._main_split)

    # 初期状態
    tab._update_action_bar(tab._SOURCE_GAME)
    tab._swap_detail_widget(QWidget())

    # スプリッターサイズを設定から復元（レイアウト確定後に実行）
    QTimer.singleShot(0, tab._restore_splitter_sizes)
