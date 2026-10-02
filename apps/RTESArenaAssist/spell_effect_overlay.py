from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget
from spell_effects import SpellEffectRow
STYLES = ('A', 'B', 'C', 'D', 'E', 'F')
MAX_PAINT_SCALE = 1.1

class SpellEffectOverlay(QWidget):

    def __init__(self, owner=None):
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput
        super().__init__(owner, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._rows: list[SpellEffectRow] = []
        self._style = 'E'
        self._top_offset = 10
        self.hide()

    def render(self, rows: list[SpellEffectRow], *, style: str, rect: tuple[int, int, int, int], top_offset: int=10) -> None:
        left, top, right, bottom = rect
        if not rows or right <= left or bottom <= top:
            self.clear()
            return
        self._rows = rows[:8]
        self._style = style if style in STYLES else 'E'
        self._top_offset = max(10, min(80, top_offset))
        self.setGeometry(left, top, right - left, bottom - top)
        self.show()
        self.raise_()
        self.update()

    def clear(self) -> None:
        self._rows = []
        self.hide()

    def _text(self, painter: QPainter, rect: QRectF, text: str, *, size: int=12, bold: bool=False, color: str='#f3f8f9', align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft) -> None:
        font = QFont('Yu Gothic UI')
        font.setPixelSize(size)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(rect, align, text)

    @staticmethod
    def _card(painter: QPainter, box: QRectF) -> None:
        painter.setPen(QPen(QColor(238, 237, 220, 110), 0.7))
        painter.setBrush(QColor(9, 13, 19, 215))
        painter.drawRoundedRect(box, 6, 6)

    def _icon(self, painter: QPainter, x: float, y: float, size: float, row: SpellEffectRow, *, radial: bool=False) -> None:
        box = QRectF(x, y, size, size)
        painter.setPen(QPen(QColor(row.color), 1.2))
        painter.setBrush(QColor(row.color).darker(250))
        painter.drawEllipse(box)
        self._text(painter, box, row.glyph, size=round(size * 0.55), bold=True, color=row.color, align=Qt.AlignmentFlag.AlignCenter)
        if radial and row.ratio is not None:
            elapsed = 1.0 - row.ratio
            if elapsed > 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(3, 6, 10, 175))
                painter.drawPie(box, 90 * 16, -round(elapsed * 360 * 16))

    @staticmethod
    def _meter(painter: QPainter, x: float, y: float, width: float, row: SpellEffectRow, *, height: float=5) -> None:
        if row.ratio is None:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(53, 62, 72, 225))
        painter.drawRoundedRect(QRectF(x, y, width, height), 2, 2)
        painter.setBrush(QColor(row.color))
        painter.drawRoundedRect(QRectF(x, y, max(0.0, width * row.ratio), height), 2, 2)

    def paintEvent(self, _event) -> None:
        if not self._rows or self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 640, self.height() / 400, MAX_PAINT_SCALE)
        painter.scale(scale, scale)
        style = self._style
        y_base = self._top_offset
        for index, row in enumerate(self._rows):
            if style == 'D':
                x = 12 + index % 4 * 52
                y = y_base + index // 4 * 66
                self._card(painter, QRectF(x, y, 48, 61))
                self._icon(painter, x + 6, y + 3, 36, row, radial=True)
                self._text(painter, QRectF(x + 2, y + 40, 44, 18), row.value, size=10, color=row.color, align=Qt.AlignmentFlag.AlignCenter)
                continue
            if style == 'F':
                x = 12 + index % 2 * 104
                y = y_base + index // 2 * 38
                self._card(painter, QRectF(x, y, 100, 34))
                self._icon(painter, x + 4, y + 4, 25, row)
                self._text(painter, QRectF(x + 32, y + 2, 65, 30), row.value, size=11, bold=True, color=row.color)
                continue
            height = {'A': 31, 'B': 39, 'C': 36, 'E': 38}[style]
            y = y_base + index * (height + 3)
            width = {'A': 208, 'B': 216, 'C': 170, 'E': 218}[style]
            self._card(painter, QRectF(12, y, width, height))
            if style == 'A':
                self._text(painter, QRectF(22, y + 2, 117, 27), row.name)
                self._text(painter, QRectF(139, y + 2, 73, 27), row.value, size=11, bold=True, color=row.color, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            elif style == 'B':
                self._text(painter, QRectF(22, y + 3, 116, 22), row.name)
                self._text(painter, QRectF(140, y + 3, 78, 22), row.value, size=10, color=row.color, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._meter(painter, 22, y + 29, 194, row, height=5)
            elif style == 'C':
                self._icon(painter, 18, y + 4, 28, row)
                self._text(painter, QRectF(51, y + 2, 127, 17), row.value, size=10, color=row.color)
                self._meter(painter, 51, y + 24, 120, row, height=6)
            else:
                self._icon(painter, 18, y + 5, 28, row)
                self._text(painter, QRectF(53, y + 2, 102, 25), row.name, size=11, bold=True)
                self._text(painter, QRectF(152, y + 2, 74, 25), row.value, size=10, bold=True, color=row.color, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._meter(painter, 53, y + 30, 166, row, height=4)
        painter.end()
__all__ = ['SpellEffectOverlay', 'STYLES']
