from __future__ import annotations
from typing import Optional, Tuple
from screen_detector import _tr, FLAG_STATUS_POPUP_OFFSET, FLAG_EQUIPMENT_OPEN_OFFSET, POPUP_OPEN_OFFSET, _read_u8

def detect_common_play_screen(analyzer, anchor: int, img_name: str) -> Optional[Tuple[str, str]]:
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
        return ('spellbook', _tr('spellbook'))
    if popup_open == 1:
        if img_upper == 'LOGBOOK.IMG':
            return ('logbook', _tr('logbook'))
        if img_upper in ('AUTOMAP.IMG', 'POINTER.IMG'):
            return ('automap', _tr('automap'))
    return None
