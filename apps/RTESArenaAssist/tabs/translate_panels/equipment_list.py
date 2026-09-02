from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
import assist_settings as settings
import i18n_helper as i18n
_COL_YELLOW = QColor('#EBC734')
_COL_TAN = QColor('#D38E00')
_COL_RED = QColor('#C72000')
_COL_CYAN = QColor('#45BABE')
_COL_BRIGHT_CYAN = QColor('#8AFFFF')
_COL_DIM = QColor('#6a8a9a')
CATEGORY_LABEL_IDS = {'weapon': 'equipment.category.weapon', 'armor': 'equipment.category.armor', 'shield': 'equipment.category.shield', 'accessory': 'equipment.category.accessory', 'spellcasting': 'equipment.category.spellcasting', 'potion': 'equipment.category.potion'}

def category_label(item_type: str) -> str:
    key = CATEGORY_LABEL_IDS.get(item_type or '')
    return i18n.tr(key) if key else ''

def row_matches(item_data: dict, *, text: str='', slot: str='', category: str='') -> bool:
    if category and (item_data.get('item_type') or '') != category:
        return False
    if slot and (item_data.get('slot_label') or '') != slot:
        return False
    if not text:
        return True
    needle = text.strip().casefold()
    if not needle:
        return True
    haystack = ' '.join((str(item_data.get(k) or '') for k in ('en', 'ja', 'slot_label')))
    return needle in haystack.casefold()

def category_keys(items: list) -> list:
    present = {i.get('item_type') or '' for i in items or ()}
    return [k for k in CATEGORY_LABEL_IDS if k in present]

def slot_labels(items: list, *, category: str='') -> list:
    seen: list = []
    for item_data in items or ():
        if category and (item_data.get('item_type') or '') != category:
            continue
        label = (item_data.get('slot_label') or '').strip()
        if label and label not in seen:
            seen.append(label)
    return seen

def _uses_text(item_data: dict) -> str:
    uses = item_data.get('uses')
    if uses is None:
        return ''
    try:
        return str(int(uses))
    except (TypeError, ValueError):
        return ''

def render_equipment_list(table: QTableWidget, items: list, *, text_filter: str='', slot_filter: str='', category_filter: str='') -> None:
    table.setRowCount(0)
    mark_equipped = settings.get('equipment_mark_equipped', 'Ｅ')
    mark_equippable = settings.get('equipment_mark_equippable', '')
    mark_unequippable = settings.get('equipment_mark_unequippable', '✕')
    for item_data in items:
        if not row_matches(item_data, text=text_filter, slot=slot_filter, category=category_filter):
            continue
        equipped = item_data.get('equipped', False)
        is_unidentified = item_data.get('is_unidentified', False)
        can_equip = item_data.get('can_equip', None)
        en = item_data.get('en', '')
        ja = item_data.get('ja', '') or '—'
        slot_label = item_data.get('slot_label', '') or '—'
        weight = item_data.get('weight', '') or '—'
        condition = item_data.get('condition', '') or '—'
        uses = _uses_text(item_data) or '—'
        effect = item_data.get('effect', '') or '—'
        if weight == 'n/a':
            weight = '—'
        if is_unidentified and equipped:
            name_color = _COL_BRIGHT_CYAN
        elif is_unidentified:
            name_color = _COL_CYAN
        elif can_equip is False:
            name_color = _COL_RED
        elif equipped:
            name_color = _COL_YELLOW
        else:
            name_color = _COL_TAN
        if equipped:
            mark = mark_equipped
        elif can_equip is False:
            mark = mark_unequippable
        else:
            mark = mark_equippable
        row = table.rowCount()
        table.insertRow(row)
        cells = [(mark, name_color, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), ('?' if is_unidentified else '', _COL_CYAN if is_unidentified else _COL_DIM, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), (slot_label, _COL_DIM, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), (en, name_color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), (ja, name_color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), (weight, _COL_DIM, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), (condition, _COL_DIM, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), (uses, _COL_DIM, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), (effect, _COL_DIM, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)]
        for col, (text, color, align) in enumerate(cells):
            cell = QTableWidgetItem(text)
            cell.setTextAlignment(align)
            cell.setForeground(color)
            table.setItem(row, col, cell)
    for col_idx in (2, 5, 6, 7, 8):
        table.resizeColumnToContents(col_idx)
