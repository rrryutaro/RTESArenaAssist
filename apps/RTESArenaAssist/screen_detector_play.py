from __future__ import annotations
from typing import Tuple
from screen_detector_play_common import detect_common_play_screen
from screen_detector_play_city import detect_city_play_screen
from screen_detector_play_dungeon import detect_dungeon_play_screen
from system_menu_visual import system_menu_art_visible

def detect_play_screen(analyzer, anchor: int, img_name: str, mif_name: str='', menu_active_was_zero: bool=False, area: str | None=None, foreground_ptr: int | None=None, trigger_display_active: bool=False) -> Tuple[str, str]:
    from active_template_reader import is_death_popup_text_pointer, is_response_buffer_pointer
    common = detect_common_play_screen(analyzer, anchor, img_name, foreground_ptr=foreground_ptr)
    if common is not None:
        return common
    popup_foreground = trigger_display_active or is_response_buffer_pointer(foreground_ptr) or is_death_popup_text_pointer(foreground_ptr)

    def menu_visual() -> bool:
        return system_menu_art_visible(analyzer, anchor)
    if area == 'city':
        return detect_city_play_screen(analyzer, anchor, img_name, menu_active_was_zero=menu_active_was_zero, popup_foreground=popup_foreground, menu_visual=menu_visual)
    return detect_dungeon_play_screen(analyzer, anchor, img_name, menu_active_was_zero=menu_active_was_zero, popup_foreground=popup_foreground, menu_visual=menu_visual)
