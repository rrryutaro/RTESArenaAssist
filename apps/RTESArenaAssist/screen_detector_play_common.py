from __future__ import annotations
from typing import Optional, Tuple
from screen_detector import is_spell_detail_drawn, _tr, FLAG_STATUS_POPUP_OFFSET, FLAG_EQUIPMENT_OPEN_OFFSET, LOGBOOK_FG_WORD_OFFSET, LOGBOOK_FG_WORD_VALUE, POPUP_OPEN_OFFSET, _read_u8, _read_u16_le
INVENTORY_SCREEN_IMGS = ('MRSHIRT.IMG', 'EQUIP.IMG', 'MPANTS.IMG', 'PAGE2.IMG', 'CHARSTAT.IMG')

def is_inventory_screen_img(img_name: str) -> bool:
    return (img_name or '').upper() in INVENTORY_SCREEN_IMGS

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
        drawn_detail = is_spell_detail_drawn(analyzer, anchor)
        if drawn_detail is None:
            raise OSError('screen row unreadable')
        if drawn_detail:
            return ('spell_detail', _tr('spell_detail'))
        return ('spellbook', _tr('spellbook'))
    if popup_open == 1:
        if img_upper == 'LOGBOOK.IMG':
            return ('logbook', _tr('logbook'))
        if img_upper in ('AUTOMAP.IMG', 'POINTER.IMG'):
            from template_parser import status_popup_foreground
            if not status_popup_foreground(analyzer, anchor):
                return ('automap', _tr('automap'))
    elif img_upper == 'LOGBOOK.IMG':
        if _read_u16_le(analyzer, anchor + LOGBOOK_FG_WORD_OFFSET) == LOGBOOK_FG_WORD_VALUE:
            return ('logbook', _tr('logbook'))
    return None
