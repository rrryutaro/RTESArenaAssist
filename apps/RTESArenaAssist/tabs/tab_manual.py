"""
tab_manual.py — マニュアルビューアタブ
"""

import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSizePolicy, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

import i18n_helper as i18n

_MODE_SIMPLE = "simple"
_MODE_FULL = "full"

# 公開版は manual を _internal に置かず exe 内 seed から読む。resource 相対の
# "manual/<mode>/<lang>" を app_resources で解決し、表示時に実パスへ（seed 時のみ一時抽出）。


def _manual_subdir(mode: str) -> str:
    """resource 相対の manual サブフォルダ "manual/<mode>/<lang>" を返す（seed/disk 共通）。"""
    import app_resources
    lang = i18n.current_lang()
    rel = f"manual/{mode}/{lang}"
    if app_resources.is_dir(rel) and any(
            f.endswith(".html") for f in app_resources.listdir(rel)):
        return rel
    # full モードで当該言語がない場合は en/ にフォールバック
    if mode == _MODE_FULL:
        en_rel = f"manual/{mode}/en"
        if app_resources.is_dir(en_rel):
            return en_rel
    # simple フォールバック
    return f"manual/{mode}/ja"


def _list_docs(mode: str) -> list[tuple[str, str]]:
    """Return [(stem, resource_rel), ...] sorted by filename."""
    import app_resources
    d = _manual_subdir(mode)
    return sorted(
        (os.path.splitext(f)[0], f"{d}/{f}")
        for f in app_resources.listdir(d)
        if f.lower().endswith(".html")
    )


def _doc_label(stem: str, mode: str) -> str:
    key = f"manual.doc.{mode}.{stem}"
    label = i18n.tr(key)
    if label == key:
        # simple モードの旧キーへフォールバック
        key2 = f"manual.doc.{stem}"
        label2 = i18n.tr(key2)
        return stem if label2 == key2 else label2
    return label


class TabManual(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode: str = _MODE_SIMPLE
        self._docs: list[tuple[str, str]] = []
        self._matches: list[int] = []
        self._match_idx: int = 0
        self._build_ui()
        self._load_docs()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── ツールバー（モード切替 + 検索）──
        toolbar = QWidget()
        toolbar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.setSpacing(4)

        # 簡易 / 詳細 トグルボタン
        self._btn_simple = QPushButton(i18n.tr("manual.mode.simple"))
        self._btn_full = QPushButton(i18n.tr("manual.mode.full"))
        for btn in (self._btn_simple, self._btn_full):
            btn.setCheckable(True)
            btn.setFixedWidth(56)
        self._btn_simple.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._btn_simple)
        self._mode_group.addButton(self._btn_full)
        self._btn_simple.clicked.connect(lambda: self._switch_mode(_MODE_SIMPLE))
        self._btn_full.clicked.connect(lambda: self._switch_mode(_MODE_FULL))

        # 検索バー
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(i18n.tr("manual.search_placeholder"))
        self._search_edit.setMaximumWidth(180)
        self._search_edit.returnPressed.connect(self._search)
        self._prev_btn = QPushButton(i18n.tr("manual.prev"))
        self._next_btn = QPushButton(i18n.tr("manual.next"))
        self._prev_btn.setFixedWidth(60)
        self._next_btn.setFixedWidth(60)
        self._prev_btn.clicked.connect(self._prev_match)
        self._next_btn.clicked.connect(self._next_match)
        self._match_lbl = QLabel("")
        self._match_lbl.setMinimumWidth(56)
        self._match_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        toolbar_row.addWidget(self._btn_simple)
        toolbar_row.addWidget(self._btn_full)
        toolbar_row.addSpacing(8)
        toolbar_row.addWidget(self._search_edit)
        toolbar_row.addWidget(self._prev_btn)
        toolbar_row.addWidget(self._next_btn)
        toolbar_row.addWidget(self._match_lbl)
        toolbar_row.addStretch()
        root.addWidget(toolbar)

        # ── Splitter: left nav | right browser ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._nav = QListWidget()
        self._nav.setObjectName("manualNav")
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setWordWrap(True)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        splitter.addWidget(self._nav)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        splitter.addWidget(self._browser)

        splitter.setSizes([140, 360])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._prev_btn.setEnabled(False)
        self._next_btn.setEnabled(False)

    def _switch_mode(self, mode: str):
        if self._mode == mode:
            return
        self._mode = mode
        current_row = self._nav.currentRow()
        self._load_docs()
        # 同じ位置を選択し直す（章が異なる場合は先頭）
        if current_row < self._nav.count():
            self._nav.setCurrentRow(current_row)

    def _load_docs(self):
        self._docs = _list_docs(self._mode)
        self._nav.clear()
        if not self._docs:
            self._browser.setPlainText(i18n.tr("manual.no_manual"))
            return
        for stem, _ in self._docs:
            self._nav.addItem(QListWidgetItem(_doc_label(stem, self._mode)))
        self._nav.setCurrentRow(0)

    def _on_nav_changed(self, row: int):
        if row < 0 or row >= len(self._docs):
            return
        _, rel = self._docs[row]
        import app_resources
        self._browser.setSource(QUrl.fromLocalFile(app_resources.resource_fs_path(rel)))
        self._matches = []
        self._match_idx = 0
        self._update_match_label()

    def _search(self):
        keyword = self._search_edit.text().strip()
        if not keyword:
            return
        doc = self._browser.document()
        cursor = doc.find(keyword)
        positions = []
        while not cursor.isNull():
            positions.append(cursor.position())
            cursor = doc.find(keyword, cursor)
        self._matches = positions
        self._match_idx = 0
        if positions:
            self._go_to_match(0)
        self._update_match_label()
        self._prev_btn.setEnabled(len(positions) > 1)
        self._next_btn.setEnabled(len(positions) > 1)

    def _prev_match(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx - 1) % len(self._matches)
        self._go_to_match(self._match_idx)
        self._update_match_label()

    def _next_match(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx + 1) % len(self._matches)
        self._go_to_match(self._match_idx)
        self._update_match_label()

    def _go_to_match(self, idx: int):
        from PySide6.QtGui import QTextCursor
        doc = self._browser.document()
        cursor = QTextCursor(doc)
        cursor.setPosition(self._matches[idx])
        self._browser.setTextCursor(cursor)
        self._browser.ensureCursorVisible()

    def _update_match_label(self):
        if not self._matches:
            kw = self._search_edit.text().strip()
            self._match_lbl.setText(i18n.tr("manual.no_match") if kw else "")
        else:
            self._match_lbl.setText(
                i18n.tr("manual.match_count",
                        current=self._match_idx + 1,
                        total=len(self._matches))
            )
