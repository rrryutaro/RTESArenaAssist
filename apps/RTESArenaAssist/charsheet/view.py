from __future__ import annotations
import logging
from pathlib import Path
from typing import Callable, Optional
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QFrame, QTextBrowser
import armor_rating
from charsheet import potions
from charsheet import template_engine
from charsheet import values as sheet_values
from charsheet.images import SheetImages, equipment_key
_log = logging.getLogger('RTESArenaAssist')
RENDER_INTERVAL_MS = 250
EQUIPMENT_CHECK_MS = 1000

class CharacterSheetView(QTextBrowser):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._template = ''
        self._base_dir: Optional[Path] = None
        self._values: dict[str, str] = {}
        self._equipment_source: Optional[Callable[[], Optional[list]]] = None
        self._equipment_key: tuple = ()
        self._images = SheetImages()
        self._page_background = ''
        self._pending = False
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._render)
        self._equipment_timer = QTimer(self)
        self._equipment_timer.setInterval(EQUIPMENT_CHECK_MS)
        self._equipment_timer.timeout.connect(self._check_equipment)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_width)

    def set_template(self, template_html: str, base_dir: Optional[str]) -> None:
        self._template = template_html or ''
        self._base_dir = Path(base_dir).resolve() if base_dir else None
        self._request()

    def set_values(self, values: dict[str, str]) -> None:
        self._values = dict(values)
        self._request()

    def set_equipment_source(self, source: Optional[Callable[[], Optional[list]]]) -> None:
        self._equipment_source = source
        self._equipment_key = ()
        self._request()

    def _request(self) -> None:
        if not self._render_timer.isActive():
            self._render_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._equipment_timer.start()
        if self._pending:
            self._request()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._equipment_timer.stop()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_width()

    def _fit_width(self, *_args) -> None:
        overflow = self.document().idealWidth() - self.viewport().width()
        policy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff if 0 < overflow <= self.document().documentMargin() else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        if self.horizontalScrollBarPolicy() != policy:
            self.setHorizontalScrollBarPolicy(policy)

    def _read_equipment(self) -> Optional[list]:
        if self._equipment_source is None:
            return None
        try:
            return self._equipment_source()
        except Exception:
            _log.debug('charsheet equipment read failed', exc_info=True)
            return None

    @staticmethod
    def _equipment_state(equipped: Optional[list]) -> tuple:
        return (equipment_key(equipped), armor_rating.materials_key(equipped), potions.state(equipped))

    def _check_equipment(self) -> None:
        if self._equipment_state(self._read_equipment()) != self._equipment_key:
            self._request()

    def _render(self) -> None:
        if not self.isVisible():
            self._pending = True
            return
        self._pending = False
        equipped = self._read_equipment()
        self._equipment_key = self._equipment_state(equipped)
        self._images.update(self._values, equipped)
        values = sheet_values.with_armor(sheet_values.with_derived(self._values), equipped)
        values.update(potions.sheet_values(equipped))
        html = template_engine.render(self._template, values, sheet_values.labels(), self._images.urls())
        bar = self.verticalScrollBar()
        position = bar.value()
        self.setHtml(html)
        bar.setValue(position)
        self._apply_page_background()
        self._fit_width()

    def _apply_page_background(self) -> None:
        brush = self.document().rootFrame().frameFormat().background()
        color = brush.color().name() if brush.style() != Qt.BrushStyle.NoBrush else ''
        if color != self._page_background:
            self._page_background = color
            self.setStyleSheet(f'QTextBrowser {{ background-color: {color}; }}' if color else '')

    def loadResource(self, resource_type: int, url: QUrl):
        if url.scheme() == 'charsheet':
            return self._images.image(url.path())
        path = self._local_path(url)
        if path is None:
            return None
        if resource_type == int(QTextDocument.ResourceType.ImageResource):
            image = QImage(str(path))
            return image if not image.isNull() else None
        if resource_type == int(QTextDocument.ResourceType.StyleSheetResource):
            try:
                return path.read_text(encoding='utf-8-sig')
            except (OSError, UnicodeDecodeError):
                return None
        return None

    def _local_path(self, url: QUrl) -> Optional[Path]:
        if self._base_dir is None or url.scheme() not in ('', 'file'):
            return None
        raw = url.toLocalFile() if url.scheme() == 'file' else url.path()
        if not raw:
            return None
        try:
            candidate = (self._base_dir / raw).resolve()
        except OSError:
            return None
        if not candidate.is_relative_to(self._base_dir) or not candidate.is_file():
            return None
        return candidate
__all__ = ['CharacterSheetView', 'RENDER_INTERVAL_MS', 'EQUIPMENT_CHECK_MS']
