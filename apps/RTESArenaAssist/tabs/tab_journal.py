"""tab_journal.py — ジャーナル (Logbook) 表示タブ。

ゲーム画面で LOGBOOK.IMG (J キー or Logbook ボタン) を開いた時の
ジャーナル本文を、項目ごとに 1 つの GroupBox として表示する。

UI 構造:
  項目 = QGroupBox (タイトル = 日付の和訳)
    └─ クエスト本文 (和訳のみ、原文は表示しない)

複数 entry に拡張可能な構造で、現状は 1 entry のみ表示する。
poll_controller から `update_journal_entries(entries)` を呼ばれて更新。
LOGBOOK.IMG を閉じても直近表示は保持 (= ステータスタブと同じ振る舞い)。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox, QLabel, QSizePolicy, QVBoxLayout, QWidget, QScrollArea,
)

import i18n_helper as i18n
from tts_read_aloud import attach_read_aloud


class JournalEntryWidget(QGroupBox):
    """ジャーナル 1 項目 = GroupBox。タイトル = 日付翻訳、中身 = 本文翻訳。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        self._body_lbl = QLabel("—")
        self._body_lbl.setObjectName("valueLabel")
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # 読み上げ（右クリック）。本文は set_entry で更新されるため遅延取得。
        self._body_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        attach_read_aloud(self._body_lbl, self._body_lbl.text)
        layout.addWidget(self._body_lbl)

    def set_entry(self, date_ja: str, body_ja: str) -> None:
        """日付翻訳をタイトルに、本文翻訳を中身に設定。"""
        nd = i18n.tr("translate.not_in_dict")
        title = date_ja or "—"
        self.setTitle(title)
        self._body_lbl.setText(body_ja or nd)


class TabJournal(QWidget):
    """ジャーナル (Logbook) 専用タブ。

    update_journal_entries(entries) を poll_controller から呼ぶ。
    entries: [{"date_ja": str, "body_ja": str}, ...]
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._entry_widgets: list[JournalEntryWidget] = []
        self._display_active: bool = True
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # スクロール可能な容器 (複数 entry 拡張時に対応)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll_inner = QWidget()
        self._inner_layout = QVBoxLayout(self._scroll_inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(8)
        self._inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._scroll_inner)
        root.addWidget(self._scroll, 1)

    def update_journal_entries(self, entries: list[dict]) -> None:
        """ジャーナル全体を 1 回で更新。entries 数に合わせて GroupBox を増減。

        entries: [{"date_ja": str, "body_ja": str}, ...] (現状 1 件、複数対応の構造)
        """
        # display_active が False のときは更新を無視する (タイトル中 / chargen
        # で前回プレイのジャーナル残置を防ぐため)
        if not getattr(self, "_display_active", True):
            return
        # 必要数まで widget を増やす
        while len(self._entry_widgets) < len(entries):
            w = JournalEntryWidget()
            self._entry_widgets.append(w)
            self._inner_layout.addWidget(w)
        # 余剰 widget は非表示
        for i, w in enumerate(self._entry_widgets):
            if i < len(entries):
                w.show()
                e = entries[i]
                w.set_entry(e.get("date_ja", "") or "",
                            e.get("body_ja", "") or "")
            else:
                w.hide()

    def set_display_active(self, active: bool) -> None:
        """ジャーナル表示の有効/無効を切替える。

        無効時はエントリを全クリアし、後続の update_journal_entries 呼出を
        無視する。タイトル中 / chargen で False、通常プレイで True。
        """
        self._display_active = active
        if not active:
            for w in self._entry_widgets:
                w.hide()
