
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

import i18n_helper as i18n
from attributes_panel import AttributesPanel


class TabStatus(QWidget):
    def __init__(self, panel=None, parent=None):
        super().__init__(parent)
        self._connected: bool = False
        self._display_active: bool = True
        self._panel = panel if panel is not None else AttributesPanel()
        self._build_ui()
        self._refresh_visibility()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._no_conn_lbl = QLabel(i18n.tr("status.no_connection"))
        self._no_conn_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_conn_lbl.setWordWrap(True)
        self._no_conn_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._no_conn_lbl)

        self._attr_slot = QWidget()
        _slot_lay = QVBoxLayout(self._attr_slot)
        _slot_lay.setContentsMargins(0, 0, 0, 0)
        _slot_lay.addWidget(self._panel, 1)
        root.addWidget(self._attr_slot, 1)


    def _refresh_visibility(self) -> None:
        if not self._connected:
            self._no_conn_lbl.setVisible(True)
            self._panel.setVisible(False)
        elif not self._display_active:
            self._no_conn_lbl.setVisible(False)
            self._panel.setVisible(False)
        else:
            self._no_conn_lbl.setVisible(False)
            self._panel.setVisible(True)

    def mount_attributes_panel(self) -> None:
        if self._panel.parent() is not self._attr_slot:
            self._attr_slot.layout().addWidget(self._panel, 1)
        self._refresh_visibility()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if not connected:
            self._panel.clear_memory_target()
        self._refresh_visibility()

    def set_memory_target(self, analyzer, anchor: int) -> None:
        self._connected = True
        self._panel.set_memory_target(analyzer, anchor)
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
