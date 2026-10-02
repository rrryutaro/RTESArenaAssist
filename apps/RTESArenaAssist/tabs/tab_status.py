from __future__ import annotations
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget
import assist_settings as settings
import i18n_helper as i18n
from charsheet import catalog as sheet_catalog
from charsheet.status_display import StatusDisplay
_SETTING_KEY = 'charsheet_template'

class TabStatus(QWidget):

    def __init__(self, display=None, parent=None):
        super().__init__(parent)
        self._connected: bool = False
        self._display_active: bool = True
        self._display = display if display is not None else StatusDisplay()
        self._panel = self._display.panel()
        self._build_ui()
        self._populate_views(str(settings.get(_SETTING_KEY, '') or ''))
        self._refresh_visibility()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(QLabel(i18n.tr('status.view.label')))
        self._view_combo = QComboBox()
        self._view_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._view_combo.currentIndexChanged.connect(self._on_view_changed)
        header.addWidget(self._view_combo)
        header.addStretch(1)
        self._folder_btn = QPushButton(i18n.tr('status.view.open_folder'))
        self._folder_btn.setToolTip(i18n.tr('status.view.open_folder_tip'))
        self._folder_btn.clicked.connect(self._open_folder)
        header.addWidget(self._folder_btn)
        self._reload_btn = QPushButton(i18n.tr('status.view.reload'))
        self._reload_btn.setToolTip(i18n.tr('status.view.reload_tip'))
        self._reload_btn.clicked.connect(self._reload_views)
        header.addWidget(self._reload_btn)
        root.addLayout(header)
        self._no_conn_lbl = QLabel(i18n.tr('status.no_connection'))
        self._no_conn_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_conn_lbl.setWordWrap(True)
        self._no_conn_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._no_conn_lbl)
        self._attr_slot = QWidget()
        _slot_lay = QVBoxLayout(self._attr_slot)
        _slot_lay.setContentsMargins(0, 0, 0, 0)
        _slot_lay.addWidget(self._display, 1)
        root.addWidget(self._attr_slot, 1)

    def _refresh_visibility(self) -> None:
        self._no_conn_lbl.setVisible(not self._connected)
        self._display.set_showing(self._connected and self._display_active)

    def _populate_views(self, selected_id: str) -> None:
        self._view_combo.blockSignals(True)
        self._view_combo.clear()
        self._view_combo.addItem(i18n.tr('status.view.standard'), '')
        for entry in sheet_catalog.all_templates():
            self._view_combo.addItem(entry.name, entry.id)
        index = self._view_combo.findData(selected_id)
        self._view_combo.setCurrentIndex(index if index >= 0 else 0)
        self._view_combo.blockSignals(False)
        self._apply_view(self._view_combo.currentData() or '')

    def _on_view_changed(self, _index: int) -> None:
        template_id = self._view_combo.currentData() or ''
        settings.set_val(_SETTING_KEY, template_id)
        self._apply_view(template_id)

    def _apply_view(self, template_id: str) -> None:
        self._display.select(template_id)
        self._refresh_visibility()

    def _reload_views(self) -> None:
        self._populate_views(self._view_combo.currentData() or '')

    def _open_folder(self) -> None:
        folder = sheet_catalog.ensure_user_dir()
        if folder is None:
            return
        self._reload_views()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def mount_status_display(self) -> None:
        if self._display.parent() is not self._attr_slot:
            self._attr_slot.layout().addWidget(self._display, 1)
        self._refresh_visibility()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if not connected:
            self._panel.clear_memory_target()
            self._display.set_equipment_source(None)
        self._refresh_visibility()

    def set_memory_target(self, analyzer, anchor: int) -> None:
        self._connected = True
        self._panel.set_memory_target(analyzer, anchor)
        from inventory_reader import read_equipment_items_with_status

        def read_sheet_inventory():
            ok, items = read_equipment_items_with_status(analyzer, anchor)
            return items if ok else None
        self._display.set_equipment_source(read_sheet_inventory)
        self._refresh_visibility()

    def clear_memory_target(self) -> None:
        self._panel.clear_memory_target()
        self.set_connected(False)

    def set_chargen_mode(self, mode: bool) -> None:
        self._panel.set_chargen_mode(mode)

    def set_is_bonus_screen(self, mode: bool) -> None:
        self._panel.set_is_bonus_screen(mode)

    def set_race_class(self, race: str | None, cls: str | None) -> None:
        self._panel.set_race_class(race, cls)

    def set_freeze_updates(self, freeze: bool) -> None:
        self._panel.set_freeze_updates(freeze)

    def set_display_active(self, active: bool) -> None:
        if self._display_active == active:
            return
        self._display_active = active
        self._panel.set_display_active(active)
        self._refresh_visibility()

    def apply_cheat_settings(self) -> None:
        self._panel.apply_cheat_settings()

    def health_observer(self):
        return self._panel.health_observer()
