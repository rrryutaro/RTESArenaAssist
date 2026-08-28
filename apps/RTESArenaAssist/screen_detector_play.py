from __future__ import annotations
from typing import Tuple
from play_area_classifier import detect_play_area
from screen_detector_play_common import detect_common_play_screen
from screen_detector_play_city import detect_city_play_screen
from screen_detector_play_dungeon import detect_dungeon_play_screen

def detect_play_screen(analyzer, anchor: int, img_name: str, mif_name: str='', menu_active_was_zero: bool=False, area: str | None=None, foreground_ptr: int | None=None, trigger_display_active: bool=False) -> Tuple[str, str]:
    from active_template_reader import is_death_popup_text_pointer, is_response_buffer_pointer
    common = detect_common_play_screen(analyzer, anchor, img_name)
    if common is not None:
        return common
    popup_foreground = trigger_display_active or is_response_buffer_pointer(foreground_ptr) or is_death_popup_text_pointer(foreground_ptr)
    if area is None:
        area = detect_play_area(analyzer, anchor, mif_name)
    if area == 'city':
        return detect_city_play_screen(analyzer, anchor, img_name, menu_active_was_zero=menu_active_was_zero, popup_foreground=popup_foreground)
    return detect_dungeon_play_screen(analyzer, anchor, img_name, menu_active_was_zero=menu_active_was_zero, popup_foreground=popup_foreground)
