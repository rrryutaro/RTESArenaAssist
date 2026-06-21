from __future__ import annotations
from typing import Tuple

from play_area_classifier import detect_play_area
from screen_detector_play_common import detect_common_play_screen
from screen_detector_play_city import detect_city_play_screen
from screen_detector_play_dungeon import detect_dungeon_play_screen


def detect_play_screen(
    analyzer,
    anchor: int,
    img_name: str,
    mif_name: str = "",
    menu_active_was_zero: bool = False,
    area: str | None = None,
) -> Tuple[str, str]:
    common = detect_common_play_screen(analyzer, anchor, img_name)
    if common is not None:
        return common

    if area is None:
        area = detect_play_area(analyzer, anchor, mif_name)
    if area == "city":
        return detect_city_play_screen(
            analyzer, anchor, img_name,
            menu_active_was_zero=menu_active_was_zero,
        )
    return detect_dungeon_play_screen(
        analyzer, anchor, img_name,
        menu_active_was_zero=menu_active_was_zero,
    )
