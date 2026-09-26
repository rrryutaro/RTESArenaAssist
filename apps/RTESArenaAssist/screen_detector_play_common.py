from __future__ import annotations
from typing import Optional, Tuple
from screen_detector import is_spell_detail_drawn, _tr, FLAG_STATUS_POPUP_OFFSET, FLAG_EQUIPMENT_OPEN_OFFSET, POPUP_OPEN_OFFSET, _read_u8
INVENTORY_SCREEN_IDS = frozenset({'status_page', 'bonus_screen', 'equipment', 'spellbook', 'spell_detail'})

def is_inventory_screen(screen_id: str | None) -> bool:
    return screen_id in INVENTORY_SCREEN_IDS

def detect_common_play_screen(analyzer, anchor: int, img_name: str, foreground_ptr: int | None=None) -> Optional[Tuple[str, str]]:
    img_upper = (img_name or '').upper()
    flag_status = _read_u8(analyzer, anchor + FLAG_STATUS_POPUP_OFFSET)
    flag_equipment = _read_u8(analyzer, anchor + FLAG_EQUIPMENT_OPEN_OFFSET)
    popup_open = _read_u8(analyzer, anchor + POPUP_OPEN_OFFSET)
    if flag_status == 1:
        if img_upper == 'PAGE2.IMG':
            return ('status_page', _tr('status_page'))
        if img_upper == 'CHARSTAT.IMG':
            return ('bonus_screen', _tr('bonus_screen'))
        if flag_equipment == 1:
            return ('equipment', _tr('equipment'))
        drawn_detail = is_spell_detail_drawn(analyzer, anchor)
        if drawn_detail is None:
            raise OSError('screen row unreadable')
        if drawn_detail:
            return ('spell_detail', _tr('spell_detail'))
        return ('spellbook', _tr('spellbook'))
    if img_upper == 'LOGBOOK.IMG':
        from journal_reader import is_journal_drawn
        if is_journal_drawn(analyzer, anchor):
            return ('logbook', _tr('logbook'))
    if popup_open == 1:
        if img_upper in ('AUTOMAP.IMG', 'POINTER.IMG'):
            from template_parser import status_popup_foreground
            from active_template_reader import is_dialog_text_pointer
            if not status_popup_foreground(analyzer, anchor) and (not is_dialog_text_pointer(foreground_ptr)):
                return ('automap', _tr('automap'))
    return None
