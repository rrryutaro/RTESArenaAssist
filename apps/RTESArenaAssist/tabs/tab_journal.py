from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QSizePolicy, QVBoxLayout, QWidget, QScrollArea
import i18n_helper as i18n
from tts_read_aloud import attach_read_aloud

class JournalEntryWidget(QGroupBox):

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        self._body_lbl = QLabel('—')
        self._body_lbl.setObjectName('valueLabel')
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        attach_read_aloud(self._body_lbl, self._body_lbl.text)
        layout.addWidget(self._body_lbl)

    def set_entry(self, date_ja: str, body_ja: str) -> None:
        nd = i18n.tr('translate.not_in_dict')
        title = date_ja or '—'
        self.setTitle(title)
        self._body_lbl.setText(body_ja or nd)

class TabJournal(QWidget):

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        self._entry_widgets: list[JournalEntryWidget] = []
        self._display_active: bool = True
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
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
        if not getattr(self, '_display_active', True):
            return
        while len(self._entry_widgets) < len(entries):
            w = JournalEntryWidget()
            self._entry_widgets.append(w)
            self._inner_layout.addWidget(w)
        for i, w in enumerate(self._entry_widgets):
            if i < len(entries):
                w.show()
                e = entries[i]
                w.set_entry(e.get('date_ja', '') or '', e.get('body_ja', '') or '')
            else:
                w.hide()

    def set_display_active(self, active: bool) -> None:
        self._display_active = active
        if not active:
            for w in self._entry_widgets:
                w.hide()
