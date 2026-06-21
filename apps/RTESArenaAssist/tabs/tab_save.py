"""
tab_save.py — セーブ管理タブ

レイアウト:
  左ペイン : QListWidget#saveLeftList
              - 先頭固定: 📁 ゲームフォルダ
              - 以降: {name}  {date} （バックアップ一覧、新しい順）
  右上ペイン: QTableWidget（スロット一覧）
              列: [☐ | No. | 名称 | ラベル | 日付]
  右下ペイン:
    ゲームモード: 選択スロット詳細 + メモ編集
    バックアップモード: タブ（バックアップ情報 / セーブデータ）
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import assist_settings as cfg
import i18n_helper as i18n
import save_manager
import save_reader

from tabs.tab_save_ui import build_ui


# ------------------------------------------------------------------
# モジュールレベルヘルパー
# ------------------------------------------------------------------

def _effective_backup_dir() -> str:
    d = cfg.get("backup_dir", "").strip()
    return d if d else save_manager.default_backup_dir()


def _sep_widget() -> QWidget:
    """水平区切り線（スタイルシート使用）。"""
    w = QWidget()
    w.setFixedHeight(1)
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    w.setStyleSheet("background-color: rgba(128,128,128,0.35);")
    return w


# ------------------------------------------------------------------
# TabSave
# ------------------------------------------------------------------

class TabSave(QWidget):
    """セーブ管理タブ。"""

    status_message = Signal(str)

    _SOURCE_GAME   = "game"
    _SOURCE_BACKUP = "backup"

    def __init__(self, parent=None):
        super().__init__(parent)

        self._source_type: str = self._SOURCE_GAME
        self._current_backup_meta: dict | None = None
        self._current_slot: int | None = None

        # 詳細パネル内の編集ウィジェット（再構築時に差し替え）
        self._note_name_edit:  QLineEdit | None      = None
        self._note_memo_edit:  QPlainTextEdit | None = None
        self._bk_name_edit:    QLineEdit | None      = None
        self._bk_tags_edit:    QLineEdit | None      = None
        self._bk_memo_edit:    QPlainTextEdit | None = None

        # ゲーム内セーブ変更検出用 (QFileSystemWatcher + 200ms debounce)
        self._save_watcher = QFileSystemWatcher(self)
        self._watcher_debounce = QTimer(self)
        self._watcher_debounce.setSingleShot(True)
        self._watcher_debounce.setInterval(200)
        self._watcher_debounce.timeout.connect(self._check_save_name_changes)
        self._save_watcher.fileChanged.connect(self._on_names_dat_changed)
        self._save_watcher.directoryChanged.connect(self._on_save_dir_changed)
        self._watched_names_path: str | None = None

        self._setup_ui()
        self._connect_signals()
        # 起動時にゲーム内セーブ名の整合性チェック + watcher 張る
        self._rebuild_save_watcher()
        self._check_save_name_changes()
        self._refresh()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _setup_ui(self):
        build_ui(self)

    def _connect_signals(self):
        self._btn_refresh.clicked.connect(self._refresh)
        self._left_list.currentRowChanged.connect(self._on_left_changed)
        self._table.currentCellChanged.connect(self._on_table_changed)

        self._btn_backup_all.clicked.connect(self._do_backup_all)
        self._btn_backup_checked.clicked.connect(self._do_backup_checked)
        self._btn_backup_selected.clicked.connect(self._do_backup_selected)

        self._btn_restore_selected.clicked.connect(self._do_restore_selected)
        self._btn_restore_checked.clicked.connect(self._do_restore_checked)
        self._btn_restore_all.clicked.connect(self._do_restore_all)
        self._btn_delete.clicked.connect(self._do_delete)

        # スプリッターサイズ保存（デバウンス 300ms）
        self._splitter_timer = QTimer(self)
        self._splitter_timer.setSingleShot(True)
        self._splitter_timer.setInterval(300)
        self._splitter_timer.timeout.connect(self._save_splitter_sizes)
        self._main_split.splitterMoved.connect(lambda *_: self._splitter_timer.start())
        self._right_split.splitterMoved.connect(lambda *_: self._splitter_timer.start())

    # ------------------------------------------------------------------
    # スプリッターサイズ 保存・復元
    # ------------------------------------------------------------------

    def _save_splitter_sizes(self):
        cfg.set_val("save_tab_split_h", self._main_split.sizes())
        cfg.set_val("save_tab_split_v", self._right_split.sizes())

    def _restore_splitter_sizes(self):
        sizes_h = cfg.get("save_tab_split_h")
        if isinstance(sizes_h, list) and len(sizes_h) == 2:
            self._main_split.setSizes(sizes_h)
        sizes_v = cfg.get("save_tab_split_v")
        if isinstance(sizes_v, list) and len(sizes_v) == 2:
            self._right_split.setSizes(sizes_v)

    # ------------------------------------------------------------------
    # アクションバー切替
    # ------------------------------------------------------------------

    def _update_action_bar(self, source_type: str):
        is_game = source_type == self._SOURCE_GAME
        for btn in self._game_btns:
            btn.setVisible(is_game)
        for btn in self._backup_btns:
            btn.setVisible(not is_game)

    # ------------------------------------------------------------------
    # 左リスト構築・更新
    # ------------------------------------------------------------------

    def _refresh(self, keep_backup_id: str | None = None):
        """左リストを再構築する。keep_backup_id が指定されたときはそのバックアップを選択する。"""
        self._left_list.blockSignals(True)
        self._left_list.clear()

        # ゲームフォルダ（先頭固定）
        game_item = QListWidgetItem(i18n.tr("save.source_game"))
        game_item.setData(Qt.ItemDataRole.UserRole, {"type": "game"})
        self._left_list.addItem(game_item)

        # バックアップ一覧（セパレータなし・アイコンなし）
        backup_dir = _effective_backup_dir()
        backups = save_manager.list_backups(backup_dir)
        for meta in backups:
            dt_str = meta.get("datetime", "")[:16].replace("T", " ")
            name = meta.get("name", "").strip()
            label = f"{name}  {dt_str}" if name else dt_str
            bk_item = QListWidgetItem(label)
            bk_item.setData(Qt.ItemDataRole.UserRole, {"type": "backup", "meta": meta})
            self._left_list.addItem(bk_item)

        self._left_list.blockSignals(False)

        # 選択行を決定: keep_backup_id があればそのバックアップ行を探す
        if keep_backup_id:
            for row in range(1, self._left_list.count()):
                item = self._left_list.item(row)
                data = item.data(Qt.ItemDataRole.UserRole) if item else None
                if data and data.get("meta", {}).get("id") == keep_backup_id:
                    self._left_list.setCurrentRow(row)
                    self._on_left_changed(row)
                    return
        # デフォルト: ゲームフォルダ
        self._left_list.setCurrentRow(0)
        self._on_left_changed(0)

    # ------------------------------------------------------------------
    # 左リスト選択変更
    # ------------------------------------------------------------------

    def _on_left_changed(self, row: int):
        if row < 0:
            return
        item = self._left_list.item(row)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            # セパレータ行: スキップ
            return

        src_type = data.get("type")
        if src_type == "game":
            self._source_type = self._SOURCE_GAME
            self._current_backup_meta = None
            self._update_action_bar(self._SOURCE_GAME)
            self._load_game_slots()
        elif src_type == "backup":
            self._source_type = self._SOURCE_BACKUP
            self._current_backup_meta = data["meta"]
            self._update_action_bar(self._SOURCE_BACKUP)
            self._load_backup_slots(data["meta"])

    # ------------------------------------------------------------------
    # テーブル読み込み
    # ------------------------------------------------------------------

    def _load_game_slots(self):
        """ゲームフォルダのスロットをテーブルに読み込む。"""
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._current_slot = None
        self._table.blockSignals(False)
        self._clear_edit_refs()
        self._swap_detail_widget(QWidget())

        game_dir = cfg.get("save_dir", "").strip()
        if not game_dir or not os.path.isdir(game_dir):
            return

        slots = save_manager.list_slots(game_dir)
        notes = save_manager.load_slot_notes(_effective_backup_dir())

        self._table.blockSignals(True)
        for slot in slots:
            info = save_reader.read_slot_info(game_dir, slot)
            row = self._table.rowCount()
            self._table.insertRow(row)

            # col 0: チェックボックス
            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            chk.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(row, 0, chk)

            # col 1: スロット番号
            slot_item = QTableWidgetItem(str(slot))
            slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            slot_item.setData(Qt.ItemDataRole.UserRole, slot)
            self._table.setItem(row, 1, slot_item)

            # col 2: 名称（NAMES.DAT の値のみ）
            save_name = info.get("save_name") or i18n.tr("save.parse_unknown")
            self._table.setItem(row, 2, QTableWidgetItem(save_name))

            # col 3: ラベル（ユーザーが付けたメモラベル）
            note_label = notes.get(str(slot), {}).get("name", "")
            self._table.setItem(row, 3, QTableWidgetItem(note_label))

            # col 4: 日付
            modified = info.get("modified") or ""
            self._table.setItem(row, 4, QTableWidgetItem(modified))
        self._table.blockSignals(False)

    def _load_backup_slots(self, meta: dict):
        """バックアップのスロットをテーブルに読み込む。"""
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._current_slot = None
        self._table.blockSignals(False)
        self._clear_edit_refs()

        slots       = meta.get("slots", [])
        slot_names  = meta.get("slot_names", {})
        slot_notes  = meta.get("slot_notes", {})
        backup_path = os.path.join(_effective_backup_dir(), meta["id"])

        self._table.blockSignals(True)
        for slot in slots:
            row = self._table.rowCount()
            self._table.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            chk.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(row, 0, chk)

            slot_item = QTableWidgetItem(str(slot))
            slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            slot_item.setData(Qt.ItemDataRole.UserRole, slot)
            self._table.setItem(row, 1, slot_item)

            # col 2: バックアップ時点の名称
            save_name = slot_names.get(str(slot), i18n.tr("save.parse_unknown"))
            self._table.setItem(row, 2, QTableWidgetItem(save_name))

            # col 3: バックアップ内のユーザーラベル（backup_meta.json から）
            note_label = slot_notes.get(str(slot), {}).get("name", "")
            self._table.setItem(row, 3, QTableWidgetItem(note_label))

            # col 4: 元のセーブファイルの最終更新日時（shutil.copy2 でタイムスタンプ保持）
            try:
                file_info = save_reader.read_slot_info(backup_path, slot)
                modified = file_info.get("modified", "")
            except Exception:
                modified = ""
            self._table.setItem(row, 4, QTableWidgetItem(modified))
        self._table.blockSignals(False)

        # バックアップ概要を詳細パネルに表示
        self._rebuild_detail_backup_overview(meta)

    # ------------------------------------------------------------------
    # テーブル選択変更
    # ------------------------------------------------------------------

    def _on_table_changed(self, current_row: int, _cc, _pr, _pc):
        if current_row < 0:
            if self._source_type == self._SOURCE_BACKUP and self._current_backup_meta:
                self._rebuild_detail_backup_overview(self._current_backup_meta)
            else:
                self._clear_edit_refs()
                self._swap_detail_widget(QWidget())
            return

        slot_item = self._table.item(current_row, 1)
        if not slot_item:
            return
        slot = slot_item.data(Qt.ItemDataRole.UserRole)
        self._current_slot = slot

        if self._source_type == self._SOURCE_GAME:
            self._rebuild_detail_game_slot(slot)
        else:
            self._rebuild_detail_backup_slot(slot)

    # ------------------------------------------------------------------
    # 詳細パネル構築ヘルパー
    # ------------------------------------------------------------------

    def _clear_edit_refs(self):
        """編集ウィジェットへの参照をリセットする。"""
        self._note_name_edit = None
        self._note_memo_edit = None
        self._bk_name_edit   = None
        self._bk_tags_edit   = None
        self._bk_memo_edit   = None

    def _swap_detail_widget(self, w: QWidget):
        """詳細スクロールエリアのウィジェットだけを差し替える（参照は触らない）。"""
        old = self._detail_scroll.takeWidget()
        if old:
            old.hide()
            old.setParent(self._detail_scroll)
            old.deleteLater()
        self._detail_scroll.setWidget(w)

    @staticmethod
    def _make_form() -> QFormLayout:
        """スタイル設定済みの QFormLayout を返す。"""
        form = QFormLayout()
        form.setSpacing(4)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return form

    # ------------------------------------------------------------------
    # 詳細パネル — ゲームスロット
    # ------------------------------------------------------------------

    def _rebuild_detail_game_slot(self, slot: int):
        # ① 先にリセット ② ウィジェット構築 ③ 参照を設定 ④ スワップ
        self._clear_edit_refs()

        game_dir   = cfg.get("save_dir", "").strip()
        backup_dir = _effective_backup_dir()
        notes      = save_manager.load_slot_notes(backup_dir)
        slot_note  = notes.get(str(slot), {})

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        hdr = QLabel(i18n.tr("save.slot_n").format(n=slot))
        hdr.setObjectName("detailHeader")
        lay.addWidget(hdr)

        info = save_reader.read_slot_info(game_dir, slot) if game_dir else {}
        form = self._make_form()
        form.addRow(
            i18n.tr("save.slot_save_name") + ":",
            QLabel(info.get("save_name") or i18n.tr("save.parse_unknown")),
        )
        form.addRow(
            i18n.tr("save.slot_modified") + ":",
            QLabel(info.get("modified") or "—"),
        )
        form.addRow(
            i18n.tr("save.slot_files") + ":",
            QLabel(str(info.get("file_count", 0))),
        )
        lay.addLayout(form)

        lay.addWidget(_sep_widget())

        memo_hdr = QLabel(f"📝  {i18n.tr('save.slot_note_name')}")
        lay.addWidget(memo_hdr)

        note_form = self._make_form()

        note_name_edit = QLineEdit()
        note_name_edit.setPlaceholderText(i18n.tr("save.slot_note_name_ph"))
        note_name_edit.setText(slot_note.get("name", ""))
        note_form.addRow(i18n.tr("save.slot_note_name") + ":", note_name_edit)

        note_memo_edit = QPlainTextEdit()
        note_memo_edit.setPlaceholderText(i18n.tr("save.slot_note_memo_ph"))
        note_memo_edit.setPlainText(slot_note.get("memo", ""))
        note_memo_edit.setFixedHeight(64)
        note_form.addRow(i18n.tr("save.slot_note_memo") + ":", note_memo_edit)
        lay.addLayout(note_form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_save = QPushButton(i18n.tr("save.save_notes"))
        btn_save.clicked.connect(lambda: self._do_save_notes(slot))
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        lay.addStretch()

        # ③ 参照を保存してから ④ スワップ
        self._note_name_edit = note_name_edit
        self._note_memo_edit = note_memo_edit
        self._swap_detail_widget(container)

    # ------------------------------------------------------------------
    # 詳細パネル — バックアップ概要（スロット未選択時）
    # ------------------------------------------------------------------

    def _rebuild_detail_backup_overview(self, meta: dict):
        self._clear_edit_refs()
        self._swap_detail_widget(self._build_backup_tabbed_widget(meta, slot=None))

    # ------------------------------------------------------------------
    # 詳細パネル — バックアップ内スロット選択時
    # ------------------------------------------------------------------

    def _rebuild_detail_backup_slot(self, slot: int):
        meta = self._current_backup_meta
        if not meta:
            self._clear_edit_refs()
            self._swap_detail_widget(QWidget())
            return
        self._clear_edit_refs()
        self._swap_detail_widget(
            self._build_backup_tabbed_widget(meta, slot=slot, initial_tab=1)
        )

    # ------------------------------------------------------------------
    # バックアップ詳細タブウィジェット共通ビルダー
    # ------------------------------------------------------------------

    def _build_backup_tabbed_widget(
        self, meta: dict, slot: int | None, initial_tab: int = 0
    ) -> QWidget:
        """
        タブ付き詳細ウィジェットを組み立てる。
          Tab0: バックアップ情報 + 編集フォーム
          Tab1: セーブデータ情報 + メモ編集（slot=None のときはヒント表示）
        _bk_*_edit / _note_*_edit 参照をこのメソッド内で self に設定する。
        """
        container = QWidget()
        outer_lay = QVBoxLayout(container)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        tabs = QTabWidget()

        # ── Tab 0: バックアップ情報 ─────────────────────────────────
        bk_tab = QWidget()
        bk_lay = QVBoxLayout(bk_tab)
        bk_lay.setContentsMargins(10, 10, 10, 10)
        bk_lay.setSpacing(8)

        bk_hdr = QLabel(meta.get("name") or i18n.tr("save.backup_detail_title"))
        bk_hdr.setObjectName("detailHeader")
        bk_lay.addWidget(bk_hdr)

        info_form = self._make_form()
        dt_str = meta.get("datetime", "")[:16].replace("T", " ")
        info_form.addRow(i18n.tr("save.backup_date_label") + ":", QLabel(dt_str))
        slots_str = ", ".join(str(s) for s in meta.get("slots", []))
        info_form.addRow(i18n.tr("save.backup_slots_label") + ":", QLabel(slots_str))
        files_str = str(len(meta.get("files", [])))
        info_form.addRow(i18n.tr("save.backup_files_label") + ":", QLabel(files_str))
        bk_lay.addLayout(info_form)

        bk_lay.addWidget(_sep_widget())

        edit_form = self._make_form()

        bk_name_edit = QLineEdit()
        bk_name_edit.setPlaceholderText(i18n.tr("save.new_name_placeholder"))
        bk_name_edit.setText(meta.get("name", ""))
        edit_form.addRow(i18n.tr("save.edit_name") + ":", bk_name_edit)

        bk_tags_edit = QLineEdit()
        bk_tags_edit.setText(", ".join(meta.get("tags", [])))
        edit_form.addRow(i18n.tr("save.edit_tags") + ":", bk_tags_edit)

        bk_memo_edit = QPlainTextEdit()
        bk_memo_edit.setPlainText(meta.get("memo", ""))
        bk_memo_edit.setFixedHeight(64)
        edit_form.addRow(i18n.tr("save.edit_memo") + ":", bk_memo_edit)
        bk_lay.addLayout(edit_form)

        btn_row0 = QHBoxLayout()
        btn_row0.addStretch()
        btn_bk_save = QPushButton(i18n.tr("save.save_backup_info"))
        btn_bk_save.clicked.connect(lambda: self._do_save_bk_info(meta["id"]))
        btn_row0.addWidget(btn_bk_save)
        bk_lay.addLayout(btn_row0)

        bk_lay.addStretch()
        tabs.addTab(bk_tab, i18n.tr("save.tab_backup_info"))

        # ── Tab 1: セーブデータ情報 ──────────────────────────────────
        save_tab = QWidget()
        save_lay = QVBoxLayout(save_tab)
        save_lay.setContentsMargins(10, 10, 10, 10)
        save_lay.setSpacing(8)

        note_name_edit: QLineEdit | None = None
        note_memo_edit: QPlainTextEdit | None = None

        if slot is None:
            hint = QLabel(i18n.tr("save.select_slot_hint"))
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            save_lay.addStretch()
            save_lay.addWidget(hint)
            save_lay.addStretch()
        else:
            slot_hdr = QLabel(i18n.tr("save.slot_n").format(n=slot))
            slot_hdr.setObjectName("detailHeader")
            save_lay.addWidget(slot_hdr)

            slot_names = meta.get("slot_names", {})
            sv_name = slot_names.get(str(slot), i18n.tr("save.parse_unknown"))
            # 元のセーブファイルの最終更新日時（copy2 でタイムスタンプ保持）
            try:
                _bp = os.path.join(_effective_backup_dir(), meta["id"])
                _fi = save_reader.read_slot_info(_bp, slot)
                slot_modified = _fi.get("modified", "—")
            except Exception:
                slot_modified = "—"
            slot_info = self._make_form()
            slot_info.addRow(i18n.tr("save.slot_save_name") + ":", QLabel(sv_name))
            slot_info.addRow(i18n.tr("save.slot_modified") + ":", QLabel(slot_modified))
            save_lay.addLayout(slot_info)

            save_lay.addWidget(_sep_widget())

            # slot_note はバックアップメタから（slot_notes.json とは独立）
            slot_note = meta.get("slot_notes", {}).get(str(slot), {})

            note_form = self._make_form()

            note_name_edit = QLineEdit()
            note_name_edit.setPlaceholderText(i18n.tr("save.slot_note_name_ph"))
            note_name_edit.setText(slot_note.get("name", ""))
            note_form.addRow(i18n.tr("save.slot_note_name") + ":", note_name_edit)

            note_memo_edit = QPlainTextEdit()
            note_memo_edit.setPlaceholderText(i18n.tr("save.slot_note_memo_ph"))
            note_memo_edit.setPlainText(slot_note.get("memo", ""))
            note_memo_edit.setFixedHeight(64)
            note_form.addRow(i18n.tr("save.slot_note_memo") + ":", note_memo_edit)
            save_lay.addLayout(note_form)

            btn_row1 = QHBoxLayout()
            btn_row1.addStretch()
            btn_note_save = QPushButton(i18n.tr("save.save_notes"))
            btn_note_save.clicked.connect(lambda: self._do_save_notes(slot))
            btn_row1.addWidget(btn_note_save)
            save_lay.addLayout(btn_row1)

            save_lay.addStretch()

        tabs.addTab(save_tab, i18n.tr("save.tab_save_info"))
        tabs.setCurrentIndex(initial_tab)

        outer_lay.addWidget(tabs)

        # 参照を self に保存（_swap_detail_widget を呼ぶ前に設定）
        self._bk_name_edit = bk_name_edit
        self._bk_tags_edit = bk_tags_edit
        self._bk_memo_edit = bk_memo_edit
        self._note_name_edit = note_name_edit
        self._note_memo_edit = note_memo_edit

        return container

    # ------------------------------------------------------------------
    # チェック済みスロット取得
    # ------------------------------------------------------------------

    def _get_checked_slots(self) -> list[int]:
        slots = []
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                slot_item = self._table.item(row, 1)
                if slot_item is not None:
                    slots.append(slot_item.data(Qt.ItemDataRole.UserRole))
        return slots

    def _get_game_dir(self) -> str | None:
        """ゲームフォルダを検証して返す。問題があれば警告を出して None を返す。"""
        game_dir = cfg.get("save_dir", "").strip()
        if not game_dir:
            QMessageBox.warning(
                self, i18n.tr("common.warning"), i18n.tr("save.error_no_dir")
            )
            return None
        if not os.path.isdir(game_dir):
            QMessageBox.warning(
                self,
                i18n.tr("common.warning"),
                i18n.tr("save.error_dir_not_found").format(path=game_dir),
            )
            return None
        return game_dir

    # ------------------------------------------------------------------
    # バックアップ操作
    # ------------------------------------------------------------------

    def _do_backup_all(self):
        game_dir = self._get_game_dir()
        if game_dir:
            self._run_create_backup(game_dir, slots=None)

    def _do_backup_checked(self):
        game_dir = self._get_game_dir()
        if not game_dir:
            return
        slots = self._get_checked_slots()
        if not slots:
            QMessageBox.information(
                self, i18n.tr("common.warning"), i18n.tr("save.error_no_selection")
            )
            return
        self._run_create_backup(game_dir, slots=slots)

    def _do_backup_selected(self):
        if self._current_slot is None:
            QMessageBox.information(
                self, i18n.tr("common.warning"), i18n.tr("save.error_no_selection")
            )
            return
        game_dir = self._get_game_dir()
        if game_dir:
            self._run_create_backup(game_dir, slots=[self._current_slot])

    def _run_create_backup(self, game_dir: str, slots: list[int] | None):
        # バックアップ名を入力させる
        name, ok = QInputDialog.getText(
            self,
            i18n.tr("save.create_backup"),
            i18n.tr("save.edit_name") + ":",
        )
        if not ok:
            return
        backup_dir = _effective_backup_dir()
        try:
            meta = save_manager.create_backup(
                game_dir, backup_dir, name=name.strip(), slots=slots
            )
            self.status_message.emit(
                i18n.tr("save.status_created").format(name=meta["name"])
            )
            self._refresh(keep_backup_id=meta["id"])
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("common.error"), str(exc))

    # ------------------------------------------------------------------
    # リストア操作
    # ------------------------------------------------------------------

    def _do_restore_selected(self):
        if not self._current_backup_meta:
            return
        if self._current_slot is None:
            QMessageBox.information(
                self, i18n.tr("common.warning"), i18n.tr("save.no_selection")
            )
            return
        source_slot = self._current_slot
        game_dir = self._get_game_dir()
        if not game_dir:
            return

        # ゲーム側のスロット占有状況を取得（0〜9）
        try:
            occupied_slots = set(save_manager.list_slots(game_dir))
        except Exception:
            occupied_slots = set()

        items: list[str] = []
        for n in range(10):
            if n in occupied_slots:
                items.append(i18n.tr("save.restore_target_slot_item").format(n=n))
            else:
                items.append(i18n.tr("save.restore_target_slot_item_empty").format(n=n))

        # 初期選択はソーススロットと同じ番号
        chosen, ok = QInputDialog.getItem(
            self,
            i18n.tr("save.restore_target_title"),
            i18n.tr("save.restore_target_prompt").format(source=source_slot),
            items,
            current=source_slot,
            editable=False,
        )
        if not ok:
            return
        target_slot = items.index(chosen)

        # ターゲットスロットに既存データがあれば上書き確認
        if target_slot in occupied_slots:
            reply = QMessageBox.question(
                self,
                i18n.tr("common.confirm"),
                i18n.tr("save.restore_target_overwrite").format(target=target_slot),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        meta = self._current_backup_meta
        backup_dir = _effective_backup_dir()
        try:
            save_manager.restore_backup_to_slot(
                game_dir, backup_dir, meta["id"], source_slot, target_slot
            )
            self.status_message.emit(
                i18n.tr("save.status_restored").format(name=meta.get("name", ""))
            )
            # 復元後はゲーム側 NAMES.DAT が変化するため整合性チェックを通してから refresh
            self._check_save_name_changes()
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("common.error"), str(exc))

    def _do_restore_checked(self):
        if not self._current_backup_meta:
            return
        slots = self._get_checked_slots()
        if not slots:
            QMessageBox.information(
                self, i18n.tr("common.warning"), i18n.tr("save.error_no_selection")
            )
            return
        self._run_restore(slots=slots)

    def _do_restore_all(self):
        if self._current_backup_meta:
            self._run_restore(slots=None)

    def _run_restore(self, slots: list[int] | None):
        meta = self._current_backup_meta
        if not meta:
            return
        game_dir = self._get_game_dir()
        if not game_dir:
            return
        backup_dir = _effective_backup_dir()

        slots_str = ", ".join(
            str(s) for s in (slots if slots is not None else meta.get("slots", []))
        )
        reply = QMessageBox.question(
            self,
            i18n.tr("common.confirm"),
            i18n.tr("save.confirm_restore").format(
                name=meta.get("name", ""), slots=slots_str
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            save_manager.restore_backup(game_dir, backup_dir, meta["id"], slots=slots)
            self.status_message.emit(
                i18n.tr("save.status_restored").format(name=meta.get("name", ""))
            )
            # ゲーム側 NAMES.DAT が変化するので整合性チェック → ゲームフォルダビューに戻る
            self._check_save_name_changes()
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("common.error"), str(exc))

    # ------------------------------------------------------------------
    # 削除操作
    # ------------------------------------------------------------------

    def _do_delete(self):
        if not self._current_backup_meta:
            return
        meta = self._current_backup_meta
        reply = QMessageBox.question(
            self,
            i18n.tr("common.confirm"),
            i18n.tr("save.confirm_delete").format(name=meta.get("name", "")),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        backup_dir = _effective_backup_dir()
        try:
            save_manager.delete_backup(backup_dir, meta["id"])
            self.status_message.emit(
                i18n.tr("save.status_deleted").format(name=meta.get("name", ""))
            )
            self._current_backup_meta = None
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("common.error"), str(exc))

    # ------------------------------------------------------------------
    # テーブル選択の復元
    # ------------------------------------------------------------------

    def _restore_table_slot(self, slot: int):
        """テーブルを再読み込みした後に指定スロット行を再選択する。"""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == slot:
                self._table.setCurrentCell(row, 2)
                return

    # ------------------------------------------------------------------
    # メモ・情報保存
    # ------------------------------------------------------------------

    def _do_save_notes(self, slot: int):
        name = self._note_name_edit.text() if self._note_name_edit else ""
        memo = self._note_memo_edit.toPlainText() if self._note_memo_edit else ""
        backup_dir = _effective_backup_dir()

        if self._source_type == self._SOURCE_GAME:
            # ゲームフォルダモード: slot_notes.json に保存
            notes = save_manager.load_slot_notes(backup_dir)
            notes[str(slot)] = {"name": name, "memo": memo}
            save_manager.save_slot_notes(backup_dir, notes)
            self.status_message.emit(i18n.tr("save.status_updated"))
            # ラベル列を再描画し、選択スロットに戻る
            self._load_game_slots()
            self._restore_table_slot(slot)
        else:
            # バックアップモード: backup_meta.json の slot_notes に保存（slot_notes.json とは独立）
            meta = self._current_backup_meta
            if not meta:
                return
            try:
                updated_meta = save_manager.update_backup_slot_note(
                    backup_dir, meta["id"], slot, name, memo
                )
            except Exception as exc:
                QMessageBox.critical(self, i18n.tr("common.error"), str(exc))
                return
            self._current_backup_meta = updated_meta
            self.status_message.emit(i18n.tr("save.status_updated"))
            # 左リストのキャッシュ済みメタを最新に差し替える（再選択時に古いデータが使われないよう）
            for lrow in range(self._left_list.count()):
                litem = self._left_list.item(lrow)
                if not litem:
                    continue
                ldata = litem.data(Qt.ItemDataRole.UserRole)
                if (ldata and ldata.get("type") == "backup"
                        and ldata.get("meta", {}).get("id") == meta["id"]):
                    ldata["meta"] = updated_meta
                    litem.setData(Qt.ItemDataRole.UserRole, ldata)
                    break
            # col 3 (ラベル) をメタから更新
            new_label = updated_meta.get("slot_notes", {}).get(str(slot), {}).get("name", "")
            for row in range(self._table.rowCount()):
                it = self._table.item(row, 1)
                if it and it.data(Qt.ItemDataRole.UserRole) == slot:
                    lbl_it = self._table.item(row, 3)
                    if lbl_it:
                        lbl_it.setText(new_label)
                    break
            # セーブデータタブ(1)を表示したまま再描画
            self._clear_edit_refs()
            self._swap_detail_widget(
                self._build_backup_tabbed_widget(updated_meta, slot=slot, initial_tab=1)
            )

    def _do_save_bk_info(self, backup_id: str):
        if not self._bk_name_edit:
            return
        backup_dir = _effective_backup_dir()
        name     = self._bk_name_edit.text().strip()
        tags_raw = self._bk_tags_edit.text() if self._bk_tags_edit else ""
        tags     = [t.strip() for t in tags_raw.split(",") if t.strip()]
        memo     = self._bk_memo_edit.toPlainText() if self._bk_memo_edit else ""
        try:
            meta = save_manager.update_meta(backup_dir, backup_id, name, tags, memo)
            self._current_backup_meta = meta
            self.status_message.emit(i18n.tr("save.status_updated"))
            # 左リストのラベルを更新しつつ、このバックアップの選択を維持する
            self._refresh(keep_backup_id=backup_id)
        except Exception as exc:
            QMessageBox.critical(self, i18n.tr("common.error"), str(exc))

    # ------------------------------------------------------------------
    # ゲーム内セーブ変更検出（QFileSystemWatcher）
    # ------------------------------------------------------------------

    def _find_names_dat_path(self) -> str | None:
        """ゲームフォルダ内の NAMES.DAT (大文字小文字不問) のパスを返す。"""
        game_dir = cfg.get("save_dir", "").strip()
        if not game_dir or not os.path.isdir(game_dir):
            return None
        try:
            for fname in os.listdir(game_dir):
                if fname.upper() == "NAMES.DAT":
                    return os.path.join(game_dir, fname)
        except OSError:
            return None
        return None

    def _rebuild_save_watcher(self):
        """ゲームフォルダ変更時 / 起動時に watcher を張り直す。"""
        # 既存パスを全てクリア
        paths = self._save_watcher.files() + self._save_watcher.directories()
        if paths:
            self._save_watcher.removePaths(paths)
        self._watched_names_path = None

        game_dir = cfg.get("save_dir", "").strip()
        if not game_dir or not os.path.isdir(game_dir):
            return

        # 親フォルダを監視（NAMES.DAT が削除→再作成されるケースのフォールバック）
        self._save_watcher.addPath(game_dir)

        # NAMES.DAT があれば直接監視
        names_path = self._find_names_dat_path()
        if names_path:
            self._save_watcher.addPath(names_path)
            self._watched_names_path = names_path

    def _on_names_dat_changed(self, _path: str):
        """NAMES.DAT 変更を検出 → 200ms debounce 後に整合性チェック。"""
        # 一部 OS では削除→再作成で監視が外れるため、念のため再登録を試みる
        names_path = self._find_names_dat_path()
        if names_path and names_path not in self._save_watcher.files():
            self._save_watcher.addPath(names_path)
            self._watched_names_path = names_path
        self._watcher_debounce.start()

    def _on_save_dir_changed(self, _path: str):
        """ゲームフォルダ内のファイル増減検出 → NAMES.DAT の再監視 + debounce。"""
        names_path = self._find_names_dat_path()
        if names_path and names_path != self._watched_names_path:
            if self._watched_names_path:
                self._save_watcher.removePath(self._watched_names_path)
            self._save_watcher.addPath(names_path)
            self._watched_names_path = names_path
        self._watcher_debounce.start()

    def _check_save_name_changes(self):
        """
        全スロットについて NAMES.DAT の現在値 と slot_notes.game_save_name を比較し、
        - 不一致なら name / memo を初期化して game_save_name を更新（= 新規セーブ扱い）
        - 未記録なら現在値を game_save_name に記録するだけ（= 初回スロット）
        変更があった場合のみ slot_notes.json を書き込み、テーブルを再描画する。
        """
        game_dir = cfg.get("save_dir", "").strip()
        if not game_dir or not os.path.isdir(game_dir):
            return

        backup_dir = _effective_backup_dir()
        try:
            notes = save_manager.load_slot_notes(backup_dir)
        except Exception:
            return

        dirty = False
        slots_initialized: list[int] = []

        for slot in save_manager.list_slots(game_dir):
            current_name = save_reader.read_save_name(game_dir, slot)
            if current_name is None:
                continue
            s_key = str(slot)
            entry = notes.get(s_key, {})
            prev_name = entry.get("game_save_name")

            if prev_name is None:
                # 初回スロット: 記録のみ
                entry = dict(entry)
                entry["game_save_name"] = current_name
                notes[s_key] = entry
                dirty = True
            elif prev_name != current_name:
                # 名称変更検出: ラベル/メモを初期化、game_save_name を更新
                notes[s_key] = {"game_save_name": current_name}
                slots_initialized.append(slot)
                dirty = True

        if dirty:
            try:
                save_manager.save_slot_notes(backup_dir, notes)
            except Exception:
                return
            # ゲームフォルダ表示中ならテーブルを再描画
            if self._source_type == self._SOURCE_GAME:
                self._load_game_slots()
                if self._current_slot is not None:
                    self._restore_table_slot(self._current_slot)
            if slots_initialized:
                self.status_message.emit(
                    i18n.tr("save.status_updated")
                )

    # ------------------------------------------------------------------
    # 外部通知
    # ------------------------------------------------------------------

    def on_settings_changed(self):
        """設定変更後に呼ばれる。リストを再読み込みする。"""
        self._rebuild_save_watcher()
        self._check_save_name_changes()
        self._refresh()
