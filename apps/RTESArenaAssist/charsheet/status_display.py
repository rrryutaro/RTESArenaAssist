from __future__ import annotations
from typing import Callable, Optional
from PySide6.QtWidgets import QVBoxLayout, QWidget
from attributes_panel import AttributesPanel
from charsheet import catalog as sheet_catalog
from charsheet.catalog import TemplateEntry
from charsheet.view import CharacterSheetView

class StatusDisplay(QWidget):

    def __init__(self, panel: Optional[AttributesPanel]=None, parent=None) -> None:
        super().__init__(parent)
        self._panel = panel if panel is not None else AttributesPanel()
        self._sheet = CharacterSheetView()
        self._entry: Optional[TemplateEntry] = None
        self._showing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._panel, 1)
        layout.addWidget(self._sheet, 1)
        self._panel.sheetValuesChanged.connect(self._on_sheet_values_changed)
        self._refresh()

    def panel(self) -> AttributesPanel:
        return self._panel

    def sheet(self) -> CharacterSheetView:
        return self._sheet

    def entry(self) -> Optional[TemplateEntry]:
        return self._entry

    def select(self, template_id: str) -> None:
        entry = sheet_catalog.find(template_id) if template_id else None
        text = sheet_catalog.load(entry) if entry is not None else None
        if entry is None or text is None:
            self._entry = None
        else:
            self._entry = entry
            self._sheet.set_template(text, sheet_catalog.base_dir(entry))
            self._sheet.set_values(self._panel.sheet_values())
        self._refresh()

    def set_showing(self, showing: bool) -> None:
        self._showing = showing
        self._refresh()

    def set_equipment_source(self, source: Optional[Callable[[], Optional[list]]]) -> None:
        self._sheet.set_equipment_source(source)

    def _refresh(self) -> None:
        sheet_mode = self._entry is not None
        self._panel.setVisible(self._showing and (not sheet_mode))
        self._sheet.setVisible(self._showing and sheet_mode)

    def _on_sheet_values_changed(self) -> None:
        if self._entry is not None:
            self._sheet.set_values(self._panel.sheet_values())
__all__ = ['StatusDisplay']
