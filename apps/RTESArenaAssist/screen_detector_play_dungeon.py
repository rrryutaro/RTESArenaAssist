from __future__ import annotations
from typing import Tuple
from screen_detector import _tr, MENU_ACTIVE_OFFSET, _read_u16_le

def detect_dungeon_play_screen(analyzer, anchor: int, img_name: str, menu_active_was_zero: bool=False, foreground_ptr: int | None=None) -> Tuple[str, str]:
    from active_template_reader import is_message_buffer_pointer
    img_upper = (img_name or '').upper()
    menu_active = _read_u16_le(analyzer, anchor + MENU_ACTIVE_OFFSET)
    if img_upper == 'OP.IMG' and menu_active == 0 and menu_active_was_zero and (not is_message_buffer_pointer(foreground_ptr)):
        return ('system_menu', _tr('system_menu'))
    if img_upper == 'LOADSAVE.IMG' and menu_active == 0 and menu_active_was_zero and (not is_message_buffer_pointer(foreground_ptr)):
        return ('loadsave_in_play', _tr('loadsave_in_play'))
    return ('game_screen', _tr('game_screen'))
