import logging
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QTableWidgetItem, QVBoxLayout, QWidget
import assist_settings as settings
import i18n_helper as i18n
_log = logging.getLogger('RTESArenaAssist')
from attributes_panel import AttributesPanel
from appearance_faces_panel import AppearanceFacesPanel
from tabs.tab_map import TabMap
from tabs.translate_panels.item_row import ItemRow
from tabs.translate_panels.shop_item_row import ShopItemRow
from tabs.translate_panels.equipment_list import render_equipment_list
from tabs.translate_panels.load_screen import render_load_screen_slots
_MODE_TRANSLATE = 'translate'
_MODE_CLASS_LIST = 'class_list'
_MODE_RACE_LIST = 'race_list'
_MODE_CHOOSE_ATTRIBUTES = 'choose_attributes'
_MODE_LOAD_SCREEN = 'load_screen'
_MODE_ITEM_PICKUP = 'item_pickup'
_MODE_EQUIPMENT = 'equipment'
_MODE_SPELL_DETAIL = 'spell_detail'
_MODE_PLACE_LIST = 'place_list'
_MODE_SHOP_BUY = 'shop_buy'
_MODE_FACILITY_LIST = 'facility_list'
_MODE_TRAVEL_TABLE = 'travel_table'
_MODE_JOURNAL = 'journal'
_MODE_APPEARANCE_FACES = 'appearance_faces'
_MODE_FALLBACK_STATUS = 'fallback_status'
_MODE_FALLBACK_MAP = 'fallback_map'

class TabTranslate(QWidget):
    panel_mode_changed = Signal(str)

    def __init__(self, attributes_panel=None, parent=None):
        super().__init__(parent)
        self._panel_mode = _MODE_TRANSLATE
        self._attributes_panel = attributes_panel if attributes_panel is not None else AttributesPanel()
        self._build_ui()
        self.set_connected(False)

    def _build_ui(self):
        from tabs.tab_translate_ui import build_ui
        build_ui(self)

    def set_connected(self, connected: bool) -> None:
        self._no_conn.setVisible(not connected)
        self._conn_widget.setVisible(connected)

    def update_game_state(self, state: dict) -> None:
        return

    def update_translation(self, original: str, translated: str, *, suppress_fallback: bool=False) -> None:
        _prev_orig = getattr(self, '_b267_prev_orig', None)
        _prev_trans = getattr(self, '_b267_prev_trans', None)
        if (original, translated) != (_prev_orig, _prev_trans):
            self._b267_prev_orig = original
            self._b267_prev_trans = translated
            _log.debug('b267 tab_translate.update_translation (panel_mode=%r orig=%r trans=%r)', self._panel_mode, original[:160], translated[:160])
        nd = i18n.tr('translate.no_data')
        not_in = i18n.tr('translate.not_in_dict')
        import reading_highlight as _rh
        self._orig_val.setText(original or nd)
        _rh.set_plain(self._trans_val, translated if translated else not_in)

    def highlight_reading(self, full_text, current_segment, prefetched_segments=None) -> None:
        import reading_highlight as _rh
        _rh.apply_reading(self._trans_val, current_segment, prefetched_segments)
        self._highlight_journal_entries(current_segment, prefetched_segments)

    def _highlight_journal_entries(self, current_segment, prefetched_segments=None) -> None:
        widgets = getattr(self, '_journal_entry_widgets', None) or []
        probe = current_segment
        if probe is None and prefetched_segments:
            probe = prefetched_segments[0]
        matched = False
        for w in widgets:
            if not w.isVisible():
                w.clear_reading_highlight()
                continue
            if not matched and w.contains_reading_probe(probe):
                w.highlight_reading(current_segment, prefetched_segments)
                matched = True
            else:
                w.clear_reading_highlight()

    def fallback_map_tab(self) -> TabMap:
        return self._fallback_map_tab

    def update_fallback_map_state(self, *args, **kwargs) -> None:
        self._fallback_map_tab.update_map_state(*args, **kwargs)

    def poll_fallback_automap_file(self) -> bool:
        return self._fallback_map_tab.poll_automap_file()

    def apply_map_settings(self) -> None:
        self._fallback_map_tab.apply_settings()

    def set_panel_mode(self, mode: str) -> None:
        if mode == self._panel_mode:
            return
        if mode == _MODE_CLASS_LIST:
            self._stack.setCurrentIndex(1)
            self._class_list_panel.reset_selection()
        elif mode == _MODE_CHOOSE_ATTRIBUTES:
            self._stack.setCurrentIndex(2)
        elif mode == _MODE_LOAD_SCREEN:
            self._stack.setCurrentIndex(3)
        elif mode == _MODE_ITEM_PICKUP:
            self._stack.setCurrentIndex(4)
        elif mode == _MODE_EQUIPMENT:
            self._stack.setCurrentIndex(5)
        elif mode == _MODE_SPELL_DETAIL:
            self._stack.setCurrentIndex(6)
        elif mode == _MODE_RACE_LIST:
            self._stack.setCurrentIndex(7)
            self._race_list_panel.reset_selection()
        elif mode == _MODE_PLACE_LIST:
            self._stack.setCurrentIndex(8)
        elif mode == _MODE_SHOP_BUY:
            self._stack.setCurrentIndex(9)
        elif mode == _MODE_FACILITY_LIST:
            self._stack.setCurrentIndex(12)
        elif mode == _MODE_TRAVEL_TABLE:
            self._stack.setCurrentIndex(13)
        elif mode == _MODE_JOURNAL:
            self._stack.setCurrentIndex(14)
        elif mode == _MODE_APPEARANCE_FACES:
            self._stack.setCurrentIndex(10)
        elif mode == _MODE_FALLBACK_STATUS:
            self._stack.setCurrentIndex(2)
        elif mode == _MODE_FALLBACK_MAP:
            self._stack.setCurrentIndex(11)
        else:
            mode = _MODE_TRANSLATE
            self._stack.setCurrentIndex(0)
        self._panel_mode = mode
        self.panel_mode_changed.emit(mode)

    def update_item_pickup_list(self, items: list, remaining: int) -> None:
        layout = self._pickup_rows_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for item_data in items:
            en = item_data.get('en', '')
            ja = item_data.get('ja', '') or '—'
            row = ItemRow(en, ja)
            if item_data.get('taken'):
                row.set_taken(True)
            layout.addWidget(row)
        layout.addStretch(1)
        self._pickup_remaining.setText(f'残り {remaining} 個' if remaining > 0 else '')

    def update_equipment_list(self, items: list) -> None:
        render_equipment_list(self._equip_table, items)

    def update_place_list(self, items: list) -> None:
        layout = self._place_rows_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for item_data in items:
            en = item_data.get('en', '')
            ja = item_data.get('ja', '') or '—'
            layout.addWidget(ItemRow(en, ja, show_mark=False))
        layout.addStretch(1)

    def set_place_list_title(self, title: str) -> None:
        self._place_list_group.setTitle(title)

    @staticmethod
    def _render_price_rows(layout, items: list, *, show_price: bool=True) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for item_data in items:
            en = item_data.get('en', '')
            ja = item_data.get('ja', '') or ''
            price_display = item_data.get('price_display', '')
            extras = []
            hands = item_data.get('hands', '')
            protects = item_data.get('protects_ja', '') or item_data.get('protects', '')
            weight = item_data.get('weight', '')
            if protects:
                extras.append(str(protects))
            elif hands:
                extras.append(str(hands))
            if weight:
                extras.append(str(weight))
            layout.addWidget(ShopItemRow(en, ja, price_display, extras=extras, show_price=show_price, unidentified=bool(item_data.get('is_unidentified', False))))
        layout.addStretch(1)

    def update_shop_buy_list(self, items: list) -> None:
        self._render_price_rows(self._shop_buy_rows_layout, items)

    def update_facility_list(self, items: list) -> None:
        has_hands = any((item.get('hands', '') for item in items))
        has_protects = any((item.get('protects', '') or item.get('protects_ja', '') for item in items))
        has_weight = any((item.get('weight', '') for item in items))
        has_price = any((item.get('price_display', '') for item in items))
        self._facility_header_hands.setText('保護部位' if has_protects else '持ち手')
        self._facility_header_hands.setVisible(has_hands or has_protects)
        self._facility_header_weight.setVisible(has_weight)
        self._facility_header_price.setVisible(has_price)
        self._render_price_rows(self._facility_list_rows_layout, items, show_price=has_price)

    def set_facility_list_title(self, title: str) -> None:
        self._facility_list_group.setTitle(title)

    def update_travel_table(self, rows: list) -> None:
        idx = 0
        for table, n in zip(self._travel_tables, self._travel_group_sizes):
            group = rows[idx:idx + n]
            idx += n
            table.setRowCount(len(group))
            for i, row in enumerate(group):
                if isinstance(row, dict):
                    label = row.get('label', '')
                    en = row.get('en', '')
                    ja = row.get('ja', '')
                else:
                    label, en, ja = row
                table.setItem(i, 0, QTableWidgetItem(label or ''))
                table.setItem(i, 1, QTableWidgetItem(en if en else '—'))
                table.setItem(i, 2, QTableWidgetItem(ja if ja else '—'))
            table.resizeRowsToContents()
            h = sum((table.rowHeight(r) for r in range(table.rowCount())))
            table.setFixedHeight(h + 2)

    def set_travel_table_title(self, title: str) -> None:
        return

    def update_journal_entries(self, entries: list) -> None:
        from tabs.tab_journal import JournalEntryWidget
        widgets = getattr(self, '_journal_entry_widgets', None)
        layout = getattr(self, '_journal_entries_layout', None)
        if widgets is None or layout is None:
            return
        while len(widgets) < len(entries):
            w = JournalEntryWidget()
            widgets.append(w)
            layout.addWidget(w)
        for i, w in enumerate(widgets):
            if i < len(entries):
                w.show()
                e = entries[i]
                w.set_entry(e.get('date_ja', '') or '', e.get('body_ja', '') or '')
            else:
                w.hide()

    def set_shop_buy_title(self, title: str) -> None:
        self._shop_buy_group.setTitle(title)

    def _on_equip_toggle(self, key: str, col_idx: int, checked: bool) -> None:
        self._equip_table.setColumnHidden(col_idx, not checked)
        cols = dict(settings.get('equipment_columns', {}))
        cols[key] = checked
        settings.set_val('equipment_columns', cols)

    def set_equipment_panel_title(self, title: str) -> None:
        self._equip_group.setTitle(title)

    @staticmethod
    def _spell_effect_details_for_display(data: dict) -> list[dict]:
        details = [d for d in data.get('effect_details') or [] if isinstance(d, dict) and d.get('effect_en')]
        if details:
            return details
        effect_en = data.get('effect_en', '')
        if effect_en and effect_en != '(none)':
            return [{'effect_en': effect_en, 'effect_ja': data.get('effect_ja', ''), 'text_en': data.get('text_en', ''), 'text_ja': data.get('text_ja', '')}]
        return []

    @staticmethod
    def _spell_effect_ja_text(text_en: str, text_ja: str) -> str:
        if text_ja:
            return text_ja
        return '(テンプレート未登録)' if text_en else '—'

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

    def _add_spell_effect_card(self, detail: dict) -> None:
        card = QFrame()
        card.setObjectName('spellEffectCard')
        card.setStyleSheet('QFrame#spellEffectCard {  background: #17293a;  border: 1px solid #2a4258;  border-radius: 4px;}')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 7, 8, 8)
        lay.setSpacing(4)
        effect_en = detail.get('effect_en', '') or '—'
        effect_ja = detail.get('effect_ja', '') or '—'
        title_text = f'{effect_en}  {effect_ja}' if effect_en != effect_ja else effect_en
        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet('QLabel { color: #c9d1e0; font-size: 12px; font-weight: bold; }')
        lay.addWidget(title)
        lay.addSpacing(4)
        text_en = detail.get('text_en', '') or ''
        text_ja = detail.get('text_ja', '') or ''
        en_label = QLabel(text_en or '—')
        en_label.setWordWrap(True)
        en_label.setStyleSheet('QLabel { color: #c9d1e0; font-size: 12px; }')
        lay.addWidget(en_label)
        ja_label = QLabel(self._spell_effect_ja_text(text_en, text_ja))
        ja_label.setWordWrap(True)
        ja_label.setStyleSheet('QLabel { color: #a0c4d8; font-size: 11px; }')
        lay.addWidget(ja_label)
        self._sd_effect_cards_layout.addWidget(card)

    def _render_spell_effect_cards(self, details: list[dict]) -> None:
        layout = self._sd_effect_cards_layout
        self._clear_layout(layout)
        if not details:
            none = QLabel('—')
            none.setStyleSheet('QLabel { color: #c9d1e0; font-size: 12px; }')
            layout.addWidget(none)
            layout.addStretch(1)
            return
        for detail in details:
            self._add_spell_effect_card(detail)
        layout.addStretch(1)

    def update_spell_detail(self, data: dict) -> None:
        self._sd_player_name.setText(data.get('player_name', '') or '—')
        gold = data.get('player_gold', 0)
        self._sd_player_balance.setText(str(gold) if gold else '—')
        level = data.get('player_level', 0)
        self._sd_player_level.setText(str(level) if level else '—')
        raw_cost = data.get('cost', 0)
        cast_cost = data.get('casting_cost', raw_cost)
        spell_cost = data.get('spell_cost')
        if spell_cost:
            self._sd_spell_cost.setText(str(spell_cost))
        else:
            self._sd_spell_cost.setText(str(raw_cost * 2) if raw_cost else '—')
        self._sd_name_en.setText(data.get('name', '') or '—')
        self._sd_name_ja.setText(data.get('name_ja', '') or '—')
        elem_en = data.get('element_en', '')
        elem_ja = data.get('element_ja', '')
        if elem_en:
            self._sd_save_vs.setText(f'{elem_en} ({elem_ja})')
        else:
            self._sd_save_vs.setText('—')
        tgt_en = data.get('target_en', '')
        tgt_ja = data.get('target_ja', '')
        if tgt_en:
            self._sd_target.setText(f'{tgt_en} ({tgt_ja})')
        else:
            self._sd_target.setText('—')
        self._sd_cost_lbl.setText(str(cast_cost) if cast_cost else '—')
        self._render_spell_effect_cards(self._spell_effect_details_for_display(data))

    def update_load_screen_slots(self, slots: list) -> None:
        render_load_screen_slots(self._load_table, slots)

    def panel_mode(self) -> str:
        return self._panel_mode

    def select_class_in_list(self, en_name: str) -> None:
        self._class_list_panel.select_class(en_name)

    def set_chargen_active(self, active: bool) -> None:
        self._gs_group.setVisible(not active)

    def appearance_faces_panel(self) -> AppearanceFacesPanel:
        return self._appearance_faces_panel

    def attributes_panel(self) -> AttributesPanel:
        return self._attributes_panel

    def mount_attributes_panel(self) -> None:
        if self._attributes_panel.parent() is not self._attr_slot:
            self._attr_slot.layout().addWidget(self._attributes_panel)
