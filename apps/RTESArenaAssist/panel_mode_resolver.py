from __future__ import annotations
from typing import Optional
MODE_TRANSLATE = 'translate'
MODE_FALLBACK_MAP = 'fallback_map'
MODE_FALLBACK_STATUS = 'fallback_status'
FOREGROUND_MODES = frozenset({'item_pickup', 'shop_buy', 'facility_list', 'equipment', 'spellbook', 'spell_detail', 'place_list', 'travel_table', 'journal', 'load_screen', 'choose_attributes', 'class_list', 'race_list', 'appearance_faces', 'map_screen'})
_TRANSLATE_FAMILY = frozenset({MODE_TRANSLATE, MODE_FALLBACK_MAP, MODE_FALLBACK_STATUS})
OWNER_BOUND_MODES: dict[str, str] = {'load_screen': 'load_screen'}
SCREEN_STATE_OWNERS: frozenset = frozenset(OWNER_BOUND_MODES.values())

def is_screen_state_owner(owner: Optional[str]) -> bool:
    return (owner or '') in SCREEN_STATE_OWNERS

def required_owner_for_mode(mode: Optional[str]) -> Optional[str]:
    return OWNER_BOUND_MODES.get(mode or '')

def panel_is_effective(*, panel_present: bool, emulate_panel_hidden: bool) -> bool:
    return bool(panel_present) and (not bool(emulate_panel_hidden))
_FALLBACK_SETTING_TO_MODE = {'map': MODE_FALLBACK_MAP, 'status': MODE_FALLBACK_STATUS}

def resolve_flush_mode(*, winner_mode: Optional[str], top_level: str, emulate: bool, winner_has_content: bool, winner_is_tab_owner: bool, fallback_setting: str, current_owner: str, panel_active: Optional[bool]=None) -> str:
    _required_owner = required_owner_for_mode(winner_mode)
    if _required_owner is not None and _required_owner != (current_owner or ''):
        winner_mode = None
    if winner_mode in FOREGROUND_MODES:
        return winner_mode
    if top_level != 'normal-play':
        return MODE_TRANSLATE
    if winner_is_tab_owner and (not bool(panel_active)):
        return MODE_TRANSLATE
    if emulate and winner_has_content:
        return MODE_TRANSLATE
    return _FALLBACK_SETTING_TO_MODE.get(fallback_setting, MODE_TRANSLATE)
__all__ = ['resolve_flush_mode', 'required_owner_for_mode', 'is_screen_state_owner', 'FOREGROUND_MODES', 'OWNER_BOUND_MODES', 'SCREEN_STATE_OWNERS', 'MODE_TRANSLATE', 'MODE_FALLBACK_MAP', 'MODE_FALLBACK_STATUS']
