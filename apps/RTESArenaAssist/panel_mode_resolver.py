from __future__ import annotations
from typing import Optional
MODE_TRANSLATE = 'translate'
MODE_FALLBACK_MAP = 'fallback_map'
MODE_FALLBACK_STATUS = 'fallback_status'
FOREGROUND_MODES = frozenset({'item_pickup', 'shop_buy', 'facility_list', 'equipment', 'spell_detail', 'place_list', 'travel_table', 'journal', 'load_screen', 'choose_attributes', 'class_list', 'race_list', 'appearance_faces'})
_TRANSLATE_FAMILY = frozenset({MODE_TRANSLATE, MODE_FALLBACK_MAP, MODE_FALLBACK_STATUS})
_FALLBACK_SETTING_TO_MODE = {'map': MODE_FALLBACK_MAP, 'status': MODE_FALLBACK_STATUS}

def resolve_flush_mode(*, winner_mode: Optional[str], top_level: str, emulate: bool, winner_has_content: bool, winner_is_tab_owner: bool, fallback_setting: str) -> str:
    if winner_mode in FOREGROUND_MODES:
        return winner_mode
    if top_level != 'normal-play':
        return MODE_TRANSLATE
    if winner_is_tab_owner:
        return MODE_TRANSLATE
    if emulate and winner_has_content:
        return MODE_TRANSLATE
    return _FALLBACK_SETTING_TO_MODE.get(fallback_setting, MODE_TRANSLATE)
__all__ = ['resolve_flush_mode', 'FOREGROUND_MODES', 'MODE_TRANSLATE', 'MODE_FALLBACK_MAP', 'MODE_FALLBACK_STATUS']
