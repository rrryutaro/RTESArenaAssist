from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy


class ShopItemRow(QFrame):

    def __init__(self, en: str, ja: str, price_display: str,
                 extras: list[str] | None = None, parent=None,
                 show_price: bool = True, unidentified: bool = False):
        super().__init__(parent)
        self.setObjectName("shopItemRow")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(8)

        self._mark_lbl = QLabel("?" if unidentified else "")
        self._mark_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self._mark_lbl.setObjectName("shopItemRowMark")
        self._mark_lbl.setFixedWidth(16)
        if unidentified:
            self._mark_lbl.setToolTip("未鑑定")
        layout.addWidget(self._mark_lbl, 0)

        en_obj = "shopItemRowEnUnid" if unidentified else "shopItemRowEn"
        ja_obj = "shopItemRowJaUnid" if unidentified else "shopItemRowJa"

        self._en_lbl = QLabel(en)
        self._en_lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._en_lbl.setObjectName(en_obj)
        layout.addWidget(self._en_lbl, 2)

        self._ja_lbl = QLabel(ja if ja else "—")
        self._ja_lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._ja_lbl.setObjectName(ja_obj)
        layout.addWidget(self._ja_lbl, 2)

        for value in extras or []:
            if not value:
                continue
            meta_lbl = QLabel(str(value))
            meta_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            meta_lbl.setObjectName("shopItemRowMeta")
            meta_lbl.setMinimumWidth(56)
            layout.addWidget(meta_lbl, 1)

        if show_price:
            price_text = _format_price(price_display)
            self._price_lbl = QLabel(price_text)
            self._price_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._price_lbl.setObjectName("shopItemRowPrice")
            self._price_lbl.setMinimumWidth(60)
            layout.addWidget(self._price_lbl, 1)

        self.setStyleSheet(
            "QFrame#shopItemRow {"
            "  background: #1c2e3f;"
            "  border: 1px solid #2a4258;"
            "  border-radius: 4px;"
            "}"
            "QFrame#shopItemRow QLabel#shopItemRowEn {"
            "  color: #c9d1e0;"
            "  background: transparent;"
            "  border: none;"
            "}"
            "QFrame#shopItemRow QLabel#shopItemRowJa {"
            "  color: #a0c4d8;"
            "  background: transparent;"
            "  border: none;"
            "}"
            "QFrame#shopItemRow QLabel#shopItemRowMark {"
            "  color: #45babe;"
            "  background: transparent;"
            "  border: none;"
            "  font-weight: bold;"
            "}"
            "QFrame#shopItemRow QLabel#shopItemRowEnUnid {"
            "  color: #45babe;"
            "  background: transparent;"
            "  border: none;"
            "}"
            "QFrame#shopItemRow QLabel#shopItemRowJaUnid {"
            "  color: #45babe;"
            "  background: transparent;"
            "  border: none;"
            "}"
            "QFrame#shopItemRow QLabel#shopItemRowMeta {"
            "  color: #78a8ba;"
            "  background: transparent;"
            "  border: none;"
            "}"
            "QFrame#shopItemRow QLabel#shopItemRowPrice {"
            "  color: #f0c860;"
            "  background: transparent;"
            "  border: none;"
            "  font-weight: bold;"
            "}"
        )


def _format_price(price_display: str) -> str:
    if not price_display:
        return ""
    text = str(price_display).strip()
    if not text:
        return ""
    return text if any(ch.isalpha() for ch in text) else f"{text} gp"
