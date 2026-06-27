from __future__ import annotations
from typing import Optional, Tuple
import i18n_helper as _i18n
FLAG_STATUS_POPUP_OFFSET = 4794
FLAG_EQUIPMENT_OPEN_OFFSET = 4762
FLAG_SPELL_DETAIL_OFFSET = 6890
SPELL_VIEW_OFFSET = 36718
MENU_ACTIVE_OFFSET = 4732
POPUP_OPEN_OFFSET = 31012
CITY_NPC_ACTIVE_OFFSET = 43077
ACTION_ACTIVE_OFFSET = 31145
SCREEN_IDS: frozenset = frozenset({'quote', 'scroll01', 'scroll02', 'menu', 'loadsave', 'newgame_intro', 'race_select', 'race_confirm', 'race_description', 'status_proclamation', 'class_select', 'class_list', 'class_accept', 'ten_questions', 'province_confirm', 'class_advice', 'goyenow', 'distribute', 'choose_attrs', 'name_input', 'sex_select', 'appearance', 'chargen_complete', 'opening_cinematic', 'game_screen', 'status_page', 'bonus_screen', 'equipment', 'spellbook', 'spell_detail', 'system_menu', 'loadsave_in_play', 'automap', 'logbook', 'npc_dialog', 'combat', 'shop', 'travel_map', 'message_box', 'loading', 'unknown'})

def _tr(sid: str, **kwargs) -> str:
    return _i18n.tr(f'screen.{sid}', **kwargs)

def _read_u8(analyzer, addr: int) -> int:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return 0

def _read_u16_le(analyzer, addr: int) -> int:
    try:
        b = analyzer.read_bytes(addr, 2)
        return b[0] | b[1] << 8
    except (OSError, AttributeError):
        return 65535
_CITY_NPC_PHASE_ASKING = 133
_CITY_NPC_PHASE_RESPONDING = 16

def is_city_npc_dialog_active(raw_value: int) -> bool:
    return int(raw_value) & 255 in (_CITY_NPC_PHASE_ASKING, _CITY_NPC_PHASE_RESPONDING)

def _detect_pregame_screen(img_name: str) -> Optional[Tuple[str, str]]:
    img_upper = (img_name or '').upper()
    if img_upper.endswith('.XMI'):
        return ('loading', _tr('loading'))
    if img_upper == 'QUOTE.IMG':
        return ('quote', _tr('quote'))
    if img_upper == 'SCROLL01.IMG':
        return ('scroll01', _tr('scroll01'))
    if img_upper == 'SCROLL02.IMG':
        return ('scroll02', _tr('scroll02'))
    if img_upper == 'MENU.IMG':
        return ('menu', _tr('menu'))
    if img_upper == 'LOADSAVE.IMG':
        return ('loadsave', _tr('loadsave'))
    return None

def detect_screen(analyzer, anchor: Optional[int], img_name: str, chargen_hint: Optional[str]=None, menu_active_was_zero: bool=False, top_level_state: str='pregame', last_chargen_subscreen: Optional[str]=None, mif_name: str='', area: Optional[str]=None) -> Tuple[str, str]:
    from screen_detector_chargen import detect_chargen_screen
    from screen_detector_play import detect_play_screen
    if analyzer is None or anchor is None:
        return ('loading', _tr('loading'))
    if top_level_state == 'pregame':
        result = _detect_pregame_screen(img_name)
        return result if result is not None else ('loading', _tr('loading'))
    elif top_level_state == 'chargen':
        result = detect_chargen_screen(chargen_hint, img_name, last_subscreen=last_chargen_subscreen)
        if result is not None:
            return result
        fallback = last_chargen_subscreen or 'loading'
        return (fallback, _tr(fallback))
    else:
        return detect_play_screen(analyzer, anchor, img_name, mif_name=mif_name, menu_active_was_zero=menu_active_was_zero, area=area)

def get_chargen_subscreen(window) -> Optional[str]:
    if getattr(window, '_chargen_opening_displayed', False):
        return 'opening_cinematic'
    if getattr(window, '_chargen_sex_select_displayed', False):
        return 'sex_select'
    if getattr(window, '_in_chargen_name', False):
        return 'name_input'
    if getattr(window, '_chargen_appearance_displayed', False):
        return 'appearance'
    if getattr(window, '_chargen_choose_attrs_displayed', False):
        return 'choose_attrs'
    if getattr(window, '_chargen_distribute_displayed', False):
        return 'distribute'
    if getattr(window, '_chargen_goyenow_displayed', False):
        return 'goyenow'
    if getattr(window, '_chargen_in_advice', False):
        return 'class_advice'
    if getattr(window, '_chargen_race_desc_displayed', False):
        return 'race_description'
    if getattr(window, '_chargen_complete_displayed', False):
        return 'status_proclamation'
    if getattr(window, '_chargen_race_select_displayed', False):
        return 'race_select'
    if getattr(window, '_chargen_class_accept_displayed', False):
        return 'class_accept'
    if getattr(window, '_chargen_10q_displayed', False):
        return 'ten_questions'
    if getattr(window, '_chargen_class_list_active', False):
        return 'class_list'
    if getattr(window, '_chargen_method_window', False):
        return 'class_select'
    return None
