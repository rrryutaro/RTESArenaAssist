from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

class ItemRow(QFrame):

    def __init__(self, en: str, ja: str, parent=None, *, show_mark: bool=True):
        super().__init__(parent)
        self._taken = False
        self._show_mark = show_mark
        self.setObjectName('itemRow')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(8)
        if show_mark:
            self._mark_lbl = QLabel('•')
            self._mark_lbl.setFixedWidth(14)
            self._mark_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._mark_lbl.setObjectName('itemRowMark')
            layout.addWidget(self._mark_lbl)
        else:
            self._mark_lbl = None
        self._en_lbl = QLabel(en)
        self._en_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._en_lbl.setObjectName('itemRowEn')
        layout.addWidget(self._en_lbl, 1)
        self._ja_lbl = QLabel(ja if ja else '—')
        self._ja_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._ja_lbl.setObjectName('itemRowJa')
        layout.addWidget(self._ja_lbl, 1)
        self._apply_style()

    def set_taken(self, taken: bool) -> None:
        if self._taken == taken:
            return
        self._taken = taken
        if self._mark_lbl is not None:
            self._mark_lbl.setText('✓' if taken else '•')
        self._apply_style()

    def _apply_style(self) -> None:
        if self._taken:
            self.setStyleSheet('QFrame#itemRow {  background: #181826;  border: 1px solid #252535;  border-radius: 4px;}QFrame#itemRow QLabel {  color: #4a4a6a;  background: transparent;  border: none;}')
        else:
            self.setStyleSheet('QFrame#itemRow {  background: #1c2e3f;  border: 1px solid #2a4258;  border-radius: 4px;}QFrame#itemRow QLabel#itemRowMark {  color: #7ab8d4;  background: transparent;  border: none;}QFrame#itemRow QLabel#itemRowEn {  color: #c9d1e0;  background: transparent;  border: none;}QFrame#itemRow QLabel#itemRowJa {  color: #a0c4d8;  background: transparent;  border: none;}')
