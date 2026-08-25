from __future__ import annotations
from typing import Tuple
from screen_detector import _tr, MENU_ACTIVE_OFFSET, CITY_NPC_ACTIVE_OFFSET, is_city_npc_dialog_active, _read_u16_le

def detect_city_play_screen(analyzer, anchor: int, img_name: str, menu_active_was_zero: bool=False, popup_foreground: bool=False) -> Tuple[str, str]:
    img_upper = (img_name or '').upper()
    menu_active = _read_u16_le(analyzer, anchor + MENU_ACTIVE_OFFSET)
    if img_upper == 'OP.IMG' and menu_active == 0 and menu_active_was_zero:
        city_npc_active = _read_u16_le(analyzer, anchor + CITY_NPC_ACTIVE_OFFSET)
        if is_city_npc_dialog_active(city_npc_active):
            return ('npc_dialog', _tr('npc_dialog'))
        if not popup_foreground:
            return ('system_menu', _tr('system_menu'))
    if img_upper == 'LOADSAVE.IMG' and menu_active == 0 and menu_active_was_zero and (not popup_foreground):
        return ('loadsave_in_play', _tr('loadsave_in_play'))
    return ('game_screen', _tr('game_screen'))
